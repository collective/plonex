from plonex.services.cron import CronService
from plonex.services.cron.installation import backend_config
from plonex.services.cron.installation import BACKENDS
from plonex.services.cron.installation import worker_requirements
from plonex.services.cron.runtime import QueueRuntime

import pytest
import sys


def test_backend_validation_and_requirements():
    for value in ("unknown", None, []):
        with pytest.raises(ValueError, match="cron_backend"):
            backend_config({"cron_backend": value})
    for value in ([], {"name": "other"}):
        with pytest.raises(ValueError, match="cron_backend_options"):
            backend_config({"cron_backend_options": value})
    assert "redis" in worker_requirements({"cron_backend": "redis"})
    assert "psycopg>=3.2" in worker_requirements({"cron_backend": "postgres"})
    assert len(BACKENDS) == 10


@pytest.mark.parametrize(
    "backend,settings",
    [
        ("sqlite", {"filename": "custom.sqlite3"}),
        ("file", {"path": "queue-files"}),
    ],
)
def test_persistent_backend_shared_between_runtime_instances(
    tmp_path, monkeypatch, backend, settings
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "etc").mkdir()
    options = {
        "cron_backend": backend,
        "cron_backend_options": settings,
        "cron_jobs": {
            "job": {
                "schedule": "* * * * *",
                "enabled": False,
                "command": [sys.executable, "-c", "pass"],
            }
        },
    }
    service = CronService(target=tmp_path, cli_options=options)
    with QueueRuntime(service) as producer:
        task = producer.enqueue("job")
    with QueueRuntime(service, read_only=True) as inspector:
        assert inspector.queue()["pending"][0]["task_id"] == task["task_id"]
    with QueueRuntime(service) as consumer:
        consumer.tasks
        consumer.huey.execute(consumer.huey.dequeue())
        assert consumer.runner.history()[0]["status"] == "succeeded"
