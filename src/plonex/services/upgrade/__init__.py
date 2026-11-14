from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from plonex.base import BaseService
from urllib.parse import urlparse

import os
import socket
import subprocess
import tempfile
import time


def private_auth_directory(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(
            f"Upgrade authentication directory must not be a symlink: {path}"
        )
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.stat()
    if info.st_mode & 0o077 or info.st_uid != os.geteuid():
        raise ValueError(
            "Upgrade authentication directory must be private "
            f"and owned by this user: {path}"
        )
    return path


def configured_auth_directory(service):
    configured = service.options.get("environment_vars", {}).get(
        "UPGRADE_TEMPFILE_AUTH_DIR"
    )
    if isinstance(configured, str):
        configured = configured.format(**service.options)
    path = Path(configured or service.var_folder / "ftw.upgrade-authentication")
    return path if path.is_absolute() else service.target / path


@dataclass(kw_only=True)
class UpgradeService(BaseService):
    name: str = "upgrade"

    @BaseService.entered_only
    def run(self):
        upgrade = self.virtualenv_dir / "bin/upgrade"
        if not upgrade.is_file():
            raise ValueError(
                "The upgrade executable is missing. "
                "Install collective.ftw.upgrade in the project."
            )
        url = self.options.get("upgrade_url") or os.environ.get("UPGRADE_ZOPE_URL")
        if url:
            self._run_upgrades(upgrade, str(url), temporary=False)
        else:
            from plonex.files import project_lock

            with project_lock(self.var_folder / "upgrade-lock"):
                with self._temporary_instance() as url:
                    self._run_upgrades(upgrade, url, temporary=True)

    def _run_upgrades(self, upgrade, url, *, temporary):
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Upgrade URL must be an HTTP(S) URL without credentials")
        values = {"UPGRADE_ZOPE_URL": url}
        if temporary or self.options.get("upgrade_tempfile_auth"):
            auth = configured_auth_directory(self)
            private_auth_directory(auth)
            values["UPGRADE_TEMPFILE_AUTH_DIR"] = str(auth)
        elif not os.environ.get("UPGRADE_AUTHENTICATION") and not os.environ.get(
            "UPGRADE_TEMPFILE_AUTH_DIR"
        ):
            raise ValueError(
                "Configure upgrade_tempfile_auth and restart the instance, "
                "or provide upgrade authentication."
            )
        previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        try:
            self.run_command([upgrade, "plone_upgrade", "-A"])
            self.run_command([upgrade, "install", "-Ap"])
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @BaseService.entered_only
    def run_command(self, command, cwd=None):
        log_path = self.var_folder / "log" / "upgrade.logs"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                list(map(str, command)),
                cwd=cwd or self.target,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    if self.command_output_enabled:
                        print(line, end="", flush=True)
                code = process.wait()
            except BaseException:
                process.terminate()
                process.wait()
                raise
        if code:
            raise SystemExit(code)

    @contextmanager
    def _temporary_instance(self):
        from plonex.services.runwsgi import RunWSGI

        auth = private_auth_directory(configured_auth_directory(self))
        log_path = self.var_folder / "log" / "upgrade.logs"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_root = self.target / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="upgrade-", dir=tmp_root) as temporary:
            instance = RunWSGI(
                target=self.target,
                name="upgrade",
                tmp_folder=Path(temporary),
                config_files=self.config_files,
                cli_options={
                    "http_address": "127.0.0.1",
                    "http_port": port,
                    "upgrade_tempfile_auth": True,
                    "environment_vars": self.options.get("environment_vars", {})
                    | {"UPGRADE_TEMPFILE_AUTH_DIR": str(auth)},
                },
            )
            instance._prepare_zope_runtime()
            for template in instance.pre_services or []:
                with template:
                    template.run()
            # Keep the normal logging configuration while directing the
            # temporary instance event log to the same upgrade log.
            ini = Path(temporary) / "etc/wsgi.ini"
            config = ini.read_text()
            config = config.replace(
                f"{instance.var_folder}/log/runwsgi-{port}.log",
                str(log_path),
            )
            ini.write_text(config)
            with log_path.open("a") as log:
                process = subprocess.Popen(
                    instance.command,
                    cwd=self.target,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    deadline = time.monotonic() + 120
                    while True:
                        if process.poll() is not None:
                            raise ValueError(
                                f"Temporary upgrade instance exited; see {log_path}"
                            )
                        try:
                            with socket.create_connection(
                                ("127.0.0.1", port), timeout=1
                            ):
                                break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise ValueError(
                                    f"Temporary upgrade instance did not start; "
                                    f"see {log_path}"
                                )
                            time.sleep(0.1)
                    yield f"http://127.0.0.1:{port}/"
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
