import json
import subprocess
import sys


def test_inspects_mx_and_buildout_without_a_plonex_project_or_changes(tmp_path):
    (tmp_path / "mx.ini").write_text("""[settings]
requirements-in = requirements.txt
version-overrides =
    zope.sendmail==7.2
[my.addon]
url = https://user:secret@example.org/my.addon.git
branch = fix
extras = test
""")
    (tmp_path / "buildout.cfg").write_text("""[buildout]
extends = https://example.org/versions.cfg
parts = zeo custom
[zeo]
recipe = plone.recipe.zeoserver
[custom]
recipe = my.unknown.recipe
[sources]
my.addon = git https://user:password@example.org/my.addon.git
""")
    before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.iterdir()
        if p.is_file()
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plonex.cli",
            "--target",
            str(tmp_path),
            "project",
            "inspect-legacy",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert {"mxdev source", "buildout recipe", "buildout source"} <= {
        item["kind"] for item in report["findings"]
    }
    assert any("plonex db" in item.get("suggestion", "") for item in report["findings"])
    assert any(
        "review its behavior manually" in item.get("suggestion", "")
        for item in report["findings"]
    )
    assert "password@" not in result.stdout and "secret@" not in result.stdout
    after = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in tmp_path.iterdir()
        if p.is_file()
    }
    assert before == after
    assert not (tmp_path / "etc").exists()


def test_malformed_legacy_file_is_reported_without_a_traceback(tmp_path):
    (tmp_path / "mx.ini").write_text("broken data\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "plonex.cli",
            "--target",
            str(tmp_path),
            "project",
            "inspect-legacy",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["findings"][0]["severity"] == "error"
    assert "Traceback" not in result.stderr


def test_mxdev_generated_files_can_be_consumed_without_rewriting_them(tmp_path):
    from plonex.services.install import InstallService

    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/plonex.yml").write_text(
        "plonex_base_constraint: constraints-mxdev.txt\n"
        'pip_requirements:\n  - "-r requirements-mxdev.txt"\n'
    )
    requirements = tmp_path / "requirements-mxdev.txt"
    constraints = tmp_path / "constraints-mxdev.txt"
    requirements.write_text("demo==1.2\n")
    constraints.write_text("demo==1.2\n")
    before = requirements.read_bytes(), constraints.read_bytes()
    service = InstallService(target=tmp_path)
    service.make_requirements_txt()
    service.make_constraints_txt()
    assert "-r requirements-mxdev.txt" in service.requirements_txt.read_text()
    assert f"-c {constraints}" in service.constrainst_txt.read_text()
    assert before == (requirements.read_bytes(), constraints.read_bytes())
