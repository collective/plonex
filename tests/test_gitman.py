from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.sources import SourcesService
from unittest import mock


class TestSourcesService(PloneXTestCase):

    def test_compile_config_writes_var_gitman_file(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
            )
            with SourcesService() as svc:
                target = svc.compile_config()
            self.assertEqual(target, cwd / "var" / "gitman.yml")
            rendered = (cwd / "var" / "gitman.yml").read_text()
            self.assertIn(f"location: {cwd / 'src'}", rendered)
            self.assertIn("- name: my.package", rendered)
            self.assertIn("type: git", rendered)

    def test_run_update_force_without_confirmation(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(svc, "ask_for_value", return_value="n"),
                    mock.patch.object(svc, "run_command") as mock_run,
                ):
                    svc.run_update(force=True, assume_yes=False)
            mock_run.assert_not_called()

    def test_run_update_uses_gitman_file_folder_as_cwd(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
            )
            with SourcesService() as svc:
                with mock.patch.object(svc, "run_command") as mock_run:
                    svc.run_update()
            mock_run.assert_called_once_with(["gitman", "update"], cwd=cwd / "var")

    def test_run_update_creates_checkout_root(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
            )
            self.assertFalse((cwd / "src").exists())
            with SourcesService() as svc:
                with mock.patch.object(svc, "run_command"):
                    svc.run_update()
            self.assertTrue((cwd / "src").exists())

    def test_run_update_invalid_empty_source_name_does_not_invoke_gitman(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "  '':\n"
                "    repo: https://github.com/example/invalid.git\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(svc, "run_command") as mock_run,
                    mock.patch.object(svc.logger, "error") as mock_error,
                ):
                    svc.run_update()
            mock_run.assert_not_called()
            self.assertTrue(
                any(
                    "Invalid source name" in str(call)
                    for call in mock_error.call_args_list
                )
            )

    def test_run_update_missing_repo_does_not_invoke_gitman(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n" "    my.package:\n" "      rev: main\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(svc, "run_command") as mock_run,
                    mock.patch.object(svc.logger, "error") as mock_error,
                ):
                    svc.run_update()
            mock_run.assert_not_called()
            self.assertTrue(
                any(
                    "missing non-empty 'repo'" in str(call)
                    for call in mock_error.call_args_list
                )
            )

    def test_run_show_tainted(self):
        with temp_cwd() as cwd:
            checkout = cwd / "src" / "my.package"
            (cwd / "etc").mkdir()
            checkout.mkdir(parents=True)
            (checkout / ".git").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "execute_command", return_value=" M setup.py\n"
                    ),
                    mock.patch("plonex.sources.Console") as MockConsole,
                ):
                    svc.run_show_tainted()
            MockConsole.return_value.print.assert_any_call("Tainted checkouts:")
            MockConsole.return_value.print.assert_any_call("- src/my.package")

    def test_missing_checkouts(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    present.package:\n"
                "      repo: https://github.com/example/present.package.git\n"
                "    missing.package:\n"
                "      repo: https://github.com/example/missing.package.git\n"
            )
            present = cwd / "src" / "present.package"
            present.mkdir(parents=True)
            with SourcesService() as svc:
                missing = svc.missing_checkouts()
            self.assertEqual(
                missing, {"missing.package": cwd / "src" / "missing.package"}
            )

    def test_run_clone_missing_clones_repo_and_checks_out_rev(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    missing.package:\n"
                "      repo: https://github.com/example/missing.package.git\n"
                "      rev: main\n"
            )
            with SourcesService() as svc:
                with mock.patch.object(svc, "run_command") as mock_run:
                    svc.run_clone_missing(assume_yes=True)
            mock_run.assert_any_call(
                [
                    "git",
                    "clone",
                    "https://github.com/example/missing.package.git",
                    str(cwd / "src" / "missing.package"),
                ]
            )
            mock_run.assert_any_call(
                ["git", "-C", str(cwd / "src" / "missing.package"), "checkout", "main"]
            )

    def test_run_clone_missing_requires_confirmation(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    missing.package:\n"
                "      repo: https://github.com/example/missing.package.git\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "ask_for_value", return_value="n"
                    ) as mock_ask,
                    mock.patch.object(svc, "run_command") as mock_run,
                ):
                    svc.run_clone_missing(assume_yes=False)
            mock_ask.assert_called_once()
            mock_run.assert_not_called()

    def test_run_list_shows_unmanaged_suggestion(self):
        with temp_cwd() as cwd:
            managed = cwd / "src" / "managed.package"
            unmanaged = cwd / "src" / "extra.package"
            managed.mkdir(parents=True)
            unmanaged.mkdir(parents=True)
            (managed / ".git").mkdir()
            (unmanaged / ".git").mkdir()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    managed.package:\n"
                "      repo: https://github.com/example/managed.package.git\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc,
                        "_has_modifications",
                        side_effect=lambda path: path == managed,
                    ),
                    mock.patch.object(
                        svc,
                        "_git_current_branch",
                        return_value="main",
                    ),
                    mock.patch.object(
                        svc,
                        "_git_remote_url",
                        side_effect=lambda path: (
                            "https://github.com/example/managed.package.git"
                            if path == managed
                            else "https://github.com/example/extra.package.git"
                        ),
                    ),
                    mock.patch("plonex.sources.Console") as MockConsole,
                ):
                    svc.run_list()
            rendered = "\n".join(
                str(call.args[0])
                for call in MockConsole.return_value.print.call_args_list
            )
            self.assertIn("Unmanaged existing checkouts found:", rendered)
            self.assertIn("Suggested configuration to add to etc/plonex.yml:", rendered)
            self.assertIn("extra.package", rendered)

    def test_run_suggest_existing_without_unmanaged(self):
        with temp_cwd() as cwd:
            managed = cwd / "src" / "managed.package"
            managed.mkdir(parents=True)
            (managed / ".git").mkdir()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    managed.package:\n"
                "      repo: https://github.com/example/managed.package.git\n"
            )
            with SourcesService() as svc:
                with mock.patch.object(svc, "print") as mock_print:
                    svc.run_suggest_existing()
            mock_print.assert_called_once_with("No unmanaged existing checkouts found.")

    def test_run_suggest_existing_apply(self):
        with temp_cwd() as cwd:
            unmanaged = cwd / "src" / "extra.package"
            unmanaged.mkdir(parents=True)
            (unmanaged / ".git").mkdir()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("log_level: info\n")
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "existing_checkouts", return_value=[unmanaged]
                    ),
                    mock.patch.object(
                        svc,
                        "_git_remote_url",
                        return_value="https://github.com/example/extra.package.git",
                    ),
                    mock.patch.object(svc, "_git_revision", return_value="main"),
                ):
                    svc.run_suggest_existing(apply=True)
            result = (cwd / "etc" / "plonex.yml").read_text()
            self.assertIn("sources:", result)
            self.assertIn("extra.package:", result)
            self.assertIn("repo: https://github.com/example/extra.package.git", result)

    def test_run_suggest_existing_apply_keeps_existing_indent(self):
        with temp_cwd() as cwd:
            unmanaged = cwd / "src" / "extra.package"
            unmanaged.mkdir(parents=True)
            (unmanaged / ".git").mkdir()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "log_level: info\n"
                "environment_vars:\n"
                "    PYTHONWARNINGS: ignore:::pkg_resources\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "existing_checkouts", return_value=[unmanaged]
                    ),
                    mock.patch.object(
                        svc,
                        "_git_remote_url",
                        return_value="https://github.com/example/extra.package.git",
                    ),
                    mock.patch.object(svc, "_git_revision", return_value="main"),
                ):
                    svc.run_suggest_existing(apply=True)
            result = (cwd / "etc" / "plonex.yml").read_text()
            self.assertIn("\nsources:\n", result)
            self.assertIn(
                "repo: https://github.com/example/extra.package.git",
                result,
            )

    def test_run_suggest_existing_apply_local(self):
        with temp_cwd() as cwd:
            unmanaged = cwd / "src" / "extra.package"
            unmanaged.mkdir(parents=True)
            (unmanaged / ".git").mkdir()
            (cwd / "etc").mkdir()
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "existing_checkouts", return_value=[unmanaged]
                    ),
                    mock.patch.object(
                        svc,
                        "_git_remote_url",
                        return_value="https://github.com/example/extra.package.git",
                    ),
                    mock.patch.object(svc, "_git_revision", return_value="main"),
                ):
                    svc.run_suggest_existing(apply_local=True)
            local_file = cwd / "etc" / "plonex-sources.local.yml"
            self.assertTrue(local_file.exists())
            rendered = local_file.read_text()
            self.assertIn("sources:", rendered)
            self.assertIn("extra.package:", rendered)

    def test_run_suggest_existing_apply_profile(self):
        with temp_cwd() as cwd:
            unmanaged = cwd / "src" / "extra.package"
            unmanaged.mkdir(parents=True)
            (unmanaged / ".git").mkdir()
            profile_dir = cwd / "profiles" / "myprofile"
            (profile_dir / "etc").mkdir(parents=True)
            (cwd / "etc").mkdir(exist_ok=True)
            (cwd / "etc" / "plonex.yml").write_text(
                "profiles:\n  - profiles/myprofile\n"
            )
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "existing_checkouts", return_value=[unmanaged]
                    ),
                    mock.patch.object(
                        svc,
                        "_git_remote_url",
                        return_value="https://github.com/example/extra.package.git",
                    ),
                    mock.patch.object(svc, "_git_revision", return_value="main"),
                ):
                    svc.run_suggest_existing(apply_profile=True)
            profile_file = profile_dir / "etc" / "plonex.yml"
            self.assertTrue(profile_file.exists())
            rendered = profile_file.read_text()
            self.assertIn("sources:", rendered)
            self.assertIn("extra.package:", rendered)

    def test_run_suggest_existing_apply_profile_no_profiles_logs_error(self):
        with temp_cwd() as cwd:
            unmanaged = cwd / "src" / "extra.package"
            unmanaged.mkdir(parents=True)
            (unmanaged / ".git").mkdir()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("log_level: info\n")
            with SourcesService() as svc:
                with (
                    mock.patch.object(
                        svc, "existing_checkouts", return_value=[unmanaged]
                    ),
                    mock.patch.object(svc.logger, "error") as mock_error,
                ):
                    svc.run_suggest_existing(apply_profile=True)
            mock_error.assert_called_once()
            self.assertIn("No profiles", str(mock_error.call_args))

    def test_run_suggest_existing_apply_both_logs_error(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("log_level: info\n")
            with SourcesService() as svc:
                with mock.patch.object(svc.logger, "error") as mock_error:
                    svc.run_suggest_existing(apply=True, apply_local=True)
            mock_error.assert_called_once()

    def test_run_suggest_existing_apply_all_three_logs_error(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("log_level: info\n")
            with SourcesService() as svc:
                with mock.patch.object(svc.logger, "error") as mock_error:
                    svc.run_suggest_existing(
                        apply=True,
                        apply_local=True,
                        apply_profile=True,
                    )
            mock_error.assert_called_once()

    def test_render_suggestions_yaml_uses_path_when_not_in_root(self):
        with temp_cwd() as cwd:
            (cwd / "src").mkdir(parents=True)
            nested = cwd / "src" / "nested" / "extra.package"
            nested.mkdir(parents=True)
            (nested / ".git").mkdir()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("sources: {}\n")
            with SourcesService() as svc:
                with (
                    mock.patch.object(svc, "existing_checkouts", return_value=[nested]),
                    mock.patch.object(
                        svc,
                        "_git_remote_url",
                        return_value="https://github.com/example/extra.package.git",
                    ),
                    mock.patch.object(svc, "_git_revision", return_value="main"),
                ):
                    rendered = svc.render_suggestions_yaml()
            self.assertIn("path: src/nested/extra.package", rendered)
            self.assertIn(
                "repo: https://github.com/example/extra.package.git", rendered
            )
            self.assertIn("rev: main", rendered)
