# The GPU stack is an optional extra; CI type-checks without it.
# pyright: reportMissingImports=false
"""`uv run satsaathi-models <command>` — install, check and load-test the models.

    doctor                      is this machine able to run the models? (exit 1 if not)
    pull                        download the pinned base snapshot
    install NAME ADAPTER_DIR    copy a trained adapter in, with its meta and eval
    load-test [--adapters all] [--n 5]
                                load everything, run the golden fixtures, report numbers

Every command reads the models directory from settings (MODELS_DIR, default
./.data/models) unless --models-dir is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from satsaathi_models import BASE_NAME, CATALOG, ModelCatalog

PASS, WARN, FAIL = "pass", "warn", "FAIL"

#: Minimums from the training runs: ~2.6 GB of VRAM at the training settings
#: (plus KV cache), and 5-6 GB of system RAM while the checkpoint loads.
MIN_FREE_VRAM_MB = 2800
MIN_FREE_RAM_MB = 5500

#: Adapter files copied besides the required ones: the tokenizer and
#: processor the adapter was saved with, and its README.
OPTIONAL_ADAPTER_FILES = (
    "chat_template.jinja",
    "processor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "README.md",
)


def _models_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    from satsaathi_core.settings import get_settings

    return Path(get_settings().models_dir)


def _table(rows: list[tuple[str, str, str]]) -> str:
    width = max(len(r[0]) for r in rows) if rows else 10
    return "\n".join(f"  {status:<4}  {name:<{width}}  {detail}" for name, status, detail in rows)


# -- doctor ------------------------------------------------------------------


def doctor_rows(catalog: ModelCatalog) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    try:
        import torch

        rows.append(("torch", PASS, torch.__version__))
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            rows.append(("cuda visible", PASS, f"{name}, CUDA {torch.version.cuda}"))
            bf16 = torch.cuda.is_bf16_supported()
            rows.append(
                ("bf16 support", PASS if bf16 else WARN,
                 "bf16" if bf16 else "no bf16 on this GPU; compute falls back to fp16")
            )
            free, total = torch.cuda.mem_get_info()
            free_mb = free / 2**20
            rows.append(
                ("free VRAM", PASS if free_mb >= MIN_FREE_VRAM_MB else FAIL,
                 f"{free_mb:.0f} / {total / 2**20:.0f} MB (need {MIN_FREE_VRAM_MB})")
            )
        else:
            rows.append(("cuda visible", FAIL, "torch.cuda.is_available() is False"))
    except ImportError as exc:
        rows.append(("torch", FAIL, f"not installed ({exc}); uv sync --extra gpu"))

    for module in ("transformers", "peft", "bitsandbytes"):
        try:
            mod = __import__(module)
            rows.append((module, PASS, getattr(mod, "__version__", "?")))
        except Exception as exc:  # noqa: BLE001 - bitsandbytes raises odd things
            rows.append((module, FAIL, f"import failed: {exc}"))

    try:
        import psutil

        avail = psutil.virtual_memory().available / 2**20
        rows.append(
            ("free RAM", PASS if avail >= MIN_FREE_RAM_MB else WARN,
             f"{avail:.0f} MB available (loading needs ~{MIN_FREE_RAM_MB})")
        )
    except ImportError:
        rows.append(("free RAM", WARN, "psutil not installed; not checked"))

    for status in catalog.all_status():
        spec = status.spec
        label = f"{spec.name}@{spec.revision}"
        if spec.kind == "hf_base":
            rows.append(
                (label, PASS if status.available else FAIL,
                 "all files present" if status.available
                 else f"missing {', '.join(status.missing_files)}; run `pull`")
            )
        elif spec.kind == "lora_adapter":
            if status.available:
                prior = status.eval and status.eval.get("finetuned")
                rows.append((label, PASS, "files present, base matches"
                             + (f", eval {json.dumps(prior)}" if prior else ", no eval.json")))
            elif status.reason_key == "model.base_mismatch":
                rows.append((label, FAIL, f"trained on {status.reason_params.get('found')}, "
                             f"not {status.reason_params.get('expected')}"))
            elif status.reason_key == "model.not_installed":
                rows.append((label, WARN, f"not installed (missing "
                             f"{', '.join(status.missing_files)})"))
            else:
                rows.append((label, FAIL, status.reason_key or "unavailable"))
        elif spec.kind == "composite":
            rows.append((label, PASS if status.available else WARN,
                         "ready" if status.available else
                         f"waiting for {status.reason_params.get('model')}"))
        elif spec.kind == "stub":
            rows.append((label, WARN, "declared stub; not implemented"))
        else:
            rows.append((label, PASS, "classical; no weights"))
    return rows


def cmd_doctor(args: argparse.Namespace) -> int:
    catalog = ModelCatalog(_models_dir(args.models_dir))
    rows = doctor_rows(catalog)
    print(f"models dir: {catalog.root.resolve()}")
    print(_table(rows))
    failed = [r for r in rows if r[1] == FAIL]
    print(f"\n{'FAILED' if failed else 'OK'}: {len(failed)} failing check(s)")
    return 1 if failed else 0


# -- pull --------------------------------------------------------------------


def cmd_pull(args: argparse.Namespace) -> int:
    from huggingface_hub import snapshot_download

    root = _models_dir(args.models_dir)
    spec = next(s for s in CATALOG if s.name == BASE_NAME)
    target = spec.directory(root)
    target.mkdir(parents=True, exist_ok=True)
    print(f"downloading {spec.hf_repo}@{spec.hf_revision} -> {target}")
    snapshot_download(
        repo_id=spec.hf_repo or "",
        revision=spec.hf_revision,
        local_dir=target,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.jinja"],
    )
    missing = spec.missing_files(root)
    if missing:
        print(f"FAILED: still missing {missing}")
        return 1
    print("OK: base snapshot complete")
    return 0


# -- install -----------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_adapter(
    root: Path, name: str, source: Path, eval_path: Path | None = None
) -> dict[str, Any]:
    """Copy an adapter into the models directory. Refuses a foreign base."""
    catalog = ModelCatalog(root)
    spec = catalog.get(name)
    if spec is None or spec.kind != "lora_adapter":
        raise SystemExit(f"{name} is not an adapter in the catalog")
    base = catalog.get(spec.base or "")
    assert base is not None

    config = json.loads((source / "adapter_config.json").read_text(encoding="utf-8"))
    declared = config.get("base_model_name_or_path")
    if declared != base.hf_repo:
        raise SystemExit(
            f"refusing {source}: trained on {declared}, catalog base is {base.hf_repo}"
        )
    missing = [f for f in spec.required_files if not (source / f).is_file()]
    if missing:
        raise SystemExit(f"refusing {source}: missing {missing}")

    target = spec.directory(root)
    target.mkdir(parents=True, exist_ok=True)
    for name_ in spec.required_files + OPTIONAL_ADAPTER_FILES:
        if (source / name_).is_file():
            shutil.copy2(source / name_, target / name_)

    eval_candidates = (
        [eval_path] if eval_path else [source / "eval.json", source.parent / "eval.json"]
    )
    eval_used = next((p for p in eval_candidates if p and p.is_file()), None)
    if eval_used:
        json.loads(eval_used.read_text(encoding="utf-8"))  # refuse garbage early
        shutil.copy2(eval_used, target / "eval.json")

    manifest = {
        "name": spec.name,
        "revision": spec.revision,
        "adapter_sha256": _sha256(target / "adapter_model.safetensors"),
        "base": base.name,
        "base_repo": base.hf_repo,
        "base_revision": base.hf_revision,
        "peft_version": config.get("peft_version"),
        "lora": {"r": config.get("r"), "alpha": config.get("lora_alpha")},
        "source": str(source.resolve()),
        "eval_source": str(eval_used.resolve()) if eval_used else None,
        "installed_at": datetime.now(UTC).isoformat(),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def cmd_install(args: argparse.Namespace) -> int:
    root = _models_dir(args.models_dir)
    manifest = install_adapter(
        root, args.name, Path(args.adapter_dir), Path(args.eval) if args.eval else None
    )
    print(json.dumps(manifest, indent=2))
    status = ModelCatalog(root).status(args.name)
    assert status is not None
    print(f"\n{args.name}: available={status.available} reason={status.reason_key}")
    return 0


# -- load-test ---------------------------------------------------------------


def _pct(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def cmd_load_test(args: argparse.Namespace) -> int:
    from . import golden
    from .runtime import get_runtime

    catalog = ModelCatalog(_models_dir(args.models_dir))
    golden_root = Path(os.environ.get("SATSAATHI_GOLDEN_DIR", golden.DEFAULT_ROOT))
    runtime = get_runtime(catalog)
    installed = runtime.adapter_names()
    wanted = installed if args.adapters == "all" else args.adapters.split(",")
    unknown = [a for a in wanted if a not in installed]
    if unknown:
        print(f"FAILED: not installed/available: {unknown}")
        return 1

    runtime.reset_peak()
    started = time.perf_counter()
    runtime.load()
    load_s = time.perf_counter() - started
    report: dict[str, Any] = {
        "load_seconds": round(load_s, 1),
        "adapters_loaded": runtime.stats.adapters_loaded,
        "adapters": {},
    }
    print(f"loaded base + {runtime.stats.adapters_loaded} in {load_s:.1f}s")

    ok = True
    for adapter in wanted:
        samples = golden.discover(adapter, golden_root)
        if not samples:
            print(f"  {adapter}: no golden fixtures under {golden_root / adapter}")
            ok = False
            continue
        latencies: list[int] = []
        parsed = passed = runs = 0
        results = []
        for i in range(args.n):
            sample = samples[i % len(samples)]
            result = golden.run_sample(runtime, sample)
            runs += 1
            latencies.append(result.latency_ms)
            parsed += int(result.parsed)
            passed += int(result.passed)
            if i < len(samples):
                results.append(result.to_dict())
        report["adapters"][adapter] = {
            "runs": runs,
            "p50_ms": _pct(latencies, 0.5),
            "p95_ms": _pct(latencies, 0.95),
            "parse_success": round(parsed / runs, 2),
            "checks_passed": round(passed / runs, 2),
            "samples": results,
        }
        print(
            f"  {adapter:<12} p50 {_pct(latencies, 0.5)} ms  p95 {_pct(latencies, 0.95)} ms  "
            f"parse {parsed}/{runs}  checks {passed}/{runs}"
        )

    # Adapter swapping must change what the model says. Same SAR sample,
    # same prompt, base (adapters disabled) versus the SAR adapter.
    swap: dict[str, Any] = {"checked": False}
    sar_samples = golden.discover("vqa-sar", golden_root) if "vqa-sar" in installed else []
    if sar_samples:
        sample = sar_samples[0]
        images, prompt, _ctx = golden.build_inputs(runtime, sample)
        system = str(runtime.meta("vqa-sar")["system_prompt"])
        base = runtime.generate(None, images, prompt, system=system, want_logprobs=False)
        tuned = runtime.generate("vqa-sar", images, prompt, want_logprobs=False)
        swap = {
            "checked": True,
            "sample": sample.name,
            "base": base.text.strip()[:160],
            "adapter": tuned.text.strip()[:160],
            "differs": base.text.strip() != tuned.text.strip(),
        }
        ok = ok and swap["differs"]
        print(f"  swap proof on {sample.name}: differs={swap['differs']}")
        print(f"    base   : {swap['base']!r}")
        print(f"    vqa-sar: {swap['adapter']!r}")
    report["swap"] = swap

    snap = runtime.snapshot()
    report["vram_peak_mb"] = snap["vram_peak_mb"]
    report["versions"] = {k: snap[k] for k in ("torch", "transformers", "peft", "bitsandbytes")}
    report["gpu_name"] = snap["gpu_name"]
    print(f"peak VRAM {snap['vram_peak_mb']} MB on {snap['gpu_name']}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"report -> {args.json}")
    runtime.unload()
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="satsaathi-models")
    parser.add_argument("--models-dir", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("pull").set_defaults(fn=cmd_pull)
    p = sub.add_parser("install")
    p.add_argument("name")
    p.add_argument("adapter_dir")
    p.add_argument("--eval", default=None, help="eval.json, if not next to the adapter")
    p.set_defaults(fn=cmd_install)
    p = sub.add_parser("load-test")
    p.add_argument("--adapters", default="all")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--json", default=None, help="write the full report here")
    p.set_defaults(fn=cmd_load_test)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
