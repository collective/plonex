from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from plonex.base import ZopeBasedService
from plonex.services.template import TemplateService
from typing import ClassVar


@dataclass(kw_only=True)
class RunWSGI(ZopeBasedService):
    """Run a WSGI service with generated Zope runtime configuration."""

    name: str = "runwsgi"

    args: list[str] = field(default_factory=list)
    stream_output: ClassVar[bool] = True

    @cached_property
    def options_defaults(self):
        options_defaults = super().options_defaults
        options_defaults.update(
            {
                "http_port": 8080,
                "http_address": "0.0.0.0",
            }
        )
        return options_defaults

    def __post_init__(self):
        super().__post_init__()
        if not self.pre_services:
            self.pre_services = self._build_zope_pre_services()
            assert (
                self.tmp_folder is not None
            ), "tmp_folder should be set before accessing pre_services"
            self.pre_services.append(
                TemplateService(
                    source_path="resource://plonex.services.runwsgi.templates:wsgi.ini.j2",  # noqa: E501
                    target_path=self.tmp_folder / "etc" / "wsgi.ini",
                    options={
                        "context": self,
                        "name": f"runwsgi-{self.options['http_port']}",
                        "zope_conf": self.tmp_folder / "etc" / "zope.conf",
                        "var_folder": self.var_folder,
                        "http_port": self.options["http_port"],
                        "http_address": self.options["http_address"],
                        "threads": self.options.get("threads", 4),
                    },
                )
            )

    @property
    def command(self):
        assert (
            self.tmp_folder is not None
        ), "tmp_folder should be set before accessing command"
        return [
            str(self.virtualenv_dir / "bin" / "runwsgi"),
            str(self.tmp_folder / "etc" / "wsgi.ini"),
            *self.args,
        ]
