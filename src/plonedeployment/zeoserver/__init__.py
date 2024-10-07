import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from plonedeployment import logger
from plonedeployment.template import render


@dataclass
class ZeoServerOption:

    address: Path
    pidfile: Path
    blob_dir: Path
    path: Path
    log_path: Path
    tmp_folder: Path
    socket_name: Path
    runzeo_path: Path


@dataclass
class RunZeoOption:
    python: Path
    instance_home: Path
    zeo_conf: Path


def run():
    target = Path.cwd()

    var_folder = target / "var"

    with TemporaryDirectory(dir=target / "tmp") as tmpdir:

        tmpdir = Path(tmpdir)
        zeo_conf_path = tmpdir / "zeo.conf"
        runzeo_path = tmpdir / "runzeo"

        options = ZeoServerOption(
            address=Path(target / "var" / "zeosocket.sock"),
            pidfile=Path(tmpdir / "zeoserver.pid"),
            blob_dir=Path(var_folder / "blobstorage"),
            path=Path(var_folder / "filestorage" / "Data.fs"),
            log_path=Path(var_folder / "log" / "zeoserver.log"),
            tmp_folder=tmpdir,
            socket_name=Path(tmpdir / "zeoserver.sock"),
            runzeo_path=runzeo_path,
        )

        zeo_conf_path.write_text(
            render("plonedeployment.zeoserver.templates:zeo.conf.j2", options)
        )
        logger.debug(f"Generated {zeo_conf_path}")
        logger.debug(zeo_conf_path.read_text())

        logger.debug("Generate the runzeo command")

        options = RunZeoOption(
            python=Path(sys.executable),
            instance_home=tmpdir,
            zeo_conf=zeo_conf_path,
        )

        runzeo_path.write_text(
            render("plonedeployment.zeoserver.templates:runzeo.j2", options),
        )
        runzeo_path.chmod(0o755)
        logger.debug(f"Generated {runzeo_path}")
        logger.debug(runzeo_path.read_text())

        logger.debug("Starting ZEO Server")

        # Temporary cd to the tmpdir and run the runzeo command
        with tmpdir:
            logger.debug(f"Running {runzeo_path}")
            runzeo_path = str(runzeo_path)
            try:
                subprocess.run([runzeo_path], check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Error running {runzeo_path}: {e}")
                sys.exit(1)
            except KeyboardInterrupt:
                pass
