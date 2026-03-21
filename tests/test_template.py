from .utils import temp_cwd
from jinja2.exceptions import UndefinedError
from plonex.template import TemplateService

import unittest


class TestTemplateService(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.temp_dir = self.enterContext(temp_cwd())

    def _make_template(self, content="Hello {{ name }}!", filename="my_tpl.j2"):
        """Helper: write a template file and return its path."""
        path = self.temp_dir / filename
        path.write_text(content)
        return path

    # --- Initialisation ---

    def test_source_path_not_found(self):
        """Test that a FileNotFoundError
        is raised when the source path does not exist
        """
        non_existent_path = self.temp_dir / "non_existent_template.j2"

        with self.assertRaises(FileNotFoundError) as cm:
            TemplateService(source_path=non_existent_path)

        self.assertIn(str(non_existent_path), str(cm.exception))

    def test_source_path_is_resolved_to_absolute(self):
        """source_path is always stored as an absolute Path"""
        source = self._make_template()
        service = TemplateService(source_path=source)
        self.assertTrue(service.source_path.is_absolute())

    def test_name_defaults_to_source_stem(self):
        """When name is not provided it is derived from the source_path stem"""
        source = self._make_template(filename="my_template.j2")
        service = TemplateService(source_path=source)
        self.assertEqual(service.name, "my_template")

    def test_name_provided_is_preserved(self):
        """When name is explicitly provided it must not be overridden"""
        source = self._make_template(filename="my_template.j2")
        service = TemplateService(source_path=source, name="custom_name")
        self.assertEqual(service.name, "custom_name")

    # --- Rendering ---

    def test_render_template(self):
        """render_template returns the rendered string"""
        source = self._make_template(content="Hello {{ name }}!")
        service = TemplateService(source_path=source, options={"name": "World"})
        self.assertEqual(service.render_template(), "Hello World!")

    def test_render_template_missing_variable_raises(self):
        """render_template raises an error for undefined variables (StrictUndefined)"""
        source = self._make_template(content="{{ undefined_var }}")
        service = TemplateService(source_path=source)
        with self.assertRaises(UndefinedError):
            service.render_template()

    # --- run() ---

    def test_run_writes_rendered_content(self):
        """run() renders the template and writes it to target_path"""
        source = self._make_template(content="value={{ x }}")
        target = self.temp_dir / "out" / "result.conf"
        service = TemplateService(
            source_path=source,
            target_path=target,
            options={"x": "42"},
        )
        service.run()
        self.assertEqual(target.read_text(), "value=42")

    def test_run_creates_parent_directories(self):
        """run() creates missing parent directories for target_path"""
        source = self._make_template(content="data")
        target = self.temp_dir / "a" / "b" / "c" / "result.conf"
        service = TemplateService(source_path=source, target_path=target)
        service.run()
        self.assertTrue(target.exists())

    def test_run_sets_file_mode(self):
        """run() applies the configured mode to the output file"""
        source = self._make_template(content="data")
        target = self.temp_dir / "result.conf"
        service = TemplateService(
            source_path=source,
            target_path=target,
            mode=0o644,
        )
        service.run()
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
