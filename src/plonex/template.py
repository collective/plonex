from importlib import resources
from jinja2 import StrictUndefined
from jinja2 import Template


def render(template_path, options):
    """This helper takes a template path and an options object.

    The template path is in the form:

    package.module.folder:template_path.j2
    """

    package, filename_path = template_path.partition(":")[::2]
    package_files = resources.files(package)
    path = package_files / filename_path
    # template with strict undefined
    template = Template(path.read_text(), undefined=StrictUndefined)
    return template.render(options=options)
