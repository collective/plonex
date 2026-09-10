"""Tests for the EditService."""

from pathlib import Path
from plonex.services.edit import EditService
from tests.utils import PloneXTestCase
from tests.utils import temp_cwd
from unittest import mock

import inspect
import os


class TestEditService(PloneXTestCase):
    """Test cases for EditService."""

    def test_init_signature(self):
        """Test that EditService has the expected signature."""
        sig = inspect.signature(EditService.__init__)
        self.assertListEqual(
            list(sig.parameters),
            ["self", "name", "target", "cli_options", "config_files", "open_all"],
        )

    def test_discover_config_files_empty_project(self):
        """Test discovering config files in an empty project."""
        with temp_cwd():
            svc = EditService()
            files = svc.discover_config_files()
            self.assertEqual(files, [])

    def test_discover_config_files_with_plonex_yml(self):
        """Test discovering plonex.yml."""
        with temp_cwd():
            etc_folder = Path("etc")
            etc_folder.mkdir()
            (etc_folder / "plonex.yml").write_text("---\n")

            with EditService() as svc:
                files = svc.discover_config_files()

            self.assertEqual(len(files), 1)
            self.assertIn(etc_folder / "plonex.yml", files)

    def test_discover_config_files_with_service_specific_yml(self):
        """Test discovering service-specific plonex-*.yml files."""
        with temp_cwd():
            etc_folder = Path("etc")
            etc_folder.mkdir()
            (etc_folder / "plonex.yml").write_text("---\n")
            (etc_folder / "plonex.runwsgi.yml").write_text("---\n")
            (etc_folder / "plonex.supervisor.yml").write_text("---\n")

            with EditService() as svc:
                files = svc.discover_config_files()

            self.assertEqual(len(files), 3)
            self.assertIn(etc_folder / "plonex.yml", files)
            self.assertIn(etc_folder / "plonex.runwsgi.yml", files)
            self.assertIn(etc_folder / "plonex.supervisor.yml", files)

    def test_discover_config_files_with_requirements(self):
        """Test discovering requirements.d files."""
        with temp_cwd() as cwd:
            etc_folder = cwd / "etc"
            (etc_folder / "requirements.d").mkdir(parents=True)
            (etc_folder / "requirements.d" / "010-custom.txt").write_text("Plone\n")
            (etc_folder / "requirements.d" / "020-more.txt").write_text("ZEO\n")

            with EditService() as svc:
                files = svc.discover_config_files()

            self.assertEqual(len(files), 2)
            self.assertIn(etc_folder / "requirements.d" / "010-custom.txt", files)
            self.assertIn(etc_folder / "requirements.d" / "020-more.txt", files)

    def test_discover_config_files_with_constraints(self):
        """Test discovering constraints.d files."""
        with temp_cwd() as cwd:
            etc_folder = cwd / "etc"
            (etc_folder / "constraints.d").mkdir(parents=True)
            (etc_folder / "constraints.d" / "010-custom.txt").write_text(
                "Plone==6.0.0\n"
            )

            svc = EditService()
            files = svc.discover_config_files()

            self.assertEqual(len(files), 1)
            self.assertIn(etc_folder / "constraints.d" / "010-custom.txt", files)

    def test_discover_config_files_with_root_config(self):
        """Test discovering root-level configuration files."""
        with temp_cwd() as cwd:
            Path("pyproject.toml").write_text("[project]\nname = 'test'\n")
            Path("Makefile").write_text("test:\n\techo test\n")

            svc = EditService()
            files = svc.discover_config_files()

            self.assertEqual(len(files), 2)
            self.assertIn(cwd / "pyproject.toml", files)
            self.assertIn(cwd / "Makefile", files)

    def test_discover_config_files_are_logically_sorted(self):
        """Test that discovered files are logically sorted."""
        with temp_cwd():
            etc_folder = Path("etc")
            (etc_folder / "requirements.d").mkdir(parents=True)
            (etc_folder / "constraints.d").mkdir(parents=True)

            # Create files out of alphabetical order
            (etc_folder / "plonex.zzz.yml").write_text("---\n")
            (etc_folder / "plonex.yml").write_text("---\n")
            (etc_folder / "plonex.aaa.yml").write_text("---\n")

            with EditService() as svc:
                files = svc.discover_config_files()

            expected = [
                # Default file
                etc_folder / "plonex.yml",
                # Overrides sorted alphabetically
                etc_folder / "plonex.aaa.yml",
                etc_folder / "plonex.zzz.yml",
            ]
            self.assertListEqual(files, expected)

    def test_resolve_editor_cli_option_highest_precedence(self):
        """Test that CLI --editor option has highest precedence."""
        with temp_cwd():
            svc = EditService(cli_options={"editor": "vim"})
            editor = svc.resolve_editor()
            self.assertEqual(editor, "vim")

    def test_resolve_editor_config_option_precedence(self):
        """Test that plonex.yml options.editor has second precedence."""
        with temp_cwd() as cwd:
            # Create plonex.yml with editor option
            etc_folder = cwd / "etc"
            etc_folder.mkdir()
            (etc_folder / "plonex.yml").write_text("editor: nano\n")

            svc = EditService()
            editor = svc.resolve_editor()
            self.assertEqual(editor, "nano")

    def test_resolve_editor_env_var_precedence(self):
        """Test that $EDITOR env var has third precedence."""
        with temp_cwd():
            # Temporarily set EDITOR env var
            original_editor = os.environ.get("EDITOR")
            try:
                os.environ["EDITOR"] = "emacs"
                svc = EditService()
                editor = svc.resolve_editor()
                self.assertEqual(editor, "emacs")
            finally:
                if original_editor:
                    os.environ["EDITOR"] = original_editor
                else:
                    os.environ.pop("EDITOR", None)

    def test_resolve_editor_fallback_to_nano(self):
        """Test that editor falls back to nano."""
        with temp_cwd():
            # Ensure no EDITOR env var
            original_editor = os.environ.pop("EDITOR", None)
            try:
                svc = EditService()
                editor = svc.resolve_editor()
                self.assertEqual(editor, "nano")
            finally:
                if original_editor:
                    os.environ["EDITOR"] = original_editor

    def test_resolve_editor_cli_overrides_config(self):
        """Test that CLI --editor overrides plonex.yml option."""
        with temp_cwd() as cwd:
            etc_folder = cwd / "etc"
            etc_folder.mkdir()
            (etc_folder / "plonex.yml").write_text("editor: nano\n")

            svc = EditService(cli_options={"editor": "vim"})
            editor = svc.resolve_editor()
            self.assertEqual(editor, "vim")

    def test_resolve_editor_cli_overrides_env_var(self):
        """Test that CLI --editor overrides $EDITOR env var."""
        with temp_cwd():
            original_editor = os.environ.get("EDITOR")
            try:
                os.environ["EDITOR"] = "emacs"
                svc = EditService(cli_options={"editor": "code"})
                editor = svc.resolve_editor()
                self.assertEqual(editor, "code")
            finally:
                if original_editor:
                    os.environ["EDITOR"] = original_editor
                else:
                    os.environ.pop("EDITOR", None)

    def test_name_is_edit(self):
        """Test that the service name is 'edit'."""
        with temp_cwd():
            svc = EditService()
            self.assertEqual(svc.name, "edit")

    def test_select_files_interactive_returns_empty_when_no_files(self):
        """Test that interactive selection returns empty list when no files exist."""
        with temp_cwd():
            with EditService() as svc:
                result = svc.select_files_interactive([])
                self.assertEqual(result, [])

    def test_select_files_interactive_with_mock_input(self):
        """Test interactive file selection with mocked user input."""
        with temp_cwd() as cwd:
            file1 = cwd / "etc" / "plonex.yml"
            file2 = cwd / "etc" / "plonex-runwsgi.yml"
            file1.parent.mkdir(parents=True)
            file1.write_text("---\n")
            file2.write_text("---\n")

            svc = EditService()
            files = [file1, file2]

            # Mock user selection of both files
            with mock.patch("plonex.services.edit.Prompt.ask", return_value="1,2"):
                result = svc.select_files_interactive(files)

            self.assertEqual(len(result), 2)
            self.assertIn(file1, result)
            self.assertIn(file2, result)

    def test_select_files_interactive_with_single_selection(self):
        """Test interactive file selection with single file selection."""
        with temp_cwd() as cwd:
            file1 = cwd / "etc" / "plonex.yml"
            file2 = cwd / "etc" / "plonex-runwsgi.yml"
            file1.parent.mkdir(parents=True)
            file1.write_text("---\n")
            file2.write_text("---\n")

            svc = EditService()
            files = [file1, file2]

            # Mock user selection of only file 1
            with mock.patch("plonex.services.edit.Prompt.ask", return_value="1"):
                result = svc.select_files_interactive(files)

            self.assertEqual(len(result), 1)
            self.assertIn(file1, result)

    def test_select_files_interactive_invalid_input_returns_empty(self):
        """Test that invalid input returns empty list."""
        with temp_cwd() as cwd:
            file1 = cwd / "etc" / "plonex.yml"
            file1.parent.mkdir(parents=True)
            file1.write_text("---\n")

            svc = EditService()
            files = [file1]

            # Mock user input with invalid value
            with mock.patch("plonex.services.edit.Prompt.ask", return_value="invalid"):
                result = svc.select_files_interactive(files)

            self.assertEqual(result, [])

    def test_run_with_open_all_flag(self):
        """Test that run() uses all files when open_all is True."""
        with temp_cwd():
            etc_folder = Path("etc")
            etc_folder.mkdir()
            (etc_folder / "plonex.yml").write_text("---\n")

            with EditService(open_all=True, cli_options={"editor": "echo"}) as svc:
                with mock.patch.object(svc, "execute_command") as mock_execute:
                    mock_execute.return_value = ""
                    svc.run()

            # Should call execute_command with echo and the file
            mock_execute.assert_called_once()
            args, kwargs = mock_execute.call_args
            command = args[0]
            self.assertEqual(command[0], "echo")
            self.assertIn(str(etc_folder / "plonex.yml"), command)
            self.assertTrue(kwargs.get("stream_output"))

    def test_run_with_interactive_selection(self):
        """Test that run() uses interactive selection when open_all is False."""
        with temp_cwd():
            etc_folder = Path("etc")
            etc_folder.mkdir()
            file1 = etc_folder / "plonex.yml"
            file1.write_text("---\n")

            with EditService(open_all=False, cli_options={"editor": "echo"}) as svc:
                with mock.patch.object(svc, "select_files_interactive") as mock_select:
                    with mock.patch.object(svc, "execute_command") as mock_execute:
                        mock_select.return_value = [file1]
                        mock_execute.return_value = ""
                        svc.run()

            # Should call select_files_interactive
            mock_select.assert_called_once()
            # Should call execute_command with selected files
            mock_execute.assert_called_once()

    def test_run_with_no_config_files_found(self):
        """Test that run() handles case when no config files are found."""
        with temp_cwd():
            with EditService() as svc:
                with mock.patch.object(svc, "execute_command") as mock_execute:
                    svc.run()

            # Should not execute any command
            mock_execute.assert_not_called()
