from plonex.cli.dependencies import _run_service_dependencies


def test_template_paths_follow_each_defining_file(tmp_path, monkeypatch):
    project = tmp_path / "project"
    etc = project / "etc"
    etc.mkdir(parents=True)
    profile = project / "profile" / "etc"
    profile.mkdir(parents=True)
    (profile / "plonex.yml").write_text(
        "services:\n  - template:\n      run_for: supervisor\n"
        "      source: file:profile%20template.j2\n"
        "      target: profile.out\n"
    )
    (profile / "profile template.j2").write_text("profile")
    (etc / "plonex.yml").write_text("profiles: [profile]\n")
    (etc / "plonex.local.yml").write_text(
        "+services:\n  - template:\n      run_for: supervisor\n"
        "      source: project.j2\n"
        "      target: file:project.out\n"
    )
    (etc / "project.j2").write_text("project")
    monkeypatch.chdir(tmp_path)

    _run_service_dependencies(project, "supervisor")

    assert (profile / "profile.out").read_text() == "profile"
    assert (etc / "project.out").read_text() == "project"
