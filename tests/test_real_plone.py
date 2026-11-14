"""Opt-in integration against an already installed, disposable Plone environment."""

from pathlib import Path

import base64
import http.client
import os
import pytest
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import yaml

PLONE_ENV = os.environ.get("PLONEX_INTEGRATION_VENV")
pytestmark = pytest.mark.skipif(
    not PLONE_ENV, reason="Set PLONEX_INTEGRATION_VENV to a Plone virtualenv"
)


def test_real_zeo_wsgi_backup_and_restore(tmp_path):
    environment = Path(PLONE_ENV).resolve()
    for binary in ("runzeo", "runwsgi", "repozo"):
        if not (environment / "bin" / binary).is_file():
            pytest.fail(f"Integration virtualenv lacks {binary}")
    (tmp_path / ".venv").symlink_to(environment)
    (tmp_path / "etc").mkdir()
    panel = bool(os.environ.get("PLONEX_INTEGRATION_PANEL"))
    config = {"plonex_base_constraint": None, "http_address": "127.0.0.1"}
    if panel:
        config.update(
            {
                "cron_control_panel": True,
                "upgrade_tempfile_auth": True,
                "environment_vars": {"PYTHONPATH": str(tmp_path)},
                "cron_jobs": {
                    "smoke": {
                        "schedule": "* * * * *",
                        "enabled": False,
                        "callable": "integration_jobs:run",
                        "user": "scheduler",
                        "site": "/Plone",
                    }
                },
            }
        )
        (tmp_path / "integration_jobs.py").write_text(
            'def run(context):\n    context.setTitle("Updated by scheduled job")\n'
        )
    (tmp_path / "etc/plonex.yml").write_text(yaml.safe_dump(config))
    env = dict(os.environ) | {"PYTHONDONTWRITEBYTECODE": "1"}
    prefix = [sys.executable, "-m", "plonex.cli", "--target", str(tmp_path)]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    processes = []
    logs = []

    def launch(name, *args):
        stream = (tmp_path / (name + ".log")).open("w+")
        logs.append(stream)
        proc = subprocess.Popen(
            [*prefix, *args],
            cwd=tmp_path,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(proc)
        return proc

    def wait_until(predicate, proc, name):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.fail(
                    f'{name} exited: {(tmp_path / (name + ".log")).read_text()}'
                )
            if predicate():
                return
            time.sleep(0.2)
        pytest.fail(f'{name} did not start: {(tmp_path / (name + ".log")).read_text()}')

    def http_ready():
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", "/")
            response = connection.getresponse()
            response.read()
            connection.close()
            return 100 <= response.status < 600
        except (OSError, http.client.HTTPException):
            return False

    try:
        zeo = launch("zeo", "db", "start")
        wait_until((tmp_path / "var/zeosocket.sock").exists, zeo, "zeo")
        if panel:
            create_user = subprocess.run(
                [*prefix, "instance", "add-user", "admin", "integration-secret"],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            assert create_user.returncode == 0, create_user.stdout + create_user.stderr
            setup = tmp_path / "create_site.py"
            setup.write_text("""
import transaction
from AccessControl.SecurityManagement import newSecurityManager
from Products.CMFPlone.factory import addPloneSite
from zope.component.hooks import setSite
user = app.acl_users.getUser('admin').__of__(app.acl_users)
newSecurityManager(None, user)
addPloneSite(app, 'Plone', setup_content=False)
site = app['Plone']
setSite(site)
site.acl_users.userFolderAddUser('scheduler', 'integration-secret', ['Manager'], [])
site.portal_setup.runAllImportStepsFromProfile('profile-plonex.services.cron:queue-control-panel')
site.portal_setup.runAllImportStepsFromProfile('profile-collective.ftw.upgrade:default')
transaction.commit()
""")
            created = subprocess.run(
                [*prefix, "instance", "run", "--", str(setup)],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert created.returncode == 0, created.stdout + created.stderr
        instance = launch(
            "instance", "instance", "start", "--host", "127.0.0.1", "--port", str(port)
        )
        wait_until(http_ready, instance, "instance")
        if os.environ.get("PLONEX_INTEGRATION_DEBUGGER"):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                debug_port = probe.getsockname()[1]
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                debug_http_port = probe.getsockname()[1]
            debug = launch(
                "debug",
                "instance",
                "debug",
                "--host",
                "127.0.0.1",
                "--port",
                str(debug_http_port),
                "--debugpy",
                str(debug_port),
            )

            def debug_ready():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", debug_port), timeout=0.5
                    ):
                        return True
                except OSError:
                    return False

            wait_until(debug_ready, debug, "debug")
        if panel:
            endpoint = "/Plone/@@plonex-queue"
            authorization = (
                "Basic " + base64.b64encode(b"scheduler:integration-secret").decode()
            )

            def request(method, data=None, authenticated=True):
                headers = {"Authorization": authorization} if authenticated else {}
                if data is not None:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    data = urllib.parse.urlencode(data)
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
                connection.request(method, endpoint, body=data, headers=headers)
                response = connection.getresponse()
                body = response.read().decode(errors="replace")
                status = response.status
                connection.close()
                return status, body

            status, _ = request("GET", authenticated=False)
            assert status in {302, 401, 403}
            status, body = request("GET")
            assert status == 200, body
            token = re.search(r'name="_authenticator" value="([^"]+)"', body).group(1)
            status, _ = request("POST", {"action": "enqueue", "value": "smoke"})
            assert status == 403
            status, body = request(
                "POST", {"action": "enqueue", "value": "smoke", "_authenticator": token}
            )
            assert status in {302, 303}, body
            daemon = launch("cron", "cron", "daemon")

            def job_succeeded():
                history = tmp_path / "var/cron/history.sqlite3"
                if not history.is_file():
                    return False
                with sqlite3.connect(history) as db:
                    return bool(
                        db.execute(
                            "SELECT 1 FROM runs "
                            "WHERE job='smoke' AND status='succeeded'"
                        ).fetchone()
                    )

            wait_until(job_succeeded, daemon, "cron")
            check = tmp_path / "check_site.py"
            check.write_text('print("SITE_TITLE:", app["Plone"].Title())\n')
            checked = subprocess.run(
                [*prefix, "instance", "run", "--", str(check)],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            assert checked.returncode == 0, checked.stdout + checked.stderr
            assert "SITE_TITLE: Updated by scheduled job" in checked.stdout
            upgraded = subprocess.run(
                [*prefix, "db", "upgrade", "--url", f"http://127.0.0.1:{port}/"],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
            temporary_upgrade = subprocess.run(
                [*prefix, "db", "upgrade"],
                cwd=tmp_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert temporary_upgrade.returncode == 0, (
                temporary_upgrade.stdout
                + temporary_upgrade.stderr
                + (tmp_path / "var/log/upgrade.logs").read_text()
            )
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                os.killpg(proc.pid, 15)
        for proc in reversed(processes):
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, 9)
                proc.wait(timeout=5)
        for stream in logs:
            stream.close()
    backup = subprocess.run(
        [*prefix, "db", "backup"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert backup.returncode == 0, backup.stdout + backup.stderr
    restored = subprocess.run(
        [*prefix, "db", "restore", "--to", str(tmp_path / "restored")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (tmp_path / "restored/Data.fs").is_file()
    assert (tmp_path / "restored/blobstorage").is_dir()
