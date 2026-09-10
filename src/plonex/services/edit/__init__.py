"""Edit service for plonex configuration files."""

from dataclasses import dataclass
from pathlib import Path
from plonex.base import BaseService
from rich.console import Console
from rich.prompt import Prompt

import os


@dataclass(kw_only=True)
class EditService(BaseService):
    """Service to open plonex source configuration files in the user's editor.

    Discovers and presents an interactive menu of editable configuration files
    including YAML configs, requirements, and constraints files. Allows users
    to select which files to edit, then opens them in their preferred editor.

    Editor resolution (highest to lowest precedence):
    1. CLI --editor flag (passed via cli_options)
    2. plonex.yml options.editor setting
    3. $EDITOR environment variable
    4. Fallback to 'nano'
    """

    name: str = "edit"
    open_all: bool = False

    def discover_config_files(self) -> list[Path]:
        """Discover all source configuration files.

        Returns a sorted list of existing configuration files in:
        - etc/plonex.yml
        - etc/plonex*.yml variants
        - etc/plonex-*.yml variants
        - profiles/*.yml
        - etc/requirements.d/*.txt
        - profiles/*/requirements.d/*.txt
        - etc/constraints.d/*.txt
        - profiles/*/constraints.d/*.txt
        - Root level: pyproject.toml, Makefile
        """
        files = [
            Path(f) for f in self._yaml_resources
        ]  # Start with any YAML resources already tracked
        etc_folder = self.target / "etc"
        if etc_folder.exists():
            # Requirements fragments
            requirements_d = etc_folder / "requirements.d"
            if requirements_d.exists():
                for req_file in sorted(requirements_d.glob("*.txt")):
                    if req_file.is_file():
                        files.append(req_file)

            # Constraints fragments
            constraints_d = etc_folder / "constraints.d"
            if constraints_d.exists():
                for const_file in sorted(constraints_d.glob("*.txt")):
                    if const_file.is_file():
                        files.append(const_file)

        # Root-level config files
        root_files = [
            self.target / "pyproject.toml",
            self.target / "Makefile",
        ]
        for root_file in root_files:
            if root_file.exists():
                files.append(root_file)

        return files

    def resolve_editor(self) -> str:
        """Resolve the editor to use for editing.

        Precedence (highest to lowest):
        1. CLI --editor flag (passed via cli_options)
        2. plonex.yml options.editor
        3. $EDITOR environment variable
        4. Fallback to 'nano'
        """
        # 1. CLI option
        if self.cli_options.get("editor"):
            return str(self.cli_options["editor"])

        # 2. Config file option
        editor_from_config = self.options.get("editor")
        if editor_from_config:
            return str(editor_from_config)

        # 3. Environment variable
        editor_from_env = os.environ.get("EDITOR")
        if editor_from_env:
            return editor_from_env

        # 4. Fallback
        return "nano"

    def select_files_interactive(self, files: list[Path]) -> list[Path]:
        """Display an interactive menu for file selection.

        Returns a list of files selected by the user.
        """
        if not files:
            console = Console()
            console.print("[yellow]No configuration files found to edit.[/yellow]")
            return []

        console = Console()
        console.print("[bold]Available configuration files:[/bold]")

        # Display files with their relative paths and numbers
        file_display = []
        for idx, file_path in enumerate(files, 1):
            try:
                rel_path = file_path.relative_to(self.target)
            except ValueError:
                rel_path = file_path
            file_display.append((idx, rel_path, file_path))
            console.print(f"  {idx}. {rel_path}")

        console.print()

        try:
            selection_str = Prompt.ask(
                "Enter file numbers to edit (comma-separated, e.g., 1,3,5)",
                console=console,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Selection cancelled by user.[/yellow]")
            return []

        selected_files: list[Path] = []
        if selection_str.strip():
            try:
                indices = [int(x.strip()) for x in selection_str.split(",")]
                for idx in indices:
                    if 1 <= idx <= len(file_display):
                        selected_files.append(file_display[idx - 1][2])
                    else:
                        console.print(
                            f"[yellow]Warning: Invalid selection {idx}, "
                            f"skipping.[/yellow]"
                        )
            except ValueError:
                console.print(
                    "[red]Invalid input. Please enter comma-separated numbers.[/red]"
                )
                return []
        else:
            console.print("[yellow]No files selected. Exiting.[/yellow]")
            return []

        return selected_files

    def run(self) -> None:
        """Run the edit service.

        Discovers config files, optionally presents an interactive menu,
        then opens selected files in the user's preferred editor.
        """
        # Discover available files
        files = self.discover_config_files()

        if not files:
            console = Console()
            console.print("[yellow]No configuration files found to edit.[/yellow]")
            return

        # Determine which files to open
        if self.open_all:
            selected_files = files
        else:
            selected_files = self.select_files_interactive(files)

        if not selected_files:
            return

        # Resolve editor and execute
        editor = self.resolve_editor()

        try:
            self.logger.info(f"Opening {len(selected_files)} file(s) with {editor}")
            file_paths = [str(f) for f in selected_files]
            self.execute_command([editor] + file_paths, stream_output=True)
        except Exception as e:
            console = Console()
            console.print(f"[red]Error opening editor '{editor}': {e}[/red]")
            raise
