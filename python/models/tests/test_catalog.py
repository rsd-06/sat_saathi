"""Declaring a model, and finding out whether this machine has it."""

from __future__ import annotations

import pytest

from satsaathi_models import CATALOG, ModelCatalog, ModelSpec


@pytest.fixture
def spec():
    return ModelSpec(name="vqa-test", task="vqa", revision="v1", queue="gpu")


def install(root, spec: ModelSpec, content: bytes = b"weights") -> None:
    path = spec.weights_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestAvailability:
    def test_a_model_with_no_weights_is_not_available(self, tmp_path, spec):
        assert spec.is_available(tmp_path) is False

    def test_a_model_becomes_available_once_its_weights_are_there(self, tmp_path, spec):
        install(tmp_path, spec)

        assert spec.is_available(tmp_path) is True

    def test_weights_for_one_revision_do_not_satisfy_another(self, tmp_path, spec):
        install(tmp_path, spec)
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
        install(tmp_path, spec)

        assert spec.fingerprint(tmp_path) == spec.fingerprint(tmp_path)

    def test_swapped_weights_change_the_fingerprint(self, tmp_path, spec):
        install(tmp_path, spec, b"one set of weights")
        before = spec.fingerprint(tmp_path)
        install(tmp_path, spec, b"a different set entirely")

        # This is the point: weights replaced without bumping the revision
        # would otherwise be invisible in a trace.
        assert spec.fingerprint(tmp_path) != before

    def test_a_truncated_file_changes_the_fingerprint(self, tmp_path, spec):
        install(tmp_path, spec, b"x" * (4 << 20))
        before = spec.fingerprint(tmp_path)
        install(tmp_path, spec, b"x" * (3 << 20))

        assert spec.fingerprint(tmp_path) != before


class TestCatalog:
    def test_it_reports_a_declared_model_that_is_not_installed(self, tmp_path):
        catalog = ModelCatalog(tmp_path)

        statuses = catalog.all_status()

        # Every declared model appears, so the settings screen can name what
        # is missing rather than quietly listing fewer capabilities.
        assert len(statuses) == len(CATALOG)
        assert all(status.available is False for status in statuses)

    def test_an_unknown_model_has_no_status(self, tmp_path):
        assert ModelCatalog(tmp_path).status("not-a-model") is None
        assert ModelCatalog(tmp_path).is_available("not-a-model") is False

    def test_available_names_lists_only_what_is_installed(self, tmp_path):
        catalog = ModelCatalog(tmp_path)
        installed = CATALOG[0]
        install(tmp_path, installed)

        assert catalog.available_names() == {installed.name}

    def test_status_carries_the_fingerprint_of_installed_weights(self, tmp_path):
        catalog = ModelCatalog(tmp_path)
        install(tmp_path, CATALOG[0])

        status = catalog.status(CATALOG[0].name)

        assert status is not None
        assert status.available is True
        assert status.fingerprint is not None

    def test_the_shipped_catalog_has_no_duplicate_names(self):
        names = [spec.name for spec in CATALOG]

        assert len(names) == len(set(names))

    def test_every_shipped_model_names_a_real_task(self):
        from satsaathi_tools.protocol import TASKS

        for spec in CATALOG:
            assert spec.task in TASKS, spec.name
