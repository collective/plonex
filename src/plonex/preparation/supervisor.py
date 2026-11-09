"""The preparation graph for Supervisor-managed project programs."""

from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from plonex.files import read_only
from plonex.preparation.dependencies import DependencyTasks
from plonex.preparation.engine import digest
from plonex.preparation.engine import file_digest
from plonex.preparation.engine import Task
from plonex.services.template import TemplateService
from rich.console import Console
from rich.text import Text
from rich.tree import Tree

import configparser
import inspect
import shlex


class SupervisorPreparation:
    def __init__(self, target: Path):
        from plonex.cli.dependencies import _service_from_config
        from plonex.services.cron import CronService
        from plonex.services.supervisor import Supervisor

        self.target = target.absolute()
        self.dependencies = DependencyTasks(self.target)
        self.graph = self.dependencies.graph
        self.services = [self.dependencies.service]
        self.owned: set[Path] = set()
        with read_only():
            self.supervisor = Supervisor(target=self.target)
            self.options = self.supervisor.options
            self.services.append(self.supervisor)
            self.programs_folder = self.supervisor.programs_folder
            self.directories(
                "supervisor.directories",
                (
                    self.supervisor.etc_folder,
                    self.programs_folder,
                    self.supervisor.log_folder,
                ),
            )
            self.cron = CronService(target=self.target, cli_options=self.options)
            self.cron.jobs  # Validate before preparing anything.
            helpers = []
            for declaration in self.options.get("services", []):
                helper = _service_from_config(
                    declaration, self.target, dependency_for="supervisor"
                )
                if helper is not None:
                    helpers.append(helper)
            previous = "dependencies.ensure"
            programs = {
                path: path.read_text()
                for path in sorted(self.programs_folder.glob("*.conf"))
            }
            helper_tasks = []
            for index, helper in enumerate(helpers):
                if isinstance(helper, TemplateService):
                    if helper.target_path is None:
                        raise ValueError("Supervisor helper templates need a target")
                    previous = self.template(
                        helper,
                        (previous, "supervisor.directories"),
                        affected=("Supervisor programs",),
                    )
                    if Path(helper.target_path).parent == self.programs_folder:
                        programs[Path(helper.target_path)] = helper.render_template()
                else:

                    def run_helper(service=helper):
                        with service:
                            service.run()

                    previous = self.graph.add(
                        Task(
                            f"helper.{index}.{helper.name}",
                            run_helper,
                            self.helper_inputs(helper),
                            requires=(previous,),
                            always=True,
                        )
                    )
                helper_tasks.append(previous)
            previous_outputs = (
                self.graph.previous_receipt("supervisor.ready") or {}
            ).get("outputs", {})
            programs = {
                path: content
                for path, content in programs.items()
                if str(path) not in previous_outputs or path in self.owned
            }
            self.runtimes(programs, tuple(helper_tasks) or ("dependencies.ensure",))
            for template in self.supervisor.pre_services or []:
                self.template(
                    template,
                    ("dependencies.ensure", "supervisor.directories"),
                    affected=("Supervisor",),
                )
            cron_path = self.programs_folder / "plonex-cron.conf"
            cron_enabled = bool(self.cron.jobs.jobs)
            if cron_enabled:
                self.owned.add(cron_path)

            def configure_cron():
                affected = cron_enabled or cron_path.exists()
                self.cron.configure_supervisor(self.programs_folder)
                return {"changed": affected}

            self.graph.add(
                Task(
                    "cron.configure",
                    configure_cron,
                    lambda: {
                        "scheduled job declarations": digest(
                            self.options.get("cron_jobs", {})
                        ),
                        "workers": digest(self.options.get("cron_workers", 1)),
                        "timezone": digest(self.options.get("cron_timezone", "UTC")),
                    },
                    outputs=lambda: {
                        str(cron_path): (
                            file_digest(cron_path)
                            if cron_enabled
                            else (
                                "absent"
                                if not cron_path.exists()
                                else file_digest(cron_path)
                            )
                        )
                    },
                    requires=("dependencies.ensure",),
                    affected=("plonex-cron",),
                    revision=digest(
                        (
                            file_digest(Path(__file__)),
                            file_digest(Path(inspect.getfile(CronService))),
                        )
                    ),
                )
            )
            prerequisites = tuple(self.graph.tasks)
            self.graph.add(
                Task(
                    "supervisor.ready",
                    self.remove_obsolete,
                    lambda: {
                        "generated targets": digest(
                            sorted(str(path) for path in self.owned)
                        )
                    },
                    outputs=lambda: {
                        str(path): file_digest(path) for path in self.owned
                    },
                    requires=prerequisites,
                )
            )
            snapshot = self.configuration_snapshot()

            def validate():
                if self.configuration_snapshot() != snapshot:
                    raise ValueError(
                        "Configuration changed during preparation; retry the command"
                    )

            self.graph.validate = validate

    def configuration_snapshot(self):
        files = set(self.target.glob("etc/plonex*.yml"))
        for service in self.services:
            files.update(self.target / name for name in service._yaml_resources)
        return {str(path): file_digest(path) for path in files}

    def template(self, template, requires=(), affected=()):
        target = Path(template.target_path)
        self.owned.add(target)
        name = f"template.{target.name}.{digest(str(target))[:10]}"
        if name in self.graph.tasks:
            existing = self.graph.tasks[name]
            if existing.inputs() != self.template_inputs(template):
                raise ValueError(f"Conflicting template definitions for {target}")
            existing.requires = tuple(
                dependency
                for dependency in dict.fromkeys((*existing.requires, *requires))
                if dependency != name
            )
            existing.affected = tuple(dict.fromkeys((*existing.affected, *affected)))
            return name
        return self.graph.add(
            Task(
                name,
                template.run,
                lambda: self.template_inputs(template),
                outputs=lambda: {
                    str(target): file_digest(target),
                    f"permissions: {target}": (
                        digest(target.stat().st_mode & 0o777)
                        if target.exists()
                        else "missing"
                    ),
                },
                requires=requires,
                affected=affected,
                revision=file_digest(Path(__file__)),
            )
        )

    @staticmethod
    def template_inputs(template):
        return {
            "template source": file_digest(template.source_path),
            "rendered configuration": digest(template.render_template()),
            "file mode": digest(template.mode),
        }

    def remove_obsolete(self):
        previous = self.graph.previous.get("supervisor.ready", {}).get("outputs", {})
        for name, expected in previous.items():
            path = Path(name)
            if path in self.owned or not path.exists():
                continue
            if file_digest(path) != expected:
                raise ValueError(
                    f"Obsolete generated file was edited: {path}. "
                    "Move or remove it before preparing again."
                )
            path.unlink()

    @staticmethod
    def helper_inputs(service):
        def inputs():
            return {"helper configuration": digest(service.options)}

        return inputs

    def directories(self, name, folders, requires=("dependencies.ensure",)):
        def create():
            for folder in folders:
                folder.mkdir(parents=True, exist_ok=True)

        return self.graph.add(
            Task(
                name,
                create,
                lambda: {
                    "runtime directories": digest([str(path) for path in folders])
                },
                outputs=lambda: {
                    str(path): "directory" if path.is_dir() else "missing"
                    for path in folders
                },
                requires=requires,
            )
        )

    def runtimes(self, programs, requires):
        from plonex.cli.parser import build_parser
        from plonex.services.invocation import ServiceInvocation

        result = []
        parser = None
        for path, content in programs.items():
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(content)
            for section in config.sections():
                if not section.startswith("program:"):
                    continue
                tokens = shlex.split(config.get(section, "command", fallback=""))
                if not tokens:
                    continue
                if Path(tokens[0]).name == "plonex":
                    tokens = tokens[1:]
                elif len(tokens) > 3 and tokens[1:3] == ["-m", "plonex.cli"]:
                    tokens = tokens[3:]
                else:
                    continue
                if parser is None:
                    parser = build_parser(target=self.target)
                try:
                    args = parser.parse_args(
                        tokens,
                        namespace=Namespace(
                            target=self.target, verbose=False, quiet=False
                        ),
                    )
                except SystemExit as error:
                    raise ValueError(
                        f"{path.name}: invalid plonex command in {section}"
                    ) from error
                if args.action == "supervisor":
                    raise ValueError(
                        f"{section} recursively invokes Supervisor; check its command"
                    )
                if (
                    args.action not in {"runwsgi", "fg", "zeoserver"}
                    or Path(args.target).absolute() != self.target
                ):
                    continue
                invocation = ServiceInvocation.from_args(args, self.target)
                directory = Path(
                    config.get(section, "directory", fallback=str(self.target))
                )
                if not directory.is_absolute():
                    directory = self.target / directory
                if "config_files" in invocation.kwargs:
                    invocation.kwargs["config_files"] = [
                        str(directory / name)
                        for name in invocation.kwargs["config_files"]
                    ]
                service = invocation.create()
                self.services.append(service)
                directories = [
                    service.tmp_folder,
                    service.client_home,
                    service.var_folder / "log",
                ]
                if args.action == "zeoserver":
                    directories += [
                        service.var_folder / "blobstorage",
                        service.var_folder / "filestorage",
                    ]
                cache = service.options.get("environment_vars", {}).get(
                    "CHAMELEON_CACHE"
                )
                if cache:
                    directories.append(Path(cache))
                directory_task = f"runtime.directories.{service.name}"
                if directory_task not in self.graph.tasks:
                    self.directories(directory_task, tuple(directories))
                for template in service.pre_services or []:
                    result.append(
                        self.template(
                            template,
                            (*requires, directory_task),
                            affected=(section.removeprefix("program:"),),
                        )
                    )
        return result

    def plan(self):
        return [asdict(entry) for entry in self.graph.plan()]

    def show_plan(self):
        console = Console()
        tree = Tree("Supervisor startup plan")
        for entry in self.plan():
            style = "green" if entry["state"] == "current" else "yellow"
            label = Text(entry["task"], style="bold")
            label.append("  " + entry["state"], style=style)
            branch = tree.add(label)
            if entry["requires"]:
                branch.add(
                    Text("Requires: " + ", ".join(entry["requires"]), style="dim")
                )
            for reason in entry["reasons"]:
                branch.add(Text(reason))
            if entry["affected"] and entry["state"] != "current":
                branch.add(Text("Affects: " + ", ".join(entry["affected"])))
        console.print(tree)
        console.print(
            "Final operation: supervisor start. "
            "Preparation does not restart existing programs."
        )

    def run(self):
        executed = self.graph.run()
        if executed:
            Console().print(f"Prepared {len(executed)} task(s).", markup=False)
        return executed
