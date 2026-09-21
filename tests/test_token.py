"""token 解析与 auth.json 读写的单元测试。

不需要真实凭据 —— 所有 JWT 都是现场构造的。
"""

from __future__ import annotations

import base64
import json
import time

import pytest

from codex_web_login.token import (
    TokenInfo,
    build_chatgpt_auth,
    has_bom,
    is_jwt,
    parse_token,
)


def make_jwt(payload: dict, header: dict | None = None) -> str:
    """构造一个结构合法、但签名是假串的 JWT（用于测试）。"""

    def seg(d: dict) -> str:
        raw = json.dumps(d, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    h = header or {"alg": "RS256", "typ": "JWT"}
    return f"{seg(h)}.{seg(payload)}.FAKESIGNATURE"


def sample_payload(email="tester@example.com", plan="plus",
                   account_id="acct-1234", exp_offset=86400 * 10):
    now = int(time.time())
    return {
        "aud": ["https://api.openai.com/v1"],
        "client_id": "app_TESTCLIENT",
        "iss": "https://auth.openai.com",
        "exp": now + exp_offset,
        "iat": now,
        "https://api.openai.com/auth": {
            "chatgpt_account_id": account_id,
            "chatgpt_plan_type": plan,
            "user_id": "user-abc",
        },
        "https://api.openai.com/profile": {
            "email": email,
            "name": "测试用户",
        },
    }


# --------------------------------------------------------------------------
# is_jwt / parse_token
# --------------------------------------------------------------------------
def test_is_jwt_accepts_three_segment():
    assert is_jwt(make_jwt({"a": 1}))
    assert is_jwt("aaa.bbb.ccc")
    assert is_jwt("a-b_c.d-e_f.g-h_i")


@pytest.mark.parametrize("bad", ["", "abc", "a.b", "a.b.c.d", "not a jwt", "a..c"])
def test_is_jwt_rejects_malformed(bad):
    assert not is_jwt(bad)


def test_parse_token_reads_nested_claims():
    tok = make_jwt(sample_payload())
    info = parse_token(tok)
    assert isinstance(info, TokenInfo)
    assert info.email == "tester@example.com"
    assert info.plan == "plus"
    assert info.account_id == "acct-1234"
    assert info.name == "测试用户"
    assert info.client_id == "app_TESTCLIENT"
    assert not info.is_expired


def test_parse_token_strips_whitespace_and_bom():
    tok = make_jwt(sample_payload())
    assert parse_token("\ufeff  " + tok + "\n").email == "tester@example.com"


def test_parse_token_expired():
    tok = make_jwt(sample_payload(exp_offset=-3600))
    info = parse_token(tok)
    assert info.is_expired
    assert info.expires_in_hours < 0


def test_parse_token_rejects_non_jwt():
    with pytest.raises(ValueError, match="不是合法的 JWT"):
        parse_token("hello-world")


def test_parse_token_rejects_missing_email():
    """没有 email claim 说明不是 ChatGPT session token —— 必须拒绝。"""
    p = sample_payload()
    del p["https://api.openai.com/profile"]
    with pytest.raises(ValueError, match="没有 email"):
        parse_token(make_jwt(p))


def test_parse_token_rejects_bad_base64_payload():
    with pytest.raises(ValueError):
        parse_token("aaa.!!!not-base64!!!.ccc")


# --------------------------------------------------------------------------
# build_chatgpt_auth
# --------------------------------------------------------------------------
def test_build_auth_shape():
    info = parse_token(make_jwt(sample_payload()))
    d = build_chatgpt_auth(info, refresh_token="rt-placeholder")
    assert d["auth_mode"] == "chatgpt"
    assert d["OPENAI_API_KEY"] is None
    assert d["tokens"]["id_token"] == info.raw
    assert d["tokens"]["access_token"] == info.raw
    assert d["tokens"]["account_id"] == "acct-1234"
    assert d["tokens"]["refresh_token"] == "rt-placeholder"
    assert "last_refresh" in d


def test_build_auth_account_id_switches_per_token():
    """换账号时必须无串号 —— account_id 跟着 token 走。"""
    a = build_chatgpt_auth(parse_token(make_jwt(sample_payload(account_id="AAA"))))
    b = build_chatgpt_auth(parse_token(make_jwt(sample_payload(account_id="BBB"))))
    assert a["tokens"]["account_id"] == "AAA"
    assert b["tokens"]["account_id"] == "BBB"


def test_auth_json_roundtrip_no_bom(tmp_path, monkeypatch):
    """写入的 auth.json 必须无 BOM，否则 Codex 报 line 1 column 1。"""
    import codex_web_login.token as token_mod

    target = tmp_path / "auth.json"
    monkeypatch.setattr(token_mod, "auth_path", lambda: target)

    info = parse_token(make_jwt(sample_payload()))
    p = token_mod.atomic_write_auth(build_chatgpt_auth(info, "rt"))

    raw = p.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    assert raw[:1] == b"{"
    assert not has_bom(p)

    reloaded = json.loads(raw.decode("utf-8"))
    assert reloaded["tokens"]["account_id"] == "acct-1234"
