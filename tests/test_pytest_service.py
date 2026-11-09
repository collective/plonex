from .utils import temp_cwd
from plonex.cli import main
from plonex.cli.parser import build_parser
from plonex.services.pytest import PytestService
from unittest import mock

import os
import subprocess
import sys
import unittest


class TestPytestService(unittest.TestCase):
    def test_parser_forwards_options_and_values_after_the_package(self):
        parser = build_parser()
        for tokens in (
            ["test", "pytest", "my.package", "-k", "login or logout", "-x", "-vv"],
            [
                "test",
                "pytest",
                "my.package",
                "--",
                "-k",
                "login or logout",
                "-x",
                "-vv",
            ],
        ):
            with self.subTest(tokens=tokens):
                args = parser.parse_args(tokens)
                self.assertEqual(args.package, "my.package")
                self.assertEqual(
                    args.pytest_args, ["-k", "login or logout", "-x", "-vv"]
                )
                self.assertFalse(args.verbose)

    def test_command_uses_the_project_python_and_pyargs(self):
        with temp_cwd() as target:
            (target / ".venv" / "bin").mkdir(parents=True)
            (target / ".venv" / "bin" / "activate").touch()
            service = PytestService(package="my.package", args=["--", "-k", "login"])
            self.assertEqual(
                service.command,
                [
                    str(target / ".venv" / "bin" / "python"),
                    "-m",
                    "pytest",
                    "--pyargs",
                    "my.package",
                    "-k",
                    "login",
                ],
            )

    def test_missing_package_is_an_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "package or test path is required"):
            _ = PytestService().command

    def test_main_runs_service_dependencies_and_forwards_all_pytest_arguments(self):
        with temp_cwd() as target:
            (target / "etc").mkdir()
            (target / "etc" / "plonex.yml").write_text("{}\n")
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    ["plonex", "test", "pytest", "my.package", "-q", "-k", "login"],
                ),
                mock.patch("plonex.cli._run_service_dependencies") as dependencies,
                mock.patch("plonex.cli.PytestService") as pytest_service,
            ):
                main()
            dependencies.assert_called_once_with(target, "pytest")
            pytest_service.assert_called_once_with(
                target=target, package="my.package", args=["-q", "-k", "login"]
            )
            pytest_service.return_value.__enter__.return_value.run.assert_called_once()


class TestPytestProcess(unittest.TestCase):
    def setUp(self):
        self.target = self.enterContext(temp_cwd())
        (self.target / "etc").mkdir()
        (self.target / "etc" / "plonex.yml").write_text(
            (
                "environment_vars:\n  PLONEX_PYTEST_CONFIG: "
                "configured\naliases:\n  test_whatever: test pytest "
                "example_package\n"
            )
        )
        bin_folder = self.target / ".venv" / "bin"
        bin_folder.mkdir(parents=True)
        (bin_folder / "activate").touch()
        python = bin_folder / "python"
        python.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            "os.environ['PLONEX_PYTEST_INTERPRETER'] = 'target-python'\n"
            "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
        )
        python.chmod(0o755)
        package = self.target / "example_package"
        package.mkdir()
        (package / "__init__.py").touch()
        (package / "test_example.py").write_text(
            "import os\n"
            "def test_success():\n"
            "    assert os.environ['PLONEX_PYTEST_INTERPRETER'] == 'target-python'\n"
            "    assert os.environ['PLONEX_PYTEST_CONFIG'] == 'configured'\n"
            "def test_failure():\n"
            "    assert False, 'intentional test failure'\n"
        )
        self.env = dict(os.environ)
        # Keep the nested pytest run independent of the outer run's plugins/options.
        self.env.pop("PYTEST_ADDOPTS", None)
        self.env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    def invoke(self, *args, input=None):
        return subprocess.run(
            [sys.executable, "-m", "plonex.cli", "--target", str(self.target), *args],
            text=True,
            capture_output=True,
            cwd=self.target.parent,
            env=self.env,
            input=input,
            timeout=30,
        )

    def test_direct_package_and_alias_execute_real_pytest_with_filters(self):
        for command in (["test", "pytest", "example_package"], ["test_whatever"]):
            with self.subTest(command=command):
                result = self.invoke(*command, "-k", "success", "-q")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("1 passed", result.stdout)
                self.assertIn("1 deselected", result.stdout)

    def test_paths_and_node_ids_work_in_addition_to_package_names(self):
        for path in (
            "example_package/test_example.py::test_success",
            "example_package/test_example.py",
        ):
            with self.subTest(path=path):
                result = self.invoke("test", "pytest", path, "-k", "success", "-q")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("1 passed", result.stdout)

    def test_pytest_failure_exit_status_is_preserved(self):
        result = self.invoke("test_whatever", "-k", "failure", "-q")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("intentional test failure", result.stdout)

    def test_shell_executes_alias_and_survives_failed_tests(self):
        result = self.invoke(
            "shell",
            input=(
                "test_whatever -k failure -q\n" "test_whatever -k success -q\n" "exit\n"
            ),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 failed", result.stdout)
        self.assertIn("1 passed", result.stdout)
        self.assertIn("Command exited with status 1", result.stderr)
