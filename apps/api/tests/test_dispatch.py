import logging
import uuid

import pytest
from fastapi import BackgroundTasks

from satsaathi_api.dispatch import dispatch_job
from satsaathi_core.settings import Settings


@pytest.fixture
def job_id():
    return uuid.uuid4()


def test_inline_dispatch_runs_the_job_in_this_process(job_id):
    settings = Settings(job_dispatch="inline")
    background = BackgroundTasks()

    dispatch_job(job_id, settings, background)

    assert [t.args for t in background.tasks] == [(job_id,)]


def test_celery_dispatch_enqueues_by_name_and_queues_nothing_locally(
    job_id, monkeypatch
):
    sent = {}

    def fake_send(jid, _settings):
        sent["id"] = jid

    monkeypatch.setattr("satsaathi_api.dispatch.send_to_celery", fake_send)
    settings = Settings(job_dispatch="celery")
    background = BackgroundTasks()

    dispatch_job(job_id, settings, background)

    assert sent["id"] == job_id
    assert background.tasks == []


def test_an_unreachable_broker_falls_back_rather_than_stranding_the_job(
    job_id, monkeypatch, caplog
):
    # A job left queued for ever with nothing to explain it is the worst of
    # the available outcomes: the user waits, and no trace says why.
    def boom(_jid, _settings):
        raise ConnectionError("no broker")

    monkeypatch.setattr("satsaathi_api.dispatch.send_to_celery", boom)
    settings = Settings(job_dispatch="celery")
    background = BackgroundTasks()

    with caplog.at_level(logging.ERROR, logger="satsaathi_api.dispatch"):
        dispatch_job(job_id, settings, background)

    assert [t.args for t in background.tasks] == [(job_id,)]
    # Falling back silently would make a misconfigured deployment look like a
    # working one, so the log has to say it happened.
    assert "celery dispatch failed" in caplog.text
