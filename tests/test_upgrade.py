from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.services.upgrade import UpgradeService
from unittest import mock

import inspect


class TestUpgradeService(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(UpgradeService.__init__)
        self.assertListEqual(
            list(sig.parameters),
            ["self", "name", "target", "cli_options", "config_files"],
        )

    def test_run(self):
        """Test that run() calls run_command with the right upgrade commands"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / ".venv" / "bin" / "upgrade").touch()
            with UpgradeService(cli_options={"upgrade_tempfile_auth": True}) as svc:
                with mock.patch.object(svc, "run_command") as mock_run:
                    svc.run()
                self.assertEqual(mock_run.call_count, 2)
                first_call_args = mock_run.call_args_list[0][0][0]
                self.assertIn("upgrade", str(first_call_args[0]))
                self.assertIn("plone_upgrade", first_call_args[1])


def test_upgrade_auth_directory_rejects_symlinks_and_broad_permissions(tmp_path):
    from plonex.services.upgrade import private_auth_directory

    import pytest

    directory = tmp_path / "auth"
    directory.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="private"):
        private_auth_directory(directory)
    directory.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(directory)
    with pytest.raises(ValueError, match="symlink"):
        private_auth_directory(link)


def test_upgrade_passes_url_and_private_auth_only_for_subprocess(tmp_path, monkeypatch):
    import os

    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("upgrade_tempfile_auth: true\n")
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/activate").touch()
    (tmp_path / ".venv/bin/upgrade").touch()
    monkeypatch.delenv("UPGRADE_ZOPE_URL", raising=False)
    monkeypatch.delenv("UPGRADE_TEMPFILE_AUTH_DIR", raising=False)
    seen = []
    with UpgradeService(
        target=tmp_path, cli_options={"upgrade_url": "http://127.0.0.1:8000/"}
    ) as service:
        with mock.patch.object(
            service,
            "run_command",
            side_effect=lambda command: seen.append(
                (
                    os.environ.get("UPGRADE_ZOPE_URL"),
                    os.environ.get("UPGRADE_TEMPFILE_AUTH_DIR"),
                )
            ),
        ):
            service.run()
    assert len(seen) == 2
    assert seen[0][0] == "http://127.0.0.1:8000/"
    assert seen[0][1] == str(tmp_path / "var/ftw.upgrade-authentication")
    assert "UPGRADE_ZOPE_URL" not in os.environ
    assert "UPGRADE_TEMPFILE_AUTH_DIR" not in os.environ


def test_upgrade_failure_restores_previous_process_environment(tmp_path, monkeypatch):
    import os
    import pytest

    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("upgrade_tempfile_auth: true\n")
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/activate").touch()
    (tmp_path / ".venv/bin/upgrade").touch()
    monkeypatch.setenv("UPGRADE_ZOPE_URL", "http://127.0.0.1:1234/")
    monkeypatch.delenv("UPGRADE_TEMPFILE_AUTH_DIR", raising=False)
    with UpgradeService(
        target=tmp_path, cli_options={"upgrade_url": "http://127.0.0.1:8000/"}
    ) as service:
        with mock.patch.object(
            service, "run_command", side_effect=RuntimeError("failed")
        ):
            with pytest.raises(RuntimeError, match="failed"):
                service.run()
    assert os.environ["UPGRADE_ZOPE_URL"] == "http://127.0.0.1:1234/"
    assert "UPGRADE_TEMPFILE_AUTH_DIR" not in os.environ


def test_upgrade_ignores_unrelated_ambient_auth_directory_when_opted_in(
    tmp_path, monkeypatch
):
    import os

    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("upgrade_tempfile_auth: true\n")
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/activate").touch()
    (tmp_path / ".venv/bin/upgrade").touch()
    monkeypatch.setenv("UPGRADE_TEMPFILE_AUTH_DIR", "/unrelated/ambient")
    seen = []
    with UpgradeService(target=tmp_path) as service:
        with mock.patch.object(
            service,
            "run_command",
            side_effect=lambda command: seen.append(
                os.environ["UPGRADE_TEMPFILE_AUTH_DIR"]
            ),
        ):
            service.run()
    assert seen == [str(tmp_path / "var/ftw.upgrade-authentication")] * 2
    assert os.environ["UPGRADE_TEMPFILE_AUTH_DIR"] == "/unrelated/ambient"
