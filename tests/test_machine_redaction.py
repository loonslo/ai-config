import json
import tomllib

import pytest

from sync_core.machine.bundle import BundleError, BundleWriter
from sync_core.machine.privacy import personal_text, private_text, redact, secret_hits


SAMPLE = "sk-" + "a" * 24


@pytest.mark.parametrize('prefix', ['ask-', 'task-', 'risk-', 'flask-'])
def test_normal_word_suffix_is_not_an_api_token(prefix):
    assert not secret_hits(prefix+'questions-if-underspecified.md')


@pytest.mark.parametrize('prefix', ['', ' ', '中文', '"', "'", '=', '/', '\\', '_', '-'])
def test_api_token_at_value_boundaries_is_still_detected(prefix):
    assert any(hit.kind == 'token' and hit.confidence == 'high' for hit in secret_hits(prefix+SAMPLE))


def test_long_identifier_runs_do_not_hide_credentials_or_trigger_suffix_retries():
    padding = 'A'*100_000
    assert not secret_hits(padding)
    raw = padding + '\nSERVICE_PASSWORD="example"\n' + padding
    hits = secret_hits(raw)
    assert len(hits) == 1 and hits[0].kind == 'env_assign' and hits[0].line == 2
    clean, count = redact(raw.encode(), hits)
    assert count == 1 and clean == raw.replace('example','<REDACTED>').encode()
    assert secret_hits('MY_PASSWORD=example')[0].confidence == 'heuristic'


@pytest.mark.parametrize(("value", "kind", "confidence"), [
    (SAMPLE, "token", "high"),
    ("-----BEGIN " + "PRIVATE KEY-----\nbody\n-----END " + "PRIVATE KEY-----", "private_key", "high"),
    ("Authorization: Bearer " + "a" * 24, "bearer", "high"),
    ("eyJ" + "a" * 10 + "." + "b" * 12 + "." + "c" * 12, "jwt", "high"),
    ("https://" + "user:pass" + "@example.org/path", "url_userinfo", "high"),
    ("password: " + "x" * 24, "kv_secret", "heuristic"),
    ("SERVICE_TOKEN=" + "x" * 24, "env_assign", "heuristic"),
])
def test_credential_kinds_have_safe_audit_and_redact(value, kind, confidence):
    hits = secret_hits(value)
    assert any(hit.kind == kind and hit.confidence == confidence for hit in hits)
    output, count = redact(value.encode(), hits)
    assert count >= 1
    assert not private_text(output)
    assert value not in repr(hits)
    assert "start=" not in repr(hits)


def test_email_does_not_block_but_output_hygiene_still_detects_it():
    value = "person" + "@example.org"
    assert personal_text(value)
    assert not private_text(value)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
@pytest.mark.parametrize("prefix", [b"", b"\xff", b"\xff\xfe\xfa"])
def test_binary_encoded_credentials_preserve_surrounding_bytes(encoding, prefix):
    before = ("说明😀\n令" + "牌： ").encode(encoding)
    after = "\n原样保留。".encode(encoding)
    raw = prefix + before + SAMPLE.encode(encoding) + after
    hits = secret_hits(raw)
    result, count = redact(raw, hits)
    assert count == 1
    assert result == prefix + before + "<REDACTED>".encode(encoding) + after
    assert not secret_hits(result)
    assert SAMPLE not in repr(hits)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
def test_encoded_json_bom_and_non_ascii_offsets(encoding):
    import codecs

    bom = {"utf-16-le": codecs.BOM_UTF16_LE, "utf-16-be": codecs.BOM_UTF16_BE,
           "utf-32-le": codecs.BOM_UTF32_LE, "utf-32-be": codecs.BOM_UTF32_BE}[encoding]
    source = {"说明": "😀保持", "API_KEY": SAMPLE, "尾部": "未修改"}
    raw = bom + json.dumps(source, ensure_ascii=False).encode(encoding)
    result, count = redact(raw, secret_hits(raw))
    assert count == 1
    assert json.loads(result) == {**source, "API_KEY": "<REDACTED>"}
    assert not secret_hits(result)


def test_mixed_binary_encodings_redact_each_value():
    raw = b"header\xff" + SAMPLE.encode("utf-16-le") + b"\xffdivider\xff" + SAMPLE.encode() + b"\xffend"
    result, count = redact(raw, secret_hits(raw))
    assert count == 2
    assert result == b"header\xff" + "<REDACTED>".encode("utf-16-le") + b"\xffdivider\xff<REDACTED>\xffend"
    assert not secret_hits(result)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"])
def test_encoded_binary_skill_obeys_bundle_redact_and_skip(tmp_path, encoding):
    raw = b"\xff" + ("保留😀 " + SAMPLE + " 完整尾部").encode(encoding)
    writer = BundleWriter(tmp_path / "redact.zip")
    result, flags = writer.prepare_content(raw, logical_path="codex:main/skills/own/data.bin")
    assert result == b"\xff" + "保留😀 <REDACTED> 完整尾部".encode(encoding)
    assert flags == ["redacted:1"] and writer.flagged[0]["action"] == "redacted"
    writer.add_file("files/codex/main/skills/own/data.bin", result, agent="codex", instance="main",
                    kind="skills_text", logical_path="codex:main/skills/own/data.bin", flags=flags)
    writer.check_privacy(projects=[], exclusions=[], warnings=[])
    skip = BundleWriter(tmp_path / "skip.zip", flagged_policy="skip")
    skipped, flags = skip.prepare_content(raw, logical_path="codex:main/skills/own/data.bin")
    assert skipped is None and flags == [] and skip.flagged[0]["action"] == "skipped"


@pytest.mark.parametrize("escaped", [False, True])
def test_json_unicode_escapes_and_value_quotes_preserved(escaped):
    raw = json.dumps({"API_KEY": SAMPLE, "note": "keep"})
    if escaped:
        raw = raw.replace("sk-", "\\u0073\\u006b\\u002d")
    result, count = redact(raw.encode(), secret_hits(raw))
    assert count == 1
    assert json.loads(result) == {"API_KEY": "<REDACTED>", "note": "keep"}
    assert not private_text(result)


def test_toml_and_policy_matrix_and_invalid_format(tmp_path):
    raw = ('API_KEY = "' + SAMPLE + '"\nnote = "keep"\n').encode()
    writer = BundleWriter(tmp_path / "one.zip")
    result, flags = writer.prepare_content(raw, logical_path="codex:main/config.toml", format_hint=".toml")
    assert tomllib.loads(result.decode())["API_KEY"] == "<REDACTED>"
    assert flags == ["redacted:1"]
    heuristic = ('PASSWORD = "' + "example" + '"').encode()
    third, _ = writer.prepare_content(heuristic, logical_path="skills/third/README.md", origin="third_party")
    assert third == heuristic
    guess, _ = writer.prepare_content(heuristic, logical_path="skills/guess/README.md", origin="third_party", confidence="guess")
    assert guess != heuristic
    builtin, _ = writer.prepare_content(raw, logical_path="skills/.system/SKILL.md", origin="vendor_builtin")
    assert builtin is None
    invalid, _ = writer.prepare_content(('PASSWORD' + ' = ' + str(123456789)).encode(), logical_path="settings.toml", format_hint=".toml")
    assert invalid is None
    assert all("start" not in item and "end" not in item for item in writer.flagged)


def test_skip_policy_and_cache_guard_rechecks_modified_payload(tmp_path):
    writer = BundleWriter(tmp_path / "skip.zip", flagged_policy="skip")
    data, flags = writer.prepare_content(SAMPLE.encode(), logical_path="codex:main/AGENTS.md")
    assert data is None and not flags
    assert writer.flagged[0]["action"] == "skipped"
    safe = BundleWriter(tmp_path / "safe.zip")
    data, flags = safe.prepare_content(SAMPLE.encode(), logical_path="codex:main/AGENTS.md")
    path = "files/codex/main/AGENTS.md"
    safe.add_file(path, data, agent="codex", instance="main", kind="rules", logical_path="codex:main/AGENTS.md", flags=flags)
    safe.check_privacy(projects=[], exclusions=[], warnings=[])
    safe._files[path] = SAMPLE.encode()
    with pytest.raises(BundleError, match="private content"):
        safe.check_privacy(projects=[], exclusions=[], warnings=[])
