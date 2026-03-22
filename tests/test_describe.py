from .utils import PloneXTestCase
from .utils import temp_cwd
from pathlib import Path
from plonex.describe import DescribeService
from unittest import mock

import inspect


class TestDescribeService(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(DescribeService.__init__)
        self.assertListEqual(
            list(sig.parameters),
            [
                "self",
                "name",
                "target",
                "cli_options",
                "config_files",
                "describe_template",
                "generate_html",
                "browse_html",
            ],
        )

    def test_now_property(self):
        """Test that now returns a formatted datetime string"""
        with temp_cwd():
            svc = DescribeService()
            now = svc.now
            # Should be a string like "2026-03-21 12:34:56"
            self.assertRegex(now, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_developed_packages(self):
        """Test the developed_packages property with mocked InstallService"""
        with temp_cwd() as cwd:
            svc = DescribeService()
            with mock.patch("plonex.describe.InstallService") as MockInstall:
                MockInstall.return_value.__enter__ = mock.Mock(
                    return_value=MockInstall.return_value
                )
                MockInstall.return_value.__exit__ = mock.Mock(return_value=False)
                MockInstall.return_value.developed_packages_and_paths.return_value = {
                    "my.package → /path/to/my/package"
                }
                result = svc.developed_packages
            MockInstall.assert_called_once_with(target=cwd)
            self.assertEqual(result, ["my.package → /path/to/my/package"])

    def test_project_files(self):
        with temp_cwd() as cwd:
            (cwd / "etc" / "requirements.d").mkdir(parents=True)
            (cwd / "etc" / "constraints.d").mkdir(parents=True)
            requirement_fragment = cwd / "etc" / "requirements.d" / "010-extra.txt"
            constraint_fragment = cwd / "etc" / "constraints.d" / "010-extra.txt"
            requirement_fragment.write_text("foo\n")
            constraint_fragment.write_text("bar==1.0\n")
            svc = DescribeService()
            self.assertEqual(
                svc.project_files,
                [
                    ("Source configuration", cwd / "etc" / "plonex.yml"),
                    ("Source requirements", cwd / "etc" / "requirements.d"),
                    ("Source constraints", cwd / "etc" / "constraints.d"),
                    ("Compiled configuration", cwd / "var" / "plonex.yml"),
                    ("Compiled sources (gitman.yml)", cwd / "var" / "gitman.yml"),
                    ("Compiled requirements", cwd / "var" / "requirements.txt"),
                    ("Compiled constraints", cwd / "var" / "constraints.txt"),
                    (
                        "Supervisor configuration",
                        cwd / "tmp" / "supervisor" / "etc" / "supervisord.conf",
                    ),
                    (
                        "Markdown description",
                        cwd / "var" / "plonex_description" / "index.md",
                    ),
                    (
                        "HTML description",
                        cwd / "var" / "plonex_description" / "index.html",
                    ),
                    ("Requirement fragment 010-extra.txt", requirement_fragment),
                    ("Constraint fragment 010-extra.txt", constraint_fragment),
                ],
            )

    def test_project_file_groups(self):
        with temp_cwd() as cwd:
            (cwd / "etc" / "requirements.d").mkdir(parents=True)
            (cwd / "etc" / "constraints.d").mkdir(parents=True)
            requirement_fragment = cwd / "etc" / "requirements.d" / "010-extra.txt"
            constraint_fragment = cwd / "etc" / "constraints.d" / "010-extra.txt"
            requirement_fragment.write_text("foo\n")
            constraint_fragment.write_text("bar==1.0\n")
            svc = DescribeService()
            self.assertEqual(
                svc.project_file_groups,
                [
                    (
                        "Source Files",
                        [
                            (
                                "Requirements directory",
                                cwd / "etc" / "requirements.d",
                                [("010-extra.txt", requirement_fragment)],
                            ),
                            (
                                "Constraints directory",
                                cwd / "etc" / "constraints.d",
                                [("010-extra.txt", constraint_fragment)],
                            ),
                            ("Configuration", cwd / "etc" / "plonex.yml", []),
                        ],
                    ),
                    (
                        "Compiled Files",
                        [
                            ("Compiled configuration", cwd / "var" / "plonex.yml", []),
                            (
                                "Compiled sources (gitman.yml)",
                                cwd / "var" / "gitman.yml",
                                [],
                            ),
                            (
                                "Compiled requirements",
                                cwd / "var" / "requirements.txt",
                                [],
                            ),
                            (
                                "Compiled constraints",
                                cwd / "var" / "constraints.txt",
                                [],
                            ),
                        ],
                    ),
                    (
                        "Runtime Files",
                        [
                            (
                                "Supervisor configuration",
                                cwd / "tmp" / "supervisor" / "etc" / "supervisord.conf",
                                [],
                            ),
                        ],
                    ),
                    (
                        "Reports",
                        [
                            (
                                "Markdown description",
                                cwd / "var" / "plonex_description" / "index.md",
                                [],
                            ),
                            (
                                "HTML description",
                                cwd / "var" / "plonex_description" / "index.html",
                                [],
                            ),
                        ],
                    ),
                ],
            )

    def test_display_path(self):
        with temp_cwd() as cwd:
            svc = DescribeService()
            self.assertEqual(
                svc.display_path(cwd / "var" / "plonex.yml"), "var/plonex.yml"
            )
            self.assertEqual(
                svc.display_path(Path("/tmp/outside.txt")), "/tmp/outside.txt"
            )

    def test_display_source(self):
        with temp_cwd() as cwd:
            svc = DescribeService()
            self.assertEqual(
                svc.display_source(cwd / "var" / "plonex.yml"), "var/plonex.yml"
            )
            self.assertEqual(svc.display_source("etc/custom.txt"), "etc/custom.txt")
            self.assertEqual(
                svc.display_source(
                    "https://dist.plone.org/release/6.1.2/constraints.txt"
                ),
                "https://dist.plone.org/release/6.1.2/constraints.txt",
            )

    def test_supervisor_status(self):
        """Test the supervisor_status property with mocked Supervisor"""
        with temp_cwd() as cwd:
            svc = DescribeService()
            with mock.patch("plonex.describe.Supervisor") as MockSupervisor:
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.get_status.return_value = (
                    "Supervisord is not running"
                )
                result = svc.supervisor_status
            MockSupervisor.assert_called_once_with(target=cwd)
            self.assertEqual(result, "Supervisord is not running")

    def test_supervisor_graceful_interval(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "supervisor_graceful_interval: 2.5\n"
            )
            svc = DescribeService()
            self.assertEqual(svc.supervisor_graceful_interval, 2.5)

    def test_run(self):
        """Test that run() compiles, renders and prints the description"""
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "mykey: myvalue\n"
                "plone_version: 6.1.2\n"
                "supervisor_graceful_interval: 2.5\n"
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
                "profiles:\n"
                "  - profiles/base\n"
                "plonex_base_constraint: etc/custom-constraints.txt\n"
                "services:\n"
                "  - template:\n"
                "      run_for: describe\n"
            )
            (cwd / "etc" / "plonex.describe.yml").write_text("log_level: DEBUG\n")
            (cwd / "etc" / "requirements.d").mkdir()
            (cwd / "etc" / "requirements.d" / "010-extra.txt").write_text("foo\n")
            (cwd / "etc" / "constraints.d").mkdir()
            (cwd / "etc" / "constraints.d" / "010-extra.txt").write_text("bar==1.0\n")
            (cwd / "etc" / "custom-constraints.txt").write_text("foo==1.0\n")
            (cwd / "profiles" / "base" / "etc").mkdir(parents=True)
            (cwd / "profiles" / "base" / "etc" / "plonex.yml").write_text(
                "profile_option: true\n"
            )
            (cwd / "tmp" / "supervisor" / "etc").mkdir(parents=True)
            (cwd / "tmp" / "supervisor" / "etc" / "supervisord.conf").write_text(
                "[supervisord]\n"
            )
            developed_package_path = cwd / "src" / "my.package"
            developed_package_path.mkdir(parents=True)

            with (
                mock.patch(
                    "plonex.describe.InstallService.ensure_virtualenv",
                    return_value=None,
                ),
                mock.patch(
                    "plonex.describe.BaseService.execute_command",
                    side_effect=lambda command, cwd=None, stream_output=False: (
                        "Python 3.13.7\n"
                        if len(command) == 2 and str(command[1]) == "--version"
                        else ""
                    ),
                ),
                mock.patch("plonex.describe.Supervisor") as MockSupervisor,
                mock.patch("plonex.describe.Console") as MockConsole,
            ):
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.get_status.return_value = "not running"

                with DescribeService() as svc:
                    with mock.patch.object(
                        DescribeService,
                        "developed_packages",
                        new_callable=mock.PropertyMock,
                        return_value=[f"my.package → {developed_package_path}"],
                    ):
                        svc.run()

                self.assertTrue((cwd / "var" / "plonex.yml").exists())
                self.assertTrue((cwd / "var" / "gitman.yml").exists())
                self.assertTrue((cwd / "var" / "requirements.txt").exists())
                self.assertTrue((cwd / "var" / "constraints.txt").exists())
                rendered = (cwd / "var" / "plonex_description" / "index.md").read_text()
                self.assertIn(
                    f"[var/plonex.yml](file://{cwd / 'var' / 'plonex.yml'})",
                    rendered,
                )
                self.assertIn(
                    f"[var/gitman.yml](file://{cwd / 'var' / 'gitman.yml'})",
                    rendered,
                )
                self.assertIn(
                    f"[var/requirements.txt](file://{cwd / 'var' / 'requirements.txt'})",  # noqa: E501
                    rendered,
                )
                self.assertIn(
                    f"[var/constraints.txt](file://{cwd / 'var' / 'constraints.txt'})",
                    rendered,
                )
                self.assertIn(
                    f"[etc/plonex.yml](file://{cwd / 'etc' / 'plonex.yml'})",
                    rendered,
                )
                self.assertIn("**Plone Version**: `6.1.2`", rendered)
                self.assertIn("**Python Version**: `Python 3.13.7`", rendered)
                self.assertIn(
                    f"[.venv/bin/python](file://{cwd / '.venv' / 'bin' / 'python'})",
                    rendered,
                )
                self.assertIn(
                    "**Base Constraint**: `etc/custom-constraints.txt`",
                    rendered,
                )
                self.assertIn("**Supervisor Configuration**: `present`", rendered)
                self.assertIn(
                    "**Supervisor Graceful Interval**: `2.5s`",
                    rendered,
                )
                self.assertIn("**Sources Checkouts**: `1`", rendered)
                self.assertIn("- `profiles/base`", rendered)
                self.assertIn(
                    (
                        f"[etc/plonex.describe.yml](file://"
                        f"{cwd / 'etc' / 'plonex.describe.yml'})"
                    ),
                    rendered,
                )
                self.assertIn(
                    (
                        f"- **Requirements directory**: "
                        f"[etc/requirements.d](file://{cwd / 'etc' / 'requirements.d'})"
                    ),
                    rendered,
                )
                self.assertIn(
                    (
                        f"**010-extra.txt**: [etc/requirements.d/010-extra.txt]"
                        f"(file://{cwd / 'etc' / 'requirements.d' / '010-extra.txt'})"
                    ),
                    rendered,
                )
                self.assertIn(
                    (
                        f"- **Constraints directory**: "
                        f"[etc/constraints.d](file://{cwd / 'etc' / 'constraints.d'})"
                    ),
                    rendered,
                )
                self.assertIn(
                    (
                        f"**010-extra.txt**: [etc/constraints.d/010-extra.txt]"
                        f"(file://{cwd / 'etc' / 'constraints.d' / '010-extra.txt'})"
                    ),
                    rendered,
                )
                self.assertIn("- `template`", rendered)
                self.assertIn(
                    f"`my.package` → [src/my.package](file://{developed_package_path})",
                    rendered,
                )
                self.assertIn("### Source Files", rendered)
                self.assertIn("### Compiled Files", rendered)
                self.assertIn("### Runtime Files", rendered)
                self.assertIn("### Reports", rendered)
                self.assertIn("## Sources Status", rendered)
                self.assertIn(
                    "| Source | Folder | Repo URL | Health | Details |",
                    rendered,
                )
                self.assertIn(
                    "| `my.package` | `src/my.package` | `https://github.com/example/my.package.git` | ⚠ | not-git |",  # noqa: E501
                    rendered,
                )
                self.assertIn("Legend: ✓ clean, ⚠ warning, ✗ error", rendered)
                MockConsole.return_value.print.assert_called_once()

    def test_run_generates_html_and_browse(self):
        with temp_cwd() as cwd:
            (cwd / ".venv" / "bin").mkdir(parents=True)
            (cwd / ".venv" / "bin" / "activate").touch()
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("plone_version: 6.1.2\n")
            (cwd / "tmp" / "supervisor" / "etc").mkdir(parents=True)
            (cwd / "tmp" / "supervisor" / "etc" / "supervisord.conf").write_text(
                "[supervisord]\n"
            )

            with (
                mock.patch(
                    "plonex.describe.InstallService.ensure_virtualenv",
                    return_value=None,
                ),
                mock.patch(
                    "plonex.describe.BaseService.execute_command",
                    side_effect=lambda command, cwd=None, stream_output=False: (
                        "Python 3.13.7\n"
                        if len(command) == 2 and str(command[1]) == "--version"
                        else ""
                    ),
                ),
                mock.patch("plonex.describe.Supervisor") as MockSupervisor,
                mock.patch("plonex.describe.Console") as MockConsole,
                mock.patch("plonex.describe.webbrowser.open") as mock_open,
            ):
                MockSupervisor.return_value.__enter__ = mock.Mock(
                    return_value=MockSupervisor.return_value
                )
                MockSupervisor.return_value.__exit__ = mock.Mock(return_value=False)
                MockSupervisor.return_value.get_status.return_value = "not running"

                with DescribeService(generate_html=True, browse_html=True) as svc:
                    svc.run()

                self.assertTrue(
                    (cwd / "var" / "plonex_description" / "index.md").exists()
                )
                MockConsole.assert_called_once_with(record=True)
                MockConsole.return_value.save_html.assert_called_once_with(
                    cwd / "var" / "plonex_description" / "index.html"
                )
                mock_open.assert_called_once_with(
                    (cwd / "var" / "plonex_description" / "index.html")
                    .resolve()
                    .as_uri()
                )
