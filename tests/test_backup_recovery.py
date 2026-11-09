from pathlib import Path
from plonex.files import read_only
from plonex.services.zeoserver import ZeoServer
from unittest import mock
from ZODB import DB
from ZODB.blob import Blob
from ZODB.FileStorage import FileStorage

import fcntl
import pytest
import sys
import transaction


@pytest.fixture
def project(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text("{}\n")
    (tmp_path / ".venv").symlink_to(Path(sys.prefix))
    return tmp_path


def make_database(project):
    store = project / "var/filestorage/Data.fs"
    store.parent.mkdir(parents=True)
    blobs = project / "var/blobstorage"
    blobs.mkdir()
    storage = FileStorage(str(store), blob_dir=str(blobs))
    db = DB(storage)
    conn = db.open()
    conn.root.answer = 42
    conn.root.upload = Blob()
    with conn.root.upload.open("w") as blob:
        blob.write(b"a real file")
    transaction.commit()
    conn.close()
    db.close()
    return store, blobs


def service(project):
    with read_only():
        return ZeoServer(target=project)


def test_real_backup_and_restore_include_database_and_blobs(project):
    store, _ = make_database(project)
    worker = service(project)
    snapshot = worker.run_backup()
    destination = project / "recovered"
    assert worker.run_restore(destination=destination, backup=snapshot) == destination
    assert store.exists()
    storage = FileStorage(
        str(destination / "Data.fs"),
        read_only=True,
        blob_dir=str(destination / "blobstorage"),
    )
    db = DB(storage)
    conn = db.open()
    assert conn.root.answer == 42
    with conn.root.upload.open("r") as blob:
        assert blob.read() == b"a real file"
    conn.close()
    db.close()
    with pytest.raises(ValueError, match="already exists"):
        worker.run_restore(destination=destination, backup=snapshot)


def test_backup_refuses_active_filestorage_and_missing_blobs(project):
    store, blobs = make_database(project)
    worker = service(project)
    with Path(str(store) + ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="Database is in use"):
            worker.run_backup()
    import shutil

    shutil.rmtree(blobs)
    with pytest.raises(ValueError, match="Blob storage"):
        worker.run_backup()
    assert not blobs.exists()


def test_restore_detects_tampered_blob_before_creating_destination(project):
    _, _ = make_database(project)
    worker = service(project)
    snapshot = worker.run_backup()
    manifest = __import__("json").loads((snapshot / "manifest.json").read_text())
    blob_name = next(name for name in manifest["blobs"] if name.endswith(".blob"))
    stored_blob = snapshot / "blobstorage" / blob_name
    stored_blob.chmod(0o600)
    stored_blob.write_bytes(b"corrupt")
    destination = project / "recovered"
    with pytest.raises(ValueError, match="checksums"):
        worker.run_restore(destination=destination, backup=snapshot)
    assert not destination.exists()


def test_restore_failure_does_not_publish_partial_database(project):
    make_database(project)
    worker = service(project)
    snapshot = worker.run_backup()
    destination = project / "recovered"
    with mock.patch(
        "plonex.services.zeoserver.backup.repozo", side_effect=ValueError("bad backup")
    ):
        with pytest.raises(ValueError, match="bad backup"):
            worker.run_restore(destination=destination, backup=snapshot)
    assert not destination.exists()
