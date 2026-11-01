from app.config import Settings
from app.security import OriginPolicy, load_or_create_token, parse_bearer, token_matches


def test_token_created_and_persisted(tmp_path):
    s = Settings(data_dir=tmp_path)
    t1 = load_or_create_token(s)
    t2 = load_or_create_token(s)
    assert t1 == t2 and len(t1) >= 32


def test_token_matching():
    assert token_matches("abc", "abc")
    assert not token_matches("abc", "abd")
    assert not token_matches("abc", None)
    assert parse_bearer("Bearer xyz") == "xyz"
    assert parse_bearer("Basic xyz") is None


def test_origin_policy_pinned():
    p = OriginPolicy(Settings(allowed_extension_ids=["a" * 32]))
    assert p.is_allowed("chrome-extension://" + "a" * 32)
    assert not p.is_allowed("chrome-extension://" + "b" * 32)
    assert not p.is_allowed("https://www.tradingview.com")
    assert not p.is_allowed("https://evil.example")
    assert p.is_allowed("http://localhost:5173")
    assert p.is_allowed(None)


def test_origin_policy_unpinned_accepts_any_extension():
    p = OriginPolicy(Settings(allowed_extension_ids=[]))
    assert p.is_allowed("chrome-extension://" + "b" * 32)
    assert not p.is_allowed("https://evil.example")


def test_non_loopback_host_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")
