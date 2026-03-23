from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from plonex.base import BaseService
from rich.console import Console
from rich.table import Table
from typing import Any

import sh  # type: ignore[import-untyped]
import yaml


@dataclass(kw_only=True)
class SourcesService(BaseService):
    """Manage source checkout configuration and operations (via Gitman)."""

    name: str = "sources"
    assume_yes: bool = False

    var_folder: Path = field(init=False)
    gitman_file: Path = field(init=False)

    def __post_init__(self):
        self.target = self._ensure_dir(self.target.absolute())
        self.var_folder = self._ensure_dir(self.target / "var")
        self.gitman_file = self.var_folder / "gitman.yml"

    @property
    def sources_options(self) -> dict[str, Any]:
        sources = self.options.get("sources")
        return sources if isinstance(sources, dict) else {}

    @property
    def compiled_gitman_options(self) -> dict[str, Any] | None:
        if not self.sources_options:
            return None
        rendered_sources: list[dict[str, Any]] = []
        for source_name, source_options in self.sources_options.items():
            if not isinstance(source_options, dict):
                continue
            entry: dict[str, Any] = {
                "name": str(source_name),
                "type": str(source_options.get("type", "git")),
                "repo": source_options.get("repo"),
            }
            rev = source_options.get("rev")
            if isinstance(rev, str) and rev.strip():
                entry["rev"] = rev
            rendered_sources.append(entry)
        return {
            "location": str(self.checkout_root),
            "sources": rendered_sources,
        }

    @property
    def has_sources(self) -> bool:
        return len(self.sources_options) > 0

    @property
    def checkout_root(self) -> Path:
        location = str(self.options.get("sources_location", "src"))
        return self.target / str(location)

    @property
    def sources(self) -> dict[str, Any]:
        return self.sources_options

    def _validate_sources_for_gitman(self) -> bool:
        valid = True
        for source_name, source_options in self.sources_options.items():
            if not isinstance(source_name, str) or not source_name.strip():
                self.logger.error(
                    "Invalid source name %r: it must be a non-empty string",
                    source_name,
                )
                valid = False
                continue
            if not isinstance(source_options, dict):
                self.logger.error(
                    "Invalid source mapping for %r: expected a YAML mapping",
                    source_name,
                )
                valid = False
                continue
            repo = source_options.get("repo")
            if not isinstance(repo, str) or not repo.strip():
                self.logger.error(
                    "Invalid source mapping for %r: missing non-empty 'repo'",
                    source_name,
                )
                valid = False
        return valid

    @property
    def command(self) -> list[str]:
        gitman_bin = self.target / ".venv" / "bin" / "gitman"
        executable = str(gitman_bin) if gitman_bin.exists() else "gitman"
        return [executable]

    def compile_config(self) -> Path | None:
        options = self.compiled_gitman_options
        if options is None:
            return None
        if not self._validate_sources_for_gitman():
            return None
        self.gitman_file.write_text(yaml.dump(options, sort_keys=True))
        return self.gitman_file

    def _checkout_path(self, source_name: str, source_options: Any) -> Path:
        if isinstance(source_options, dict):
            custom_path = source_options.get("path")
            if isinstance(custom_path, str) and custom_path.strip():
                return self.target / custom_path
        return self.checkout_root / source_name

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.target).as_posix()
        except ValueError:
            return str(path)

    def configured_checkouts(self) -> dict[str, Path]:
        return {
            str(source_name): self._checkout_path(str(source_name), source_options)
            for source_name, source_options in self.sources.items()
        }

    def missing_checkouts(self) -> dict[str, Path]:
        return {
            source_name: path
            for source_name, path in self.configured_checkouts().items()
            if not path.exists()
        }

    def existing_checkouts(self) -> list[Path]:
        root = self.checkout_root
        if not root.exists():
            return []
        return sorted(
            [
                path
                for path in root.iterdir()
                if path.is_dir() and (path / ".git").exists()
            ]
        )

    def unmanaged_existing_checkouts(self) -> list[Path]:
        managed = set(self.configured_checkouts().values())
        return [path for path in self.existing_checkouts() if path not in managed]

    def _git_remote_url(self, checkout: Path) -> str | None:
        try:
            result = self.execute_command(
                ["git", "-C", str(checkout), "remote", "get-url", "origin"]
            ).strip()
        except sh.ErrorReturnCode:
            return None
        return result or None

    def _git_revision(self, checkout: Path) -> str | None:
        try:
            branch = self.execute_command(
                ["git", "-C", str(checkout), "branch", "--show-current"]
            ).strip()
            if branch:
                return branch
            commit = self.execute_command(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"]
            ).strip()
            return commit or None
        except sh.ErrorReturnCode:
            return None

    def _git_current_branch(self, checkout: Path) -> str | None:
        try:
            branch = self.execute_command(
                ["git", "-C", str(checkout), "branch", "--show-current"]
            ).strip()
        except sh.ErrorReturnCode:
            return None
        return branch or None

    def _has_modifications(self, checkout: Path) -> bool:
        try:
            status = self.execute_command(
                ["git", "-C", str(checkout), "status", "--porcelain"]
            ).strip()
        except sh.ErrorReturnCode:
            return False
        return bool(status)

    def suggested_sources_mapping(self) -> dict[str, Any]:
        suggestions: dict[str, Any] = {}
        for checkout in self.unmanaged_existing_checkouts():
            source_name = checkout.name
            source_options: dict[str, Any] = {}
            repo = self._git_remote_url(checkout)
            if repo:
                source_options["repo"] = repo
            rev = self._git_revision(checkout)
            if rev:
                source_options["rev"] = rev
            relative = checkout.relative_to(self.checkout_root).as_posix()
            if relative != source_name:
                source_options["path"] = self._display_path(checkout)
            suggestions[source_name] = source_options
        return suggestions

    def render_suggestions_yaml(self) -> str:
        suggestions = self.suggested_sources_mapping()
        if not suggestions:
            return ""
        payload: dict[str, Any] = {"sources": suggestions}
        location = self.checkout_root.relative_to(self.target).as_posix()
        if location != "src":
            payload["sources_location"] = location
        return yaml.dump(payload, sort_keys=True)

    def _apply_suggestions(self, destination: Path) -> bool:
        suggestions = self.suggested_sources_mapping()
        if not suggestions:
            return False

        indent = self._detect_yaml_indent(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing_payload: Any = {}
        if destination.exists():
            existing_payload = yaml.safe_load(destination.read_text()) or {}

        if not isinstance(existing_payload, dict):
            self.logger.error("Cannot update %r: expected a YAML mapping", destination)
            return False

        existing_sources = existing_payload.get("sources")
        sources_mapping = (
            dict(existing_sources) if isinstance(existing_sources, dict) else {}
        )
        sources_mapping.update(suggestions)
        existing_payload["sources"] = sources_mapping
        sources_location = self.checkout_root.relative_to(self.target).as_posix()
        if sources_location != "src":
            existing_payload.setdefault("sources_location", sources_location)

        destination.write_text(
            yaml.dump(
                existing_payload,
                sort_keys=False,
                default_flow_style=False,
                indent=indent,
            )
        )
        return True

    def _detect_yaml_indent(self, destination: Path, fallback: int = 2) -> int:
        if not destination.exists():
            return fallback

        for line in destination.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "\t" in line:
                continue
            leading_spaces = len(line) - len(line.lstrip(" "))
            if leading_spaces > 0:
                return max(2, leading_spaces)
        return fallback

    def list_tainted(self) -> list[Path]:
        tainted: list[Path] = []
        for source_name, source_options in self.sources.items():
            checkout = self._checkout_path(str(source_name), source_options)
            if not checkout.exists():
                continue
            if not (checkout / ".git").exists():
                continue
            try:
                status = self.execute_command(
                    ["git", "-C", str(checkout), "status", "--porcelain"]
                ).strip()
            except sh.ErrorReturnCode:
                self.logger.warning("Unable to inspect checkout %r", checkout)
                continue
            if status:
                tainted.append(checkout)
        return tainted

    @BaseService.entered_only
    def run_update(
        self,
        force: bool = False,
        assume_yes: bool | None = None,
    ) -> None:
        if not self.has_sources:
            self.logger.info("Skipping sources update: no sources configured")
            return

        self.logger.info(
            "Ensuring sources location exists: %s",
            self.checkout_root,
        )
        self.checkout_root.mkdir(parents=True, exist_ok=True)
        compiled = self.compile_config()
        if compiled is None:
            self.logger.error("Cannot update sources: invalid sources configuration")
            return

        confirmed = self.assume_yes if assume_yes is None else assume_yes
        if force and not confirmed:
            answer = self.ask_for_value(
                "Force update may discard local changes. Continue?",
                default="n",
            )
            if answer.lower() not in {"y", "yes"}:
                self.logger.info("Cancelled force update")
                return

        command = self.command + ["update"]
        if force:
            command.append("--force")
        self.run_command(command, cwd=self.gitman_file.parent)

    @BaseService.entered_only
    def run_list(self) -> None:
        checkouts = self.configured_checkouts()
        if not checkouts:
            self.print("No configured sources checkouts.")
            return

        console = Console()
        table = Table(title="Configured Sources")
        table.add_column("Source", style="bold")
        table.add_column("Folder")
        table.add_column("Repo URL")
        table.add_column("Health", justify="center", no_wrap=True)
        table.add_column("Details")

        for source_name, path in sorted(checkouts.items()):
            source_options = self.sources.get(source_name)
            configured_repo = None
            configured_rev = None
            if isinstance(source_options, dict):
                configured_repo = source_options.get("repo")
                configured_rev = source_options.get("rev")

            detected_repo = None
            details: list[str] = []
            severity = 0  # 0=ok, 1=warning, 2=error
            health_badge = "[bold green]✓[/bold green]"
            if not path.exists():
                health_badge = "[bold red]✗[/bold red]"
                details.append("missing")
                severity = 2
            elif not (path / ".git").exists():
                health_badge = "[bold yellow]⚠[/bold yellow]"
                details.append("not-git")
                severity = 1
            else:
                detected_repo = self._git_remote_url(path)
                branch = self._git_current_branch(path)
                if self._has_modifications(path):
                    health_badge = "[bold yellow]⚠[/bold yellow]"
                    details.append("modified")
                    severity = max(severity, 1)

                if branch:
                    details.append(f"[dim]branch:{branch}[/dim]")
                    if (
                        isinstance(configured_rev, str)
                        and configured_rev
                        and configured_rev != branch
                    ):
                        details.append(f"[yellow]expected:{configured_rev}[/yellow]")
                        severity = max(severity, 1)
                else:
                    details.append("[yellow]detached[/yellow]")
                    severity = max(severity, 1)

                if (
                    isinstance(configured_repo, str)
                    and configured_repo
                    and detected_repo
                    and configured_repo != detected_repo
                ):
                    health_badge = "[bold red]✗[/bold red]"
                    details.append("[bold red]repo-mismatch[/bold red]")
                    severity = 2

            repo_url = (
                detected_repo
                or (configured_repo if isinstance(configured_repo, str) else None)
                or "-"
            )
            table.add_row(
                source_name,
                self._display_path(path),
                repo_url,
                health_badge,
                ", ".join(details) if details else "[dim]-[/dim]",
                style={0: "green", 1: "yellow", 2: "red"}.get(severity, ""),
            )

        console.print(table)
        console.print(
            "[dim]Legend:[/dim] [bold green]✓[/bold green] clean "
            "[bold yellow]⚠[/bold yellow] warning "
            "[bold red]✗[/bold red] error"
        )

        unmanaged = self.unmanaged_existing_checkouts()
        if unmanaged:
            console.print("\nUnmanaged existing checkouts found:")
            for path in unmanaged:
                console.print(f"- {self._display_path(path)}")
            self._print_suggestion_block(console)

    @BaseService.entered_only
    def run_show_missing(self) -> None:
        missing = self.missing_checkouts()
        if not missing:
            self.print("No missing checkouts.")
            return
        console = Console()
        console.print("Missing checkouts:")
        for source_name, path in sorted(missing.items()):
            console.print(f"- {source_name}: {self._display_path(path)}")

    @BaseService.entered_only
    def run_clone_missing(self, assume_yes: bool | None = None) -> None:
        missing = self.missing_checkouts()
        if not missing:
            self.print("No missing checkouts.")
            return

        confirmed = self.assume_yes if assume_yes is None else assume_yes
        if not confirmed:
            answer = self.ask_for_value(
                f"Clone {len(missing)} missing checkouts now?",
                default="n",
            )
            if answer.lower() not in {"y", "yes"}:
                self.logger.info("Cancelled clone-missing")
                return

        for source_name in sorted(missing):
            source_options = self.sources.get(source_name)
            if not isinstance(source_options, dict):
                self.logger.warning("Skipping %r: invalid source mapping", source_name)
                continue
            repo = source_options.get("repo")
            if not isinstance(repo, str) or not repo.strip():
                self.logger.warning("Skipping %r: missing repo URL", source_name)
                continue
            destination = self._checkout_path(source_name, source_options)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.logger.info("Cloning %r into %r", source_name, destination)
            self.run_command(["git", "clone", repo, str(destination)])
            rev = source_options.get("rev")
            if isinstance(rev, str) and rev.strip():
                self.run_command(["git", "-C", str(destination), "checkout", rev])

    def _print_suggestion_block(self, console: Console) -> None:
        suggestion_yaml = self.render_suggestions_yaml()
        if not suggestion_yaml:
            return
        console.print("\nSuggested configuration to add to etc/plonex.yml:")
        console.print(suggestion_yaml)

    @BaseService.entered_only
    def run_suggest_existing(
        self,
        apply: bool = False,
        apply_local: bool = False,
        apply_profile: bool = False,
    ) -> None:
        selected_destinations = [apply, apply_local, apply_profile]
        if sum(1 for value in selected_destinations if value) > 1:
            self.logger.error(
                "Use only one destination flag: apply, apply_local, or apply_profile"
            )
            return

        console = Console()
        suggestion_yaml = self.render_suggestions_yaml()
        if not suggestion_yaml:
            self.print("No unmanaged existing checkouts found.")
            return

        if apply:
            destination = self.target / "etc" / "plonex.yml"
            if self._apply_suggestions(destination):
                self.print(
                    f"Applied sources suggestions to {self._display_path(destination)}"
                )
            return

        if apply_local:
            destination = self.target / "etc" / "plonex-sources.local.yml"
            if self._apply_suggestions(destination):
                self.print(
                    f"Applied sources suggestions to {self._display_path(destination)}"
                )
            return

        if apply_profile:
            plonex_yml = self.target / "etc" / "plonex.yml"
            if not plonex_yml.exists():
                self.logger.error(
                    "No etc/plonex.yml found; cannot determine a profile to write to"
                )
                return
            raw_local = yaml.safe_load(plonex_yml.read_text()) or {}
            raw_profiles = raw_local.get("profiles") or []
            if isinstance(raw_profiles, str):
                raw_profiles = [raw_profiles]
            if not raw_profiles:
                self.logger.error(
                    "No profiles configured in etc/plonex.yml; "
                    "cannot determine a profile to write to"
                )
                return
            resolved = self._resolve_profile_source(raw_profiles[0], self.target)
            if isinstance(resolved, str):
                self.logger.error("Cannot write to a remote profile: %s", resolved)
                return
            destination = resolved / "etc" / "plonex.yml"
            if self._apply_suggestions(destination):
                self.print(
                    f"Applied sources suggestions to {self._display_path(destination)}"
                )
            return

        self._print_suggestion_block(console)

    @BaseService.entered_only
    def run_show_tainted(self) -> None:
        tainted = self.list_tainted()
        if not tainted:
            self.print("No tainted checkouts found.")
            return
        console = Console()
        console.print("Tainted checkouts:")
        for path in tainted:
            console.print(f"- {self._display_path(path)}")

        if self.unmanaged_existing_checkouts():
            self._print_suggestion_block(console)
