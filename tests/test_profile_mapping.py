from plonex.base import BaseService
from plonex.files import read_only
from plonex.services.install import InstallService
from plonex.services.profile import ProfileService
from unittest import mock

import pytest
import subprocess
import yaml


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.org")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    (repo / "base/etc/requirements.d").mkdir(parents=True)
    (repo / "base/etc/plonex.yml").write_text(
        "profiles: ['../shared']\nhttp_port: 1234\n"
    )
    (repo / "base/etc/requirements.d/base.txt").write_text("example==1\n")
    (repo / "shared/etc").mkdir(parents=True)
    (repo / "shared/etc/plonex.yml").write_text("nested_option: true\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "first")
    first = git(repo, "rev-parse", "HEAD")
    (repo / "base/etc/plonex.yml").write_text("http_port: 5678\n")
    git(repo, "commit", "-am", "second")
    return repo, first, git(repo, "rev-parse", "HEAD")


def test_mapping_loads_pinned_subdirectory_and_nested_profile(tmp_path, repository):
    repo, first, second = repository
    project = tmp_path / "project"
    (project / "etc").mkdir(parents=True)
    declaration = {"repo": repo.as_uri(), "ref": first, "path": "base"}
    (project / "etc/plonex.yml").write_text(yaml.safe_dump({"profiles": [declaration]}))
    service = BaseService(target=project)
    assert service.plonex_options["http_port"] == 1234
    assert service.plonex_options["nested_option"] is True
    install = InstallService(target=project)
    assert (install.profile_roots[-1] / "etc/requirements.d/base.txt").is_file()
    first_root = ProfileService(target=project, source=declaration).source_path
    with read_only(), mock.patch.object(ProfileService, "execute_command") as execute:
        cached = ProfileService(target=project, source=declaration).source_path
        assert cached == first_root
        execute.assert_not_called()
    other = ProfileService(
        target=project, source={**declaration, "ref": second}
    ).source_path
    assert other != first_root
    assert "5678" in (other / "etc/plonex.yml").read_text()


@pytest.mark.parametrize("path", ["../outside", "/tmp", ""])
def test_mapping_rejects_invalid_paths_before_clone(tmp_path, path):
    service = ProfileService(target=tmp_path, source={"repo": "example", "path": path})
    with mock.patch.object(service, "_clone_remote_source") as clone:
        with pytest.raises(ValueError, match="Profile path"):
            service.source_path
        clone.assert_not_called()


def test_mapping_rejects_symlink_escape(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "escape").symlink_to(tmp_path, target_is_directory=True)
    service = ProfileService(
        target=tmp_path, source={"repo": "example", "path": "escape"}
    )
    with mock.patch.object(service, "_clone_remote_source", return_value=checkout):
        with pytest.raises(ValueError, match="inside the repository"):
            service.source_path


def test_mapping_defaults_to_repository_head(tmp_path, repository):
    repo, _, _ = repository
    root = ProfileService(
        target=tmp_path, source={"repo": repo.as_uri(), "path": "base"}
    ).source_path
    assert "5678" in (root / "etc/plonex.yml").read_text()


def test_uncached_mapping_is_not_cloned_in_read_only_mode(tmp_path):
    service = ProfileService(
        target=tmp_path, source={"repo": "https://example.org/repo.git", "path": "base"}
    )
    with read_only(), mock.patch.object(service, "execute_command") as execute:
        with pytest.raises(ValueError, match="not cached"):
            service.source_path
        execute.assert_not_called()


def test_profile_mapping_cannot_be_used_as_write_destination(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text(
        yaml.safe_dump({"profiles": [{"repo": "https://example.org/repo.git"}]})
    )
    with mock.patch.object(ProfileService, "_clone_remote_source") as clone:
        assert InstallService(target=tmp_path)._resolve_first_profile_root() is None
        clone.assert_not_called()
