"""Declaring a model, and finding out whether this machine has it."""

from __future__ import annotations

import json

import pytest

from satsaathi_models import BASE_NAME, CATALOG, ModelCatalog, ModelSpec
from satsaathi_models.spec import ADAPTER_FILES, HF_BASE_FILES
from satsaathi_models.testing import install_fake

SAR_EVAL = {
    "model": "Qwen/Qwen3-VL-2B-Instruct",
    "base": {"ground_acc@0.5": 0.0125, "scene_acc": 0.2333},
    "finetuned": {"ground_acc@0.5": 0.2, "ground_mIoU": 0.2018, "scene_acc": 0.8833},
}


@pytest.fixture
def spec():
    return ModelSpec(name="vqa-test", task="vqa", revision="v1", queue="gpu")


class TestOwnFiles:
    def test_a_model_with_no_weights_is_not_available(self, tmp_path, spec):
        assert spec.is_available(tmp_path) is False

    def test_every_missing_file_is_named(self, tmp_path, spec):
        assert spec.missing_files(tmp_path) == list(HF_BASE_FILES)

    def test_a_base_needs_every_file_its_loader_opens(self, tmp_path, spec):
        install_fake(tmp_path, spec, specs=(spec,))
        (spec.directory(tmp_path) / "chat_template.json").unlink()

        assert spec.missing_files(tmp_path) == ["chat_template.json"]
        assert spec.is_available(tmp_path) is False

    def test_a_model_becomes_available_once_its_files_are_there(self, tmp_path, spec):
        install_fake(tmp_path, spec, specs=(spec,))

        assert spec.is_available(tmp_path) is True

    def test_an_adapter_needs_its_weights_config_and_meta(self):
        sar = next(s for s in CATALOG if s.name == "vqa-sar")

        assert sar.required_files == ADAPTER_FILES + ("satquery_sar_meta.json",)

    def test_weights_for_one_revision_do_not_satisfy_another(self, tmp_path, spec):
        install_fake(tmp_path, spec, specs=(spec,))
        newer = ModelSpec(name="vqa-test", task="vqa", revision="v2")

        # Revisions are separate directories on purpose: dropping new weights
        # in must not silently change what an old trace claimed to have run.
        assert newer.is_available(tmp_path) is False

    def test_a_missing_directory_is_a_missing_model_not_a_crash(self, tmp_path, spec):
        catalog = ModelCatalog(tmp_path / "does" / "not" / "exist", (spec,))

        assert catalog.is_available("vqa-test") is False
        assert catalog.available_names() == set()


class TestFingerprint:
    def test_absent_weights_have_no_fingerprint(self, tmp_path, spec):
        assert spec.fingerprint(tmp_path) is None

    def test_the_fingerprint_is_stable_for_the_same_bytes(self, tmp_path, spec):
        install_fake(tmp_path, spec, specs=(spec,))

        assert spec.fingerprint(tmp_path) == spec.fingerprint(tmp_path)

    def test_swapped_weights_change_the_fingerprint(self, tmp_path, spec):
        install_fake(tmp_path, spec, specs=(spec,), weights=b"one set of weights")
        before = spec.fingerprint(tmp_path)
        install_fake(tmp_path, spec, specs=(spec,), weights=b"a different set entirely")

        # Weights replaced without bumping the revision would otherwise be
        # invisible in a trace.
        assert spec.fingerprint(tmp_path) != before

    def test_a_truncated_file_changes_the_fingerprint(self, tmp_path, spec):
        install_fake(tmp_path, spec, specs=(spec,), weights=b"x" * (4 << 20))
        before = spec.fingerprint(tmp_path)
        install_fake(tmp_path, spec, specs=(spec,), weights=b"x" * (3 << 20))

        assert spec.fingerprint(tmp_path) != before

    def test_code_only_models_have_no_fingerprint(self, tmp_path):
        water = next(s for s in CATALOG if s.name == "sar-water-mask")

        assert water.fingerprint(tmp_path) is None


class TestAdapters:
    def test_an_adapter_is_unavailable_until_its_base_is_installed(self, tmp_path):
        install_fake(tmp_path, "vqa-sar", with_base=False)

        status = ModelCatalog(tmp_path).status("vqa-sar")

        assert status.installed is True
        assert status.available is False
        assert status.reason_key == "model.base_missing"
        assert status.reason_params == {"base": BASE_NAME}

    def test_an_adapter_with_its_base_is_available(self, tmp_path):
        install_fake(tmp_path, "vqa-sar")

        status = ModelCatalog(tmp_path).status("vqa-sar")

        assert status.available is True
        assert status.compatible is True
        assert status.reason_key is None

    def test_an_adapter_trained_on_another_base_is_refused(self, tmp_path):
        install_fake(tmp_path, "vqa-sar", base_repo="Qwen/Qwen2.5-VL-3B-Instruct")

        status = ModelCatalog(tmp_path).status("vqa-sar")

        # Present on disk, and still never offered: a LoRA on the wrong base
        # produces fluent nonsense nothing downstream could catch.
        assert status.installed is True
        assert status.available is False
        assert status.compatible is False
        assert status.reason_key == "model.base_mismatch"
        assert status.reason_params == {
            "expected": "Qwen/Qwen3-VL-2B-Instruct",
            "found": "Qwen/Qwen2.5-VL-3B-Instruct",
        }

    def test_an_unreadable_adapter_config_is_not_trusted(self, tmp_path):
        spec = install_fake(tmp_path, "vqa-sar")
        (spec.directory(tmp_path) / "adapter_config.json").write_text("{not json")

        status = ModelCatalog(tmp_path).status("vqa-sar")

        assert status.available is False
        assert status.reason_key == "model.adapter_config_unreadable"

    def test_missing_adapter_files_are_reported_by_name(self, tmp_path):
        spec = install_fake(tmp_path, "vqa-sar")
        (spec.directory(tmp_path) / "satquery_sar_meta.json").unlink()

        status = ModelCatalog(tmp_path).status("vqa-sar")

        assert status.reason_key == "model.not_installed"
        assert status.missing_files == ["satquery_sar_meta.json"]


class TestEval:
    def test_eval_metrics_are_exposed_when_installed(self, tmp_path):
        install_fake(tmp_path, "vqa-sar", eval_doc=SAR_EVAL)

        status = ModelCatalog(tmp_path).status("vqa-sar")

        assert status.eval["finetuned"]["scene_acc"] == 0.8833

    def test_the_prior_is_the_held_out_metric_for_that_task(self, tmp_path):
        install_fake(tmp_path, "vqa-sar", eval_doc=SAR_EVAL)
        catalog = ModelCatalog(tmp_path)

        # SAR grounding is weak and must stay weak in every confidence built
        # on it; the scene metric must not leak into a box's prior.
        assert catalog.prior("vqa-sar", "grounding") == 0.2
        assert catalog.prior("vqa-sar", "vqa") == 0.8833

    def test_no_eval_file_means_no_prior(self, tmp_path):
        install_fake(tmp_path, "vqa-sar")

        assert ModelCatalog(tmp_path).prior("vqa-sar", "grounding") is None

    def test_a_corrupt_eval_file_is_ignored_not_fatal(self, tmp_path):
        spec = install_fake(tmp_path, "vqa-sar")
        (spec.directory(tmp_path) / "eval.json").write_text("[1, 2")

        assert ModelCatalog(tmp_path).status("vqa-sar").eval is None

    def test_the_manifest_is_exposed(self, tmp_path):
        spec = install_fake(tmp_path, "vqa-sar")
        (spec.directory(tmp_path) / "manifest.json").write_text(json.dumps({"sha256": "ab"}))

        assert ModelCatalog(tmp_path).status("vqa-sar").manifest == {"sha256": "ab"}


class TestKinds:
    def test_a_composite_needs_everything_it_uses(self, tmp_path):
        install_fake(tmp_path, "vqa-optical")

        status = ModelCatalog(tmp_path).status("fusion-optical-sar")

        assert status.available is False
        assert status.reason_key == "model.dependency_missing"
        assert status.reason_params == {"model": "vqa-sar"}

    def test_a_composite_is_available_once_its_parts_are(self, tmp_path):
        install_fake(tmp_path, "fusion-optical-sar")

        assert ModelCatalog(tmp_path).is_available("fusion-optical-sar") is True

    def test_a_classical_model_is_always_available(self, tmp_path):
        status = ModelCatalog(tmp_path).status("sar-water-mask")

        assert status.available is True
        assert status.spec.queue == "cpu"

    def test_a_declared_stub_is_never_available_and_says_so(self, tmp_path):
        status = ModelCatalog(tmp_path).status("translate-indic")

        assert status.available is False
        assert status.is_stub is True
        assert status.reason_key == "model.stub"


class TestCatalog:
    def test_it_reports_every_declared_model(self, tmp_path):
        statuses = ModelCatalog(tmp_path).all_status()

        # Every declared model appears, so the settings screen can name what
        # is missing rather than quietly listing fewer capabilities.
        assert len(statuses) == len(CATALOG)
        # Only code-only models are usable on an empty machine.
        assert {s.spec.name for s in statuses if s.available} == {"sar-water-mask"}

    def test_an_unknown_model_has_no_status(self, tmp_path):
        assert ModelCatalog(tmp_path).status("not-a-model") is None
        assert ModelCatalog(tmp_path).is_available("not-a-model") is False

    def test_available_names_lists_only_what_is_usable(self, tmp_path):
        install_fake(tmp_path, "vqa-sar")

        assert ModelCatalog(tmp_path).available_names() == {
            BASE_NAME,
            "vqa-sar",
            "sar-water-mask",
        }

    def test_status_carries_the_fingerprint_of_installed_weights(self, tmp_path):
        install_fake(tmp_path, "vqa-sar")

        assert ModelCatalog(tmp_path).status("vqa-sar").fingerprint is not None

    def test_the_shipped_catalog_has_no_duplicate_names(self):
        names = [spec.name for spec in CATALOG]

        assert len(names) == len(set(names))

    def test_every_adapter_names_a_declared_base(self):
        names = {spec.name for spec in CATALOG}
        for spec in CATALOG:
            if spec.kind == "lora_adapter":
                assert spec.base in names, spec.name
                assert spec.meta_file, spec.name

    def test_every_shipped_model_names_a_real_task(self):
        # Mirrors satsaathi_tools.protocol.TASKS; importing it here would make
        # the dependency-free models package depend on tools.
        tasks = {
            "vqa", "caption", "grounding", "change_detection", "change_vqa",
            "optical_sar_fusion", "index_compute", "sar_water_mask", "translate",
            "asr", "tts", "llm_explain", "verify",
        }
        for spec in CATALOG:
            assert spec.task in tasks, spec.name

    def test_the_package_imports_no_deep_learning_runtime(self):
        import subprocess
        import sys

        code = (
            "import sys, satsaathi_models, satsaathi_models.testing;"
            "bad=[m for m in ('torch','transformers','peft') if m in sys.modules];"
            "print(','.join(bad))"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == ""
