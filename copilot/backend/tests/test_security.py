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


def test_env_txt_from_notepad_is_read(tmp_path, monkeypatch):
    """Windows Notepad saves '.env' as '.env.txt'; the key must still be found."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("COPILOT_ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env.txt").write_bytes(b"\xef\xbb\xbfANTHROPIC_API_KEY=sk-ant-abc\r\n")
    s = Settings(_env_file=(tmp_path / ".env.txt", tmp_path / ".env"))
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-abc"


def test_ai_key_diagnosis_mentions_commented_line(tmp_path, monkeypatch):
    import app.config as cfg
    from app.main import ai_key_diagnosis

    monkeypatch.setattr(cfg, "BACKEND_DIR", tmp_path)
    (tmp_path / ".env").write_text("COPILOT_MODE=mt5\n# ANTHROPIC_API_KEY=sk-ant-x\n", encoding="utf-8")
    hints = ai_key_diagnosis(Settings(anthropic_api_key=None))
    assert any("# " in h or "Fjern #" in h for h in hints)
