"""Loading a model once per process, and refusing to fake it."""

from __future__ import annotations

import pytest

from satsaathi_models import (
    ModelSpec,
    ModelUnavailableError,
    clear_loaders,
    load,
    loaded_names,
    register_loader,
    unload_all,
)


@pytest.fixture(autouse=True)
def clean_cache():
    clear_loaders()
    yield
    clear_loaders()


@pytest.fixture
def spec():
    return ModelSpec(name="fake", task="vqa", revision="v1", runtime="fake-runtime")


def install(root, spec):
    from satsaathi_models.testing import install_fake

    install_fake(root, spec, specs=(spec,))


def test_missing_weights_raise_rather_than_returning_a_placeholder(tmp_path, spec):
    # A caller that asked for a real prediction must not be handed something
    # that quietly is not one.
    with pytest.raises(ModelUnavailableError):
        load(spec, tmp_path)


def test_a_runtime_with_no_loader_raises(tmp_path, spec):
    install(tmp_path, spec)

    with pytest.raises(ModelUnavailableError, match="no loader"):
        load(spec, tmp_path)


def test_weights_are_loaded_once_and_reused(tmp_path, spec):
    install(tmp_path, spec)
    calls = []

    def loader(model_spec, directory):
        calls.append(directory)
        return {"loaded": model_spec.name}

    register_loader("fake-runtime", loader)

    first = load(spec, tmp_path)
    second = load(spec, tmp_path)

    assert first is second
    assert len(calls) == 1
    assert loaded_names() == {spec.slug}


def test_two_revisions_are_cached_separately(tmp_path, spec):
    newer = ModelSpec(name="fake", task="vqa", revision="v2", runtime="fake-runtime")
    install(tmp_path, spec)
    install(tmp_path, newer)
    register_loader("fake-runtime", lambda s, d: {"revision": s.revision})

    assert load(spec, tmp_path) is not load(newer, tmp_path)
    assert loaded_names() == {"fake@v1", "fake@v2"}


def test_unloading_clears_everything(tmp_path, spec):
    install(tmp_path, spec)
    register_loader("fake-runtime", lambda s, d: object())
    load(spec, tmp_path)

    unload_all()

    assert loaded_names() == set()
