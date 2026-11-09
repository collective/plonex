from .utils import temp_cwd
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from plonex.base import BaseService
from plonex.cli import main
from plonex.cli.job_view import JobPresenter
from plonex.cli.parser import build_parser
from plonex.inspection import redact_tokens
from plonex.inspection import safe_value
from plonex.inspection import ServiceSnapshot
from plonex.presentation import MarkdownTable
from plonex.services.compile import CompileService
from plonex.services.install import InstallService
from plonex.services.invocation import ServiceInvocation
from plonex.services.registry import service_registry
from rich.console import Console
from rich.text import Text
from unittest import mock

import io
import json
import os
import sys
import unittest


class TestServiceInspection(unittest.TestCase):
    def setUp(self):
        self.target = self.enterContext(temp_cwd())
        (self.target / "etc").mkdir()
        (self.target / "etc" / "plonex.yml").write_text(
            (
                "http_port: 9000\nenvironment_vars:\n  INSPECTION_TEST: "
                "must-not-be-exported\n  API_TOKEN: private-token\naliases:\n  "
                "server: instance debug\n"
            )
        )

    def invocation(self, *tokens):
        args = build_parser(target=self.target).parse_args(tokens)
        return ServiceInvocation.from_args(args, self.target)

    def test_runtime_inspection_uses_real_service_defaults_and_cli_precedence(self):
        extra = self.target / "extra.yml"
        extra.write_text("http_port: 9001\nhttp_address: 192.0.2.1\n")
        invocation = self.invocation("server", "--config", str(extra), "--port", "9092")
        snapshot = ServiceSnapshot.capture(
            invocation.create(), parameters=invocation.parameters
        )
        self.assertEqual(snapshot.name, "fg")
        self.assertEqual(snapshot.service, "RunWSGI")
        self.assertEqual(snapshot.options["http_port"], 9092)
        self.assertEqual(snapshot.options["http_address"], "192.0.2.1")
        self.assertEqual(snapshot.options["debug_mode"], "on")
        self.assertEqual(snapshot.arguments["command"]["port"], 9092)
        self.assertIn(str(extra), snapshot.configuration_files)
        self.assertIn("etc/plonex.yml", snapshot.configuration_files)
        self.assertFalse((self.target / "tmp" / "fg" / "etc" / "zope.conf").exists())

    def test_runtime_host_override_is_used_by_wsgi_template(self):
        invocation = self.invocation("instance", "start", "--host", "127.0.0.1")
        service = invocation.create()
        template = service.pre_services[-1]
        self.assertIn("listen = 127.0.0.1:9000", template.render_template())

    def test_service_names_config_files_and_arguments_are_not_generic_base_defaults(
        self,
    ):
        (self.target / "etc" / "plonex-special.yml").write_text("http_port: 9093\n")
        cases = [
            (["instance", "start", "--name", "special"], "RunWSGI", "special"),
            (["instance", "run", "task.py"], "ZConsole", "zconsole"),
            (["instance", "run", "task.py"], "ZConsole", "zconsole"),
            (["dependencies", "sync"], "InstallService", "install"),
            (
                ["test", "pytest", "my.package", "-k", "login"],
                "PytestService",
                "pytest",
            ),
        ]
        for command, implementation, name in cases:
            with self.subTest(command=command):
                invocation = self.invocation(*command)
                snapshot = ServiceSnapshot.capture(invocation.create())
                self.assertEqual(snapshot.service, implementation)
                self.assertEqual(snapshot.name, name)
                if name == "special":
                    self.assertEqual(snapshot.options["http_port"], 9093)
                if name == "install":
                    self.assertIn("plonex_base_constraint", snapshot.options)

    def test_cli_preview_does_not_run_services_install_packages_or_export_environment(
        self,
    ):
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "plonex",
                    "options",
                    "--markdown",
                    "instance",
                    "debug",
                    "--port",
                    "9094",
                ],
            ),
            mock.patch.object(
                BaseService, "execute_command", side_effect=AssertionError("executed")
            ),
            mock.patch.object(
                InstallService,
                "ensure_virtualenv",
                side_effect=AssertionError("installed"),
            ),
            mock.patch.dict(os.environ, {}, clear=False),
            redirect_stdout(io.StringIO()) as output,
        ):
            os.environ.pop("INSPECTION_TEST", None)
            main()
            self.assertNotIn("INSPECTION_TEST", os.environ)
        self.assertIn("| http_port | 9094 |", output.getvalue())
        self.assertIn("RunWSGI", output.getvalue())
        self.assertNotIn("private-token", output.getvalue())
        self.assertFalse((self.target / "tmp" / "fg" / "etc" / "zope.conf").exists())

    def test_options_uses_explicit_target_even_when_launched_elsewhere(self):
        with (
            temp_cwd(),
            mock.patch.object(
                sys,
                "argv",
                [
                    "plonex",
                    "--target",
                    str(self.target),
                    "options",
                    "--markdown",
                    "instance",
                    "debug",
                ],
            ),
            redirect_stdout(io.StringIO()) as output,
        ):
            main()
        self.assertIn("| http_port | 9000 |", output.getvalue())

    def test_snapshot_is_atomic_private_and_round_trips_paths_and_redactions(self):
        invocation = self.invocation("instance", "debug", "--port", "9095")
        snapshot = ServiceSnapshot.capture(invocation.create())
        path = self.target / "snapshot.json"
        snapshot.write(path)
        restored = ServiceSnapshot.read(path)
        self.assertEqual(restored, snapshot)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            restored.options["environment_vars"]["API_TOKEN"], "[redacted]"
        )
        self.assertNotIn("private-token", path.read_text())

    def test_registry_is_shared_with_dependency_services(self):
        from plonex.cli.dependencies import _SERVICE_REGISTRY

        self.assertIs(_SERVICE_REGISTRY, service_registry.services)
        self.assertIs(service_registry.get("fg"), service_registry.get("runwsgi"))
        with self.assertRaisesRegex(ValueError, "No service options"):
            service_registry.get("shell")

    def test_malformed_snapshots_are_reported_as_inspection_errors(self):
        path = self.target / "snapshot.json"
        for value in (
            {},
            {"service": "unknown"},
            {
                "service": "RunWSGI",
                "name": "fg",
                "target": str(self.target),
                "arguments": {},
                "options": [],
                "configuration_files": [],
            },
        ):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Invalid service snapshot"):
                    ServiceSnapshot.read(path)

    def test_same_class_helper_cannot_publish_or_replace_the_main_job_snapshot(self):
        invocation = self.invocation("project", "compile")
        path = self.target / "snapshot.json"
        with mock.patch.dict(os.environ, invocation.snapshot_environment(path)):
            with CompileService(target=self.target, cli_options={"http_port": 9999}):
                pass
            self.assertFalse(path.exists())
            with invocation.create():
                pass
            original = path.read_text()
            with CompileService(target=self.target, cli_options={"http_port": 9999}):
                pass
            self.assertEqual(path.read_text(), original)
            self.assertEqual(ServiceSnapshot.read(path).options["http_port"], 9000)


class TestInspectionPresentation(unittest.TestCase):
    def test_markdown_table_escapes_pipes_and_lines_without_colour_codes(self):
        table = MarkdownTable(
            ("Name", "Value"), [("pipe", Text("one|two\nthree", style="red"))]
        )
        markdown = table.markdown()
        self.assertIn("| pipe | one\\|two<br>three |", markdown)
        self.assertNotIn("\x1b", markdown)

    def test_job_table_colours_states_and_treats_labels_as_literal_text(self):
        jobs = []
        for number, code in enumerate((None, 0, 2, -15), start=1):
            process = mock.Mock(pid=1230 + number)
            process.poll.return_value = code
            jobs.append(
                Namespace(
                    number=number,
                    process=process,
                    service_name="fg",
                    label="instance debug '[literal]' '|' args",
                    log_path=Path("job.log"),
                )
            )
        output = io.StringIO()
        presenter = JobPresenter(
            Console(
                file=output,
                force_terminal=True,
                no_color=False,
                color_system="standard",
                width=160,
            )
        )
        presenter.show(jobs)
        rendered = output.getvalue()
        self.assertIn("\x1b[32mRunning", rendered)
        self.assertIn("\x1b[31mExited (2)", rendered)
        self.assertIn("\x1b[33mExited (-15)", rendered)
        self.assertIn("[literal]", rendered)
        self.assertIn("Service", rendered)
        output.seek(0)
        output.truncate()
        presenter.show(jobs, markdown=True)
        self.assertNotIn("\x1b", output.getvalue())
        self.assertIn(
            "| Job | Service | State | PID | Command | Log |", output.getvalue()
        )

    def test_sensitive_options_and_command_arguments_are_redacted(self):
        self.assertEqual(
            redact_tokens(["instance", "add-user", "admin", "password-value"])[-1],
            "[redacted]",
        )
        value = safe_value(
            {
                "password": "pw",
                "environment_vars": {"API_TOKEN": "private"},
                "args": ["--password", "pw", "--token=secret"],
                "url": "https://name:secret@example.org/file",
                "port": 8080,
            }
        )
        serialized = json.dumps(value)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("private", serialized)
        self.assertEqual(value["port"], 8080)
