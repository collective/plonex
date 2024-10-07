import sys
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from plonedeployment.template import render


@dataclass
class ZopeConfOptions:

    instance_home: Path
    client_home: Path
    blobstorage: Path
    zeo_address: Path
    environment_vars: dict[str, str] = field(default_factory=dict)
    debug_mode: Literal["on", "off"] = "off"
    security_policy_implementation: Literal["PYTHON", "C"] = "C"
    verbose_security: Literal["on", "off"] = "off"


@dataclass
class WSGIOptions:

    zope_conf: Path
    var_folder: Path
    name: str = "instance"
    fast_listen: bool = False
    http_port: int = 8080
    threads: int = 3


@dataclass
class InterpreterOptions:

    python: Path


@dataclass
class InstanceOptions:

    python: Path
    zope_conf_path: Path
    interpreter_path: Path
    wsgi_ini_path: Path


def run():
    target = Path.cwd()

    var_folder = Path(target / "var")

    with TemporaryDirectory(dir=target / "tmp") as tmpdir:

        tmpdir = Path(tmpdir)

        # Create the directory etc/package-includes
        etc_path = tmpdir / "etc"
        etc_path.mkdir(parents=True)

        bin_path = tmpdir / "bin"
        bin_path.mkdir(parents=True)

        package_includes_path = etc_path / "package-includes"
        package_includes_path.mkdir(parents=True)

        zope_conf_path = etc_path / "zope.conf"
        wsgi_ini_path = etc_path / "wsgi.ini"
        interpreter_path = bin_path / "interpreter"
        instance_path = bin_path / "instance"

        zope_conf_path.write_text(
            render(
                "plonedeployment.zeoclient.templates:zope.conf.j2",
                ZopeConfOptions(
                    instance_home=tmpdir,
                    client_home=tmpdir,
                    blobstorage=var_folder / "blobstorage",
                    zeo_address=var_folder / "zeosocket.sock",
                ),
            )
        )

        wsgi_ini_path.write_text(
            render(
                "plonedeployment.zeoclient.templates:wsgi.ini.j2",
                WSGIOptions(zope_conf=zope_conf_path, var_folder=var_folder),
            )
        )

        interpreter_path.write_text(
            render(
                "plonedeployment.zeoclient.templates:interpreter.j2",
                InterpreterOptions(python=Path(sys.executable)),
            )
        )

        instance_path.write_text(
            render(
                "plonedeployment.zeoclient.templates:instance.j2",
                InstanceOptions(
                    python=Path(sys.executable),
                    zope_conf_path=zope_conf_path,
                    interpreter_path=interpreter_path,
                    wsgi_ini_path=wsgi_ini_path,
                ),
            )
        )
        instance_path.chmod(0o750)

        # Run the instance
        instance_path = str(instance_path)
        print(instance_path)
        import subprocess

        subprocess.run([instance_path, "fg"], check=True)
