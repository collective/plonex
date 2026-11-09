"""Offline, verified snapshots of a FileStorage and its blob directory."""

from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def files(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Blob snapshot contains a symbolic link: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = checksum(path)
        elif not path.is_dir():
            raise ValueError(f"Blob snapshot contains an unsupported entry: {path}")
    return result


@contextmanager
def storage_lock(path):
    """Use the same flock held by ZODB FileStorage for the entire backup."""
    lock = Path(str(path) + ".lock")
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "Database is in use. Stop ZEO and other FileStorage writers "
                "before backup."
            ) from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def repozo(executable, *arguments):
    try:
        subprocess.run([str(executable), *map(str, arguments)], check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"repozo failed with exit status {error.returncode}"
        ) from error


def create_backup(service):
    database = service.var_folder / "filestorage/Data.fs"
    blob = Path(service.options["blobstorage"])
    if not blob.is_absolute():
        blob = service.target / blob
    if not database.is_file():
        raise FileNotFoundError(f"Database does not exist: {database}")
    if not blob.is_dir() or blob.is_symlink():
        raise ValueError(f"Blob storage must be an existing directory: {blob}")
    repozo_bin = service.virtualenv_dir / "bin/repozo"
    root = service.var_folder / "backups"
    if root.resolve().is_relative_to(blob.resolve()) or blob.resolve().is_relative_to(
        root.resolve()
    ):
        raise ValueError("Backup and blob storage directories must not overlap")
    if database.resolve().is_relative_to(blob.resolve()):
        raise ValueError("The database cannot be inside blob storage")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".backup-", dir=root))
    try:
        with storage_lock(database):
            # Reject links before copying, and again when recording the copy.
            before = files(blob)
            repository = staging / "repozo"
            repository.mkdir(mode=0o700)
            repozo(repozo_bin, "-BvFz", "-r", repository, "-f", database)
            repozo(repozo_bin, "-V", "-r", repository)
            shutil.copytree(blob, staging / "blobstorage", symlinks=True)
            blob_hashes = files(staging / "blobstorage")
            if blob_hashes != before or files(blob) != before:
                raise ValueError(
                    "Blob storage changed during backup; retry after stopping "
                    "all blob writers."
                )
            manifest = {
                "schema": 1,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "blobs": blob_hashes,
                "database": "repozo",
                "note": "Offline snapshot; coordinate any other blob writers.",
            }
            (staging / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
        name = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
            + uuid.uuid4().hex[:8]
        )
        destination = root / name
        staging.rename(destination)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def restore_backup(service, *, destination, backup=None):
    """Recover only into a new directory, never replacing an existing target."""
    if not destination:
        raise ValueError(
            "Restore requires --to NEW_DIRECTORY. It never replaces a live database."
        )
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Restore destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise ValueError(
            f"Restore destination parent does not exist: {destination.parent}"
        )
    root = service.var_folder / "backups"
    if backup:
        bundle = Path(backup).expanduser().absolute()
    else:
        bundles = (
            sorted(
                path
                for path in root.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            )
            if root.is_dir()
            else []
        )
        if not bundles:
            raise ValueError("No snapshot backups found. Choose one with --from.")
        bundle = bundles[-1]
    manifest_path = bundle / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read backup manifest: {manifest_path}") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != 1
        or not isinstance(manifest.get("blobs"), dict)
    ):
        raise ValueError("Invalid backup manifest")
    blobs = bundle / "blobstorage"
    repository = bundle / "repozo"
    if (
        not blobs.is_dir()
        or blobs.is_symlink()
        or not repository.is_dir()
        or repository.is_symlink()
    ):
        raise ValueError("Backup is missing its blob storage or repozo repository")
    if files(blobs) != manifest["blobs"]:
        raise ValueError("Backup blob checksums do not match the manifest")
    if bundle.resolve() == destination.resolve() or bundle.resolve().is_relative_to(
        destination.resolve()
    ):
        raise ValueError("Restore destination cannot contain the backup")
    stage = Path(tempfile.mkdtemp(prefix=".plonex-restore-", dir=destination.parent))
    try:
        repozo(
            service.virtualenv_dir / "bin/repozo",
            "-Rvw",
            "-r",
            repository,
            "-o",
            stage / "Data.fs",
        )
        if not (stage / "Data.fs").is_file():
            raise ValueError("repozo did not produce a database")
        shutil.copytree(blobs, stage / "blobstorage", symlinks=True)
        if files(stage / "blobstorage") != manifest["blobs"]:
            raise ValueError("Restored blob checksums do not match the manifest")
        # Reserve the directory without replacing an existing path. A failed
        # publish leaves the new destination for inspection rather than deleting it.
        destination.mkdir(mode=0o700)
        os.link(stage / "Data.fs", destination / "Data.fs")
        (stage / "blobstorage").rename(destination / "blobstorage")
        return destination
    finally:
        shutil.rmtree(stage, ignore_errors=True)
