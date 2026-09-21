"""JWT 解析 + auth.json 读写。

关键事实（源码级验证见 docs/MECHANISM.md）：
- Codex 读的是嵌套 claim：
    https://api.openai.com/profile . email
    https://api.openai.com/auth    . chatgpt_plan_type / chatgpt_account_id
- Codex 对 tokens 段**只做结构校验，不验签**。
- 写入必须是 UTF-8 **无 BOM**（PowerShell 5.1 的 Set-Content -Encoding UTF8 会写 BOM，
  导致 Codex 报 `expected value at line 1 column 1`）。
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .config import auth_path, codex_home

CLAIM_AUTH = "https://api.openai.com/auth"
CLAIM_PROFILE = "https://api.openai.com/profile"

_JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")


@dataclass
class TokenInfo:
    raw: str
    email: str | None
    name: str | None
    plan: str | None
    account_id: str | None
    user_id: str | None
    expires_at: int | None
    issued_at: int | None
    client_id: str | None
    issuer: str | None

    @property
    def expires_in_hours(self) -> float | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - time.time()) / 3600.0

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= time.time()

    def summary(self) -> str:
        lines = [
            f"email      = {self.email}",
            f"plan       = {self.plan}",
            f"account_id = {self.account_id}",
        ]
        if self.name:
            lines.append(f"name       = {self.name}")
        if self.expires_at:
            exp = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.expires_at))
            lines.append(f"有效期     = {exp}（剩 {self.expires_in_hours:.1f} 小时）")
        return "\n".join(lines)


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * ((4 - len(seg) % 4) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def is_jwt(token: str) -> bool:
    return bool(_JWT_RE.match(token.strip()))


def parse_token(token: str) -> TokenInfo:
    """解析 accessToken。非 JWT 或结构异常时抛 ValueError。"""
    token = token.strip().lstrip("\ufeff")
    if not is_jwt(token):
        raise ValueError("不是合法的 JWT（应为三段 base64url，以 . 分隔）")

    try:
        payload = json.loads(_b64url_decode(token.split(".")[1]).decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"JWT payload 解码失败: {exc}") from exc

    auth = payload.get(CLAIM_AUTH) or {}
    profile = payload.get(CLAIM_PROFILE) or {}

    email = profile.get("email") or payload.get("email")
    if not email:
        # email 是必需的：Codex 靠它渲染账号信息
        raise ValueError(
            "token 里没有 email claim —— 这不是 ChatGPT 网页 session token。"
            "请确认用的是 /api/auth/session 的 accessToken。"
        )

    return TokenInfo(
        raw=token,
        email=email,
        name=profile.get("name"),
        plan=auth.get("chatgpt_plan_type") or payload.get("plan_type"),
        account_id=auth.get("chatgpt_account_id") or auth.get("account_id"),
        user_id=auth.get("user_id") or auth.get("chatgpt_user_id"),
        expires_at=payload.get("exp"),
        issued_at=payload.get("iat"),
        client_id=payload.get("client_id"),
        issuer=payload.get("iss"),
    )


# --------------------------------------------------------------------------
# auth.json 读写
# --------------------------------------------------------------------------
def read_auth() -> dict:
    p = auth_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def has_bom(path: Path) -> bool:
    try:
        return path.read_bytes()[:3] == b"\xef\xbb\xbf"
    except OSError:
        return False


def _email_of(auth_dict: dict) -> str | None:
    """从 auth 字典里尽力取出 email（用于判断 refresh_token 归属）。"""
    tk = auth_dict.get("tokens") or {}
    for key in ("access_token", "id_token"):
        raw = tk.get(key)
        if not isinstance(raw, str) or raw.count(".") != 2:
            continue
        try:
            payload = json.loads(_b64url_decode(raw.split(".")[1]))
        except (ValueError, KeyError):
            continue
        profile = payload.get(CLAIM_PROFILE) or {}
        if profile.get("email"):
            return profile["email"]
    return None


def _borrow_refresh_token(want_email: str | None = None) -> tuple[str | None, str | None]:
    """从历史备份里借一个 refresh_token。

    返回 (refresh_token, 来源说明)。

    ★ 为什么必须区分账号（2026-09-22 实测修正）：
        Codex 的 Rust 侧（auth/manager.rs）会拿 tokens.refresh_token 去
        https://auth.openai.com/oauth/token 换新 access_token，从而保持登录态。
        如果借来的 refresh_token 属于**别的账号**，刷新要么换回错账号的票、
        要么直接进 not_refreshable_auth 状态。
        所以优先借**同账号**的；借不到再退而求其次，并如实告知。
    """
    home = codex_home()
    if not home.is_dir():
        return None, None

    same: tuple[str, str] | None = None
    other: tuple[str, str] | None = None

    for f in sorted(home.glob("auth.json*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.name == "auth.json" or ("bak" not in f.name and f.suffix != ".bak"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        rt = (d.get("tokens") or {}).get("refresh_token")
        if not rt:
            continue
        owner = _email_of(d)
        candidate = (rt, f"{f.name}（{owner or '未知账号'}）")
        if want_email and owner and owner.lower() == want_email.lower():
            if same is None:
                same = candidate
        elif other is None:
            other = candidate

    if same:
        return same
    if other:
        return other
    return None, None


def build_chatgpt_auth(info: TokenInfo, refresh_token: str | None = None) -> dict:
    """构造 chatgpt 形态的 auth.json。

    为什么 id_token 也填 token 本身：
        Codex 要求 id_token 是 string（填 null 会报 `invalid type: null`），
        但它不做任何语义校验，所以同一个 JWT 可以同时占 id_token / access_token。

    refresh_token：
        优先用调用方显式传入的；否则从备份里借（优先同账号）。
        借不到就留空字符串 —— 首次登录不受影响，只是到期后无法自动续期。
    """
    rt = refresh_token if refresh_token is not None else _borrow_refresh_token(info.email)[0]
    return {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": info.raw,
            "access_token": info.raw,
            "refresh_token": rt or "",
            "account_id": info.account_id,
        },
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S.") + "000000000Z",
    }


def atomic_write_auth(data: dict) -> Path:
    """原子写入 auth.json，保证无 BOM。"""
    p = auth_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    # 关键：encoding="utf-8" 不带 BOM，newline="\n"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)
    if has_bom(p):
        raise RuntimeError("写入后检测到 BOM —— 这会让 Codex 解析失败")
    return p


def backup_auth(tag: str = "weblogin", keep: int = 20) -> Path | None:
    p = auth_path()
    if not p.is_file():
        return None
    ts = time.strftime("%Y%m%d_%H%M%S")
    dst = p.with_name(f"auth.json.{tag}-{ts}.bak")
    shutil.copy2(p, dst)
    _prune_backups(keep)
    return dst


def list_backups() -> list[Path]:
    home = codex_home()
    if not home.is_dir():
        return []
    out = [f for f in home.glob("auth.json*.bak") if f.is_file()]
    return sorted(out, key=lambda x: x.stat().st_mtime, reverse=True)


def _prune_backups(keep: int) -> None:
    for old in list_backups()[keep:]:
        with contextlib.suppress(OSError):
            old.unlink()


def restore_backup(keyword: str) -> Path:
    """按关键词恢复备份（匹配文件名，取最新一个）。"""
    cands = [b for b in list_backups() if keyword.lower() in b.name.lower()]
    if not cands:
        raise FileNotFoundError(f"没有匹配 '{keyword}' 的备份")
    src = cands[0]
    backup_auth(tag="pre-restore")
    shutil.copy2(src, auth_path())
    if has_bom(auth_path()):
        # 备份本身带 BOM 时清掉
        raw = auth_path().read_bytes()
        auth_path().write_bytes(raw.replace(b"\xef\xbb\xbf", b"", 1))
    return src
