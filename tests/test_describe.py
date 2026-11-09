from .utils import PloneXTestCase
from .utils import temp_cwd
from pathlib import Path
from plonex.services.describe import DescribeService
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
                "section",
                "output_format",
                "key",
                "inspect_command",
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
            with mock.patch("plonex.services.describe.InstallService") as MockInstall:
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
                    "https://dist.plone.org/release/6.2.0/constraints.txt"
                ),
                "https://dist.plone.org/release/6.2.0/constraints.txt",
            )

    def test_context_honors_var_folder_option(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("var_folder: custom-var\n")
            with DescribeService() as svc:
                self.assertEqual(svc.var_folder, cwd / "custom-var")
                self.assertEqual(
                    svc.description_path,
                    cwd / "custom-var" / "plonex_description" / "index.md",
                )

    def test_supervisor_status_is_a_silent_read_only_query(self):
        with temp_cwd() as cwd:
            service = DescribeService()
            self.assertEqual(service.supervisor_status, "Supervisor is not configured")
            configuration = cwd / "tmp" / "supervisor" / "etc" / "supervisord.conf"
            configuration.parent.mkdir(parents=True)
            configuration.write_text("[supervisorctl]\n")
            self.assertEqual(
                service.supervisor_status, "supervisorctl is not installed"
            )
            control = cwd / ".venv" / "bin" / "supervisorctl"
            control.parent.mkdir(parents=True)
            control.touch()
            with mock.patch.object(
                service, "execute_command", return_value="worker RUNNING pid 12\n"
            ) as execute:
                self.assertEqual(service.supervisor_status, "worker RUNNING pid 12")
            execute.assert_called_once_with(
                [control, "-c", configuration, "status"], capture_output=True
            )

    def test_supervisor_graceful_interval(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "supervisor_graceful_interval: 2.5\n"
            )
            svc = DescribeService()
            self.assertEqual(svc.supervisor_graceful_interval, 2.5)

    def test_run_preserves_input_files_and_exports_fragment_origins(self):
        import json

        with temp_cwd() as cwd:
            etc = cwd / "etc"
            (etc / "requirements.d").mkdir(parents=True)
            (etc / "constraints.d").mkdir()
            configuration = etc / "plonex.yml"
            configuration.write_text("http_port: 9000\n")
            requirement = etc / "requirements.d" / "010-extra.txt"
            requirement.write_text("Demo.Pkg>=1\n")
            (etc / "constraints.d" / "010-pins.txt").write_text("Demo.Pkg==1.0\n")
            with DescribeService(output_format="html") as service:
                service.run()
            payload = json.loads((service.describe_folder / "index.json").read_text())
            dependencies = next(
                section
                for section in payload["sections"]
                if section["key"] == "dependencies"
            )
            self.assertIn(
                (
                    "demo-pkg",
                    "demo-pkg>=1",
                    "requirements",
                    "etc/requirements.d/010-extra.txt",
                ),
                [tuple(row) for row in dependencies["rows"]],
            )
            self.assertIn(
                requirement.as_uri(), service.description_html_path.read_text()
            )
            self.assertEqual(configuration.read_text(), "http_port: 9000\n")
            self.assertFalse((cwd / "var" / "constraints.txt").exists())
            self.assertFalse((cwd / ".venv").exists())

    def test_run_generates_html_and_browse(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("{}\n")
            with mock.patch("plonex.services.describe.webbrowser.open") as browser:
                with DescribeService(
                    generate_html=True, browse_html=True, output_format="html"
                ) as service:
                    service.run()
            self.assertTrue(service.description_html_path.is_file())
            self.assertIn("<nav", service.description_html_path.read_text())
            browser.assert_called_once_with(service.description_html_path.as_uri())
