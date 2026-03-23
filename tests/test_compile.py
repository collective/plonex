from .utils import PloneXTestCase
from .utils import temp_cwd
from plonex.compile import CompileService

import inspect


class TestCompileService(PloneXTestCase):

    def test_init_signature(self):
        """Test the class init method"""
        sig = inspect.signature(CompileService.__init__)
        self.assertListEqual(
            list(sig.parameters),
            ["self", "name", "target", "cli_options", "config_files"],
        )

    def test_constructor(self):
        """Test that __post_init__ creates var_folder and target_file"""
        with temp_cwd() as cwd:
            svc = CompileService()
            self.assertEqual(svc.var_folder, cwd / "var")
            self.assertEqual(svc.target_file, cwd / "var" / "plonex.yml")
            self.assertTrue(svc.var_folder.exists())

    def test_run(self):
        """Test that run() writes options as YAML to the target_file"""
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text("mykey: myvalue\n")
            with CompileService() as svc:
                svc.run()
            result = (cwd / "var" / "plonex.yml").read_text()
            self.assertIn("mykey: myvalue", result)

    def test_run_creates_output_file(self):
        """Test that run() creates the output file"""
        with temp_cwd() as cwd:
            with CompileService() as svc:
                svc.run()
            self.assertTrue((cwd / "var" / "plonex.yml").exists())

    def test_run_generates_gitman_file(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
                "      rev: main\n"
            )
            with CompileService() as svc:
                svc.run()
            result = (cwd / "var" / "gitman.yml").read_text()
            self.assertIn(f"location: {cwd / 'src'}", result)
            self.assertIn("- name: my.package", result)
            self.assertIn("type: git", result)
            self.assertIn("repo: https://github.com/example/my.package.git", result)

    def test_run_generates_gitman_file_with_custom_location(self):
        with temp_cwd() as cwd:
            (cwd / "etc").mkdir()
            (cwd / "etc" / "plonex.yml").write_text(
                "sources_location: external\n"
                "sources:\n"
                "    my.package:\n"
                "      repo: https://github.com/example/my.package.git\n"
            )
            with CompileService() as svc:
                svc.run()
            result = (cwd / "var" / "gitman.yml").read_text()
            self.assertIn(f"location: {cwd / 'external'}", result)
