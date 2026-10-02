"""Credential detection uses examples assembled only while tests run."""
from sync_core.utils import SECRET


def test_secret_shapes_are_detected():
    samples = (
        "sk-" + "a" * 24,
        "gh" + "p_" + "a" * 36,
        "github_" + "pat_" + "a" * 36,
        "AK" + "IA" + "A" * 16,
        "Authorization: " + "Bearer " + "a" * 24,
        "eyJ" + "a" * 12 + "." + "eyJ" + "b" * 12 + "." + "c" * 20,
        "api key: " + "a" * 20,
        "password: " + "a" * 20,
        "密码：" + "a" * 20,
        "令牌：" + "a" * 20,
    )
    assert all(SECRET.search(sample) for sample in samples)


def test_ordinary_text_does_not_match():
    samples = (
        "Please rotate the token later.",
        "Set your password in the local credential manager.",
        "api key: example",
        "This is a sample JSON schema with no credentials.",
    )
    assert all(SECRET.search(sample) is None for sample in samples)
