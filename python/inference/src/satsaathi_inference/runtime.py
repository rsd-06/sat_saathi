# The GPU stack is an optional extra; CI type-checks without it.
# pyright: reportMissingImports=false
"""One resident base model, every adapter attached, one call at a time.

All adapters are LoRAs on the same Qwen3-VL-2B-Instruct, trained with QLoRA
(NF4, double quantisation, LoRA on the language model only). Loading a model
per catalog entry would hold the same 2 B parameters four times; instead the
base is loaded once in 4-bit, each installed adapter is attached with PEFT
under its catalog name, and a call selects one with `set_adapter`. "No
adapter" means `disable_adapter()`, which is how the plain base adjudicates
fusion.

The quantisation config is the one training used, field for field. Anything
else — 8-bit, a different compute dtype, a quantised vision tower — changes
the activations the LoRA weights were fitted to.

This is a single-GPU runtime: calls are serialised with a lock, and the
worker runs Celery with a solo pool because CUDA does not survive fork.
Memory is given back after an idle period, because the dev machine reaps
processes under memory pressure and a 4 GB model nobody is using should not
be the one it picks.
"""

from __future__ import annotations

import gc
import logging
import math
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from satsaathi_core import vlm_prompts
from satsaathi_models import (
    BASE_NAME,
    ModelCatalog,
    ModelOOMError,
    ModelUnavailableError,
)

logger = logging.getLogger(__name__)


@dataclass
class Generation:
    text: str
    #: Log-probability of each generated token under the distribution it was
    #: chosen from. Empty when not requested.
    token_logprobs: list[float]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    adapter: str | None

    @property
    def mean_token_prob(self) -> float | None:
        """Geometric-mean probability of the generated tokens."""
        if not self.token_logprobs:
            return None
        return math.exp(sum(self.token_logprobs) / len(self.token_logprobs))


@dataclass
class RuntimeStats:
    base_loaded: bool = False
    adapters_loaded: list[str] = field(default_factory=list)
    load_seconds: float | None = None
    last_inference_ms: int | None = None
    inferences_total: int = 0
    last_error_key: str | None = None
    last_used: float | None = None
    peak_vram_mb: float | None = None


def _version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


class VLMRuntime:
    """The process's one copy of the base and its adapters."""

    def __init__(self, catalog: ModelCatalog):
        self.catalog = catalog
        self._lock = threading.RLock()
        self._model: Any = None
        self._processor: Any = None
        self._is_peft = False
        self._metas: dict[str, dict[str, Any]] = {}
        self.stats = RuntimeStats()

    # -- lifecycle ---------------------------------------------------------

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def adapter_names(self) -> list[str]:
        """Adapters the catalog says are usable here, in a stable order."""
        return sorted(
            s.spec.name
            for s in self.catalog.all_status()
            if s.spec.kind == "lora_adapter" and s.available
        )

    def meta(self, adapter: str) -> dict[str, Any]:
        """The adapter's training meta. Readable without loading the model."""
        if adapter not in self._metas:
            spec = self.catalog.get(adapter)
            if spec is None or not spec.meta_file:
                raise ModelUnavailableError(f"{adapter}: not an adapter")
            path = spec.directory(self.catalog.root) / spec.meta_file
            try:
                self._metas[adapter] = vlm_prompts.load_meta(path)
            except vlm_prompts.MetaError as exc:
                raise ModelUnavailableError(str(exc)) from exc
        return self._metas[adapter]

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            try:
                self._load()
            except ModelUnavailableError as exc:
                self.stats.last_error_key = "model.not_loadable"
                logger.error("model load failed: %s", exc)
                self._release()
                raise
            except Exception as exc:  # noqa: BLE001 - any load failure is the same to a caller
                self.stats.last_error_key = (
                    "model.oom" if _is_oom(exc) else "model.not_loadable"
                )
                logger.exception("model load failed")
                self._release()
                if _is_oom(exc):
                    raise ModelOOMError(str(exc)) from exc
                raise ModelUnavailableError(f"{type(exc).__name__}: {exc}") from exc

    def _load(self) -> None:
        started = time.perf_counter()
        base_status = self.catalog.status(BASE_NAME)
        if base_status is None or not base_status.available:
            missing = base_status.missing_files if base_status else ["(not declared)"]
            raise ModelUnavailableError(f"base not installed; missing {missing}")

        try:
            import torch
            from transformers import (
                AutoModelForImageTextToText,
                AutoProcessor,
                BitsAndBytesConfig,
            )
        except ImportError as exc:
            raise ModelUnavailableError(f"GPU runtime not installed: {exc}") from exc
        if not torch.cuda.is_available():
            raise ModelUnavailableError("CUDA is not available to this process")

        # Native bf16 only; emulated bf16 (e.g. Turing) is slow under 4-bit.
        native_bf16 = torch.cuda.is_bf16_supported(including_emulation=False)
        compute = torch.bfloat16 if native_bf16 else torch.float16
        # Identical to training: NF4, double quantisation, vision tower and
        # LM head left unquantised.
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute,
            llm_int8_skip_modules=["visual", "lm_head"],
        )
        base_dir = Path(base_status.path)
        torch.cuda.reset_peak_memory_stats()
        model = AutoModelForImageTextToText.from_pretrained(
            base_dir,
            quantization_config=bnb,
            dtype=compute,
            device_map={"": 0},
            attn_implementation="sdpa",
        )
        processor = AutoProcessor.from_pretrained(base_dir)

        attached: list[str] = []
        adapters = self.adapter_names()
        if adapters:
            from peft import PeftModel

            first, *rest = adapters
            model = PeftModel.from_pretrained(
                model, self._adapter_dir(first), adapter_name=first, is_trainable=False
            )
            attached.append(first)
            for name in rest:
                model.load_adapter(self._adapter_dir(name), adapter_name=name)
                attached.append(name)
            self._is_peft = True
        model.eval()

        self._model = model
        self._processor = processor
        self.stats.base_loaded = True
        self.stats.adapters_loaded = attached
        self.stats.load_seconds = round(time.perf_counter() - started, 2)
        self.stats.last_error_key = None
        self.stats.last_used = time.time()
        self._record_peak()
        logger.info(
            "loaded %s with adapters %s in %.1fs (%s)",
            BASE_NAME, attached, self.stats.load_seconds, compute,
        )

    def _adapter_dir(self, name: str) -> str:
        spec = self.catalog.get(name)
        assert spec is not None
        return str(spec.directory(self.catalog.root))

    def unload(self) -> None:
        with self._lock:
            self._release()

    def _release(self) -> None:
        was_loaded = self._model is not None
        self._model = None
        self._processor = None
        self._is_peft = False
        self.stats.base_loaded = False
        self.stats.adapters_loaded = []
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        if was_loaded:
            logger.info("model unloaded")

    def unload_if_idle(self, idle_minutes: float) -> bool:
        """Free GPU and RAM if nothing has called for `idle_minutes`.

        Never blocks: if a call holds the lock right now, the model is plainly
        not idle.
        """
        if self._model is None or idle_minutes <= 0:
            return False
        last = self.stats.last_used or 0
        if time.time() - last < idle_minutes * 60:
            return False
        if not self._lock.acquire(blocking=False):
            return False
        try:
            self._release()
            return True
        finally:
            self._lock.release()

    # -- inference ---------------------------------------------------------

    def generate(
        self,
        adapter: str | None,
        images: list[Any],
        prompt: str,
        *,
        system: str | None = None,
        max_new_tokens: int = 256,
        want_logprobs: bool = True,
        sample: bool = False,
        temperature: float = 0.7,
    ) -> Generation:
        """One call. `adapter=None` runs the base with adapters disabled.

        The system prompt defaults to the adapter's own, from its meta;
        a caller cannot paraphrase it by accident.
        """
        if system is None:
            if adapter is None:
                raise ValueError("the base has no trained system prompt; pass one")
            system = str(self.meta(adapter)["system_prompt"])

        with self._lock:
            self.load()
            try:
                return self._generate(
                    adapter, images, prompt, system, max_new_tokens,
                    want_logprobs, sample, temperature,
                )
            except Exception as exc:
                if _is_oom(exc):
                    self.stats.last_error_key = "model.oom"
                    _empty_cache()
                    raise ModelOOMError(str(exc)) from exc
                self.stats.last_error_key = "model.inference_failed"
                raise
            finally:
                self.stats.last_used = time.time()

    def _generate(
        self,
        adapter: str | None,
        images: list[Any],
        prompt: str,
        system: str,
        max_new_tokens: int,
        want_logprobs: bool,
        sample: bool,
        temperature: float,
    ) -> Generation:
        import torch

        model, processor = self._model, self._processor
        if adapter is not None and adapter not in self.stats.adapters_loaded:
            raise ModelUnavailableError(f"adapter {adapter} is not attached")

        msgs = vlm_prompts.messages(system, len(images), prompt)
        text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        # Every processor output goes to generate — newer transformers needs
        # keys like mm_token_type_ids, and cherry-picking silently drops them.
        enc = processor(
            text=[text], images=list(images) or None, return_tensors="pt"
        ).to(model.device)
        input_len = int(enc["input_ids"].shape[1])

        if adapter is None:
            context = model.disable_adapter() if self._is_peft else nullcontext()
        else:
            model.set_adapter(adapter)
            context = nullcontext()

        kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": sample,
            "use_cache": True,
            "return_dict_in_generate": True,
            "output_scores": want_logprobs,
        }
        if sample:
            kwargs.update(temperature=temperature, top_p=1.0, top_k=0)
        else:
            # Greedy; clear the sampling defaults generation_config ships so
            # transformers does not warn on every call.
            kwargs.update(temperature=None, top_p=None, top_k=None)

        started = time.perf_counter()
        with context, torch.inference_mode():
            out = model.generate(**enc, **kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)

        generated = out.sequences[0, input_len:]
        logprobs: list[float] = []
        if want_logprobs and out.scores:
            for step, token in zip(out.scores, generated.tolist(), strict=False):
                row = torch.log_softmax(step[0].float(), dim=-1)
                value = float(row[token])
                if math.isfinite(value):
                    logprobs.append(value)
        decoded = processor.batch_decode(generated.unsqueeze(0), skip_special_tokens=True)[0]

        self.stats.inferences_total += 1
        self.stats.last_inference_ms = latency_ms
        self.stats.last_error_key = None
        self._record_peak()
        return Generation(
            text=decoded,
            token_logprobs=logprobs,
            latency_ms=latency_ms,
            input_tokens=input_len,
            output_tokens=int(generated.shape[0]),
            adapter=adapter,
        )

    # -- reporting ---------------------------------------------------------

    def _record_peak(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                peak = torch.cuda.max_memory_allocated() / 2**20
                self.stats.peak_vram_mb = round(max(peak, self.stats.peak_vram_mb or 0), 1)
        except ImportError:
            pass

    def reset_peak(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
                self.stats.peak_vram_mb = None
        except ImportError:
            pass

    def snapshot(self) -> dict[str, Any]:
        """What the heartbeat publishes. Plain JSON types only."""
        allocated = reserved = None
        gpu_name = None
        try:
            import torch

            if torch.cuda.is_available():
                allocated = round(torch.cuda.memory_allocated() / 2**20, 1)
                reserved = round(torch.cuda.memory_reserved() / 2**20, 1)
                gpu_name = torch.cuda.get_device_name(0)
        except ImportError:
            pass
        return {
            "base_loaded": self.stats.base_loaded,
            "adapters_loaded": list(self.stats.adapters_loaded),
            "vram_allocated_mb": allocated,
            "vram_reserved_mb": reserved,
            "vram_peak_mb": self.stats.peak_vram_mb,
            "gpu_name": gpu_name,
            "torch": _version("torch"),
            "transformers": _version("transformers"),
            "peft": _version("peft"),
            "bitsandbytes": _version("bitsandbytes"),
            "load_seconds": self.stats.load_seconds,
            "last_inference_ms": self.stats.last_inference_ms,
            "inferences_total": self.stats.inferences_total,
            "last_error_key": self.stats.last_error_key,
            "idle_seconds": (
                round(time.time() - self.stats.last_used, 1) if self.stats.last_used else None
            ),
        }


def _is_oom(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name == "OutOfMemoryError" or "CUDA out of memory" in str(exc)


def _empty_cache() -> None:
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


_runtime: VLMRuntime | None = None
_runtime_lock = threading.Lock()


def get_runtime(catalog: ModelCatalog) -> VLMRuntime:
    """The process singleton. One base per GPU process, however many callers."""
    global _runtime
    with _runtime_lock:
        if _runtime is None or Path(_runtime.catalog.root) != Path(catalog.root):
            _runtime = VLMRuntime(catalog)
        return _runtime


def current_runtime() -> VLMRuntime | None:
    return _runtime


def reset_runtime() -> None:
    """Drop the singleton. Tests only."""
    global _runtime
    with _runtime_lock:
        if _runtime is not None:
            _runtime.unload()
        _runtime = None
