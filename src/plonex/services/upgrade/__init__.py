from dataclasses import dataclass
from pathlib import Path
from plonex.base import BaseService
from urllib.parse import urlparse

import os


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
        from plonex.files import read_only
        from plonex.services.runwsgi import RunWSGI

        upgrade = self.virtualenv_dir / "bin/upgrade"
        if not upgrade.is_file():
            raise ValueError(
                "The upgrade executable is missing. "
                "Install collective.ftw.upgrade in the project."
            )
        url = self.options.get("upgrade_url") or os.environ.get("UPGRADE_ZOPE_URL")
        if not url:
            with read_only():
                port = RunWSGI(target=self.target).options["http_port"]
            url = f"http://127.0.0.1:{port}/"
        parsed = urlparse(str(url))
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Upgrade URL must be an HTTP(S) URL without credentials")
        values = {"UPGRADE_ZOPE_URL": str(url)}
        if self.options.get("upgrade_tempfile_auth"):
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
