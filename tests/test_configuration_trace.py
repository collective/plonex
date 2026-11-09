from plonex.base import BaseService
from plonex.services.runwsgi import RunWSGI

import yaml


def configure(root, values, name="plonex.yml"):
    path = root / "etc" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(values, sort_keys=False))
    return path


def test_trace_follows_profiles_local_files_explicit_files_and_cli(tmp_path):
    base = tmp_path / "profiles" / "base"
    child = tmp_path / "profiles" / "dev"
    first = configure(base, {"http_port": 8000})
    second = configure(child, {"profiles": ["../base"], "http_port": 8001})
    main = configure(tmp_path, {"profiles": ["profiles/dev"], "http_port": 8002})
    local = configure(tmp_path, {"http_port": 8003}, "plonex.local.yml")
    extra = configure(tmp_path, {"http_port": 8004}, "extra.yml")
    service = BaseService(
        target=tmp_path, config_files=[extra], cli_options={"http_port": 9000}
    )
    (row,) = service.configuration_trace.rows("http_port")
    assert row["value"] == 9000
    assert [event["source"] for event in row["history"]] == [
        str(first),
        str(second),
        str(main),
        str(local),
        str(extra),
        "CLI overrides",
    ]
    assert [event["value"] for event in row["history"]] == [
        8000,
        8001,
        8002,
        8003,
        8004,
        9000,
    ]


def test_prefix_merges_replacements_and_removals_preserve_definition_history(tmp_path):
    configure(
        tmp_path,
        {
            "sources": {"kept": {"repo": "a"}, "removed": {"repo": "b"}},
            "pip_requirements": ["first"],
        },
    )
    configure(
        tmp_path,
        {"-sources": ["removed"], "+pip_requirements": ["second"]},
        "plonex.local.yml",
    )
    service = BaseService(target=tmp_path)
    assert service.options["pip_requirements"] == ["first", "second"]
    assert "removed" not in service.options["sources"]
    rows = {row["key"]: row for row in service.configuration_trace.rows("sources")}
    assert rows["sources.removed"]["active"] is False
    assert rows["sources.removed.repo"]["history"][-1]["operation"] == "removed"
    assert len(rows["sources.kept.repo"]["history"]) == 1
    assert (
        service.configuration_trace.rows("pip_requirements")[0]["history"][-1][
            "operation"
        ]
        == "append"
    )


def test_derived_values_and_secrets_are_redacted_at_every_layer(tmp_path):
    configure(
        tmp_path,
        {
            "port": 8000,
            "http_url": "http://localhost:{{ port }}",
            "API_TOKEN": "old-secret",
            "public_copy": "{{ API_TOKEN }}",
            "copy_of_copy": "{{ public_copy }}",
            "environment_vars": {
                "TOKEN": "env-secret",
                "CACHE": "{{ var_folder }}/cache",
            },
        },
    )
    configure(tmp_path, {"API_TOKEN": "new-secret", "port": 9000}, "plonex.local.yml")
    service = BaseService(target=tmp_path)
    assert service.options["http_url"] == "http://localhost:9000"
    rows = service.configuration_trace.rows(nested=True)
    rendered = repr(rows)
    for secret in ("old-secret", "new-secret", "env-secret"):
        assert secret not in rendered
    by_key = {row["key"]: row for row in rows}
    assert by_key["http_url"]["references"] == ["port"]
    assert by_key["copy_of_copy"]["value"] == "[redacted]"
    assert isinstance(by_key["environment_vars"]["value"], dict)
    assert by_key["environment_vars.CACHE"]["value"] == str(tmp_path / "var" / "cache")


def test_trace_includes_zope_derived_defaults(tmp_path):
    configure(tmp_path, {})
    service = RunWSGI(target=tmp_path)
    row = service.configuration_trace.rows("zeo_address")[0]
    assert row["value"] == str(tmp_path / "var" / "zeosocket.sock")
    assert row["references"] == ["var_folder"]
    assert row["source"] == "ZopeBasedService defaults"


def test_merge_does_not_mutate_raw_inputs_or_previous_values(tmp_path):
    service = BaseService(target=tmp_path)
    before = {"items": ["one"], "mapping": {"a": 1}}
    incoming = {"+items": ["two"], "+mapping": {"b": 2}}
    result = service._merge_options_with_prefixes(before, incoming)
    assert result == {"items": ["one", "two"], "mapping": {"a": 1, "b": 2}}
    assert before == {"items": ["one"], "mapping": {"a": 1}}
    assert incoming == {"+items": ["two"], "+mapping": {"b": 2}}
