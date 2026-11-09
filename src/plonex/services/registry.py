from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from plonex.base import BaseService
from plonex.services.adduser import AddUser
from plonex.services.compile import CompileService
from plonex.services.cron import CronService
from plonex.services.describe import DescribeService
from plonex.services.directory import DirectoryService
from plonex.services.doctor import Doctor
from plonex.services.edit import EditService
from plonex.services.init import InitService
from plonex.services.install import InstallService
from plonex.services.pytest import PytestService
from plonex.services.robotserver import RobotServer
from plonex.services.robottest import RobotTest
from plonex.services.runwsgi import RunWSGI
from plonex.services.sources import SourcesService
from plonex.services.supervisor import Supervisor
from plonex.services.template import TemplateService
from plonex.services.upgrade import UpgradeService
from plonex.services.zconsole import ZConsole
from plonex.services.zeoserver import ZeoServer
from plonex.services.zopetest import ZopeTest


def _service_name(service_class) -> str | None:
    for cls_field in fields(service_class):
        if cls_field.name == "name" and isinstance(cls_field.default, str):
            return cls_field.default or None
    return None


def _build_service_registry() -> dict[str, type[BaseService]]:
    service_classes = [
        AddUser,
        CompileService,
        CronService,
        DescribeService,
        Doctor,
        DirectoryService,
        EditService,
        SourcesService,
        InitService,
        InstallService,
        PytestService,
        RobotServer,
        RobotTest,
        RunWSGI,
        Supervisor,
        UpgradeService,
        ZConsole,
        ZeoServer,
        ZopeTest,
    ]
    registry: dict[str, type[BaseService]] = {}
    for service_class in service_classes:
        service_name = _service_name(service_class)
        if service_name:
            registry[service_name] = service_class
    registry["template"] = TemplateService
    return registry


@dataclass
class ServiceRegistry:
    """The shared catalog of existing dataclass services and CLI service aliases."""

    services: dict[str, type[BaseService]] = field(
        default_factory=_build_service_registry
    )

    def get(self, name: str) -> type[BaseService]:
        aliases = {
            "fg": "runwsgi",
            "run": "zconsole",
            "db": "zeoserver",
            "dependencies": "install",
        }
        key = aliases.get(name, name)
        if key not in self.services:
            raise ValueError(
                f"No service options for {name!r}. Choose a service command."
            )
        return self.services[key]


service_registry = ServiceRegistry()
