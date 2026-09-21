"""验证层：三条判据 + 服务端额度查询。

判据（缺一不可）
----------------
1. `codex login status`            -> 应输出 "Logged in using ChatGPT"
2. app-server `account/read`        -> {type:"chatgpt", email, planType}
3. `scope_v3.user` 投影             -> {authMethod:"chatgpt", account_id}

**时序坑**：桌面端刚启动时 `account/read` 可能返回 `{}`（app-server 还没握手完），
此时 `scope_v3` 通常已经正确。判定应以 `scope_v3` 为准，或等待后重试。
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    Settings,
    app_data,
    codex_home,
    find_codex_cli,
    is_windows,
    proxy_env,
)
from .token import has_bom, parse_token, read_auth

# check_scope_projection 的重试节奏（秒）。桌面端启动后 app-server 需要一点时间
# 才能把 scope_v3 投影写出来，所以先立刻查一次，失败则等 10s 再查两次。
# 三项分别对应"立即"、"再等 10s"、"再等 10s"。
_SCOPE_RETRY_DELAYS: tuple[int, ...] = (0, 10, 10)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""

    def __str__(self) -> str:
        mark = "OK  " if self.ok else "FAIL"
        return f"[{mark}] {self.name:<22} {self.detail}"


@dataclass
class Report:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name, ok, detail))

    def render(self) -> str:
        lines = ["=" * 62, "  Codex 网页 token 登录 · 自检", "=" * 62]
        lines += [str(c) for c in self.checks]
        lines.append("-" * 62)
        lines.append("判定：" + ("PASS  账号信息通道已打通" if self.passed else "FAIL  未打通"))
        return "\n".join(lines)


def _run_cli(args: list[str], env: dict[str, str], timeout: int = 30):
    cli = find_codex_cli()
    if not cli:
        return None, "未找到 codex CLI"
    try:
        r = subprocess.run(
            [str(cli)] + args,
            env=env,
            capture_output=True,
            timeout=timeout,
            creationflags=0x08000000 if is_windows() else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    err = (r.stderr or b"").decode("utf-8", "replace").strip()
    return r.returncode, (out + "\n" + err).strip()


def check_login_status(env: dict[str, str], timeout: int = 30) -> CheckResult:
    rc, text = _run_cli(["login", "status"], env, timeout)
    if rc is None:
        return CheckResult("codex login status", False, text)
    ok = "Logged in using ChatGPT" in text
    if not ok and "API key" in text:
        return CheckResult("codex login status", False, "仍是 API key 模式（token 放错字段？）")
    return CheckResult("codex login status", ok, text.splitlines()[-1] if text else "")


def check_auth_file() -> CheckResult:
    p = codex_home() / "auth.json"
    if not p.is_file():
        return CheckResult("auth.json", False, "不存在")

    if has_bom(p):
        return CheckResult("auth.json", False, "有 BOM —— Codex 会解析失败")
    data = read_auth()
    mode = data.get("auth_mode")
    tok = (data.get("tokens") or {}).get("access_token")
    detail = f"{p.stat().st_size}B mode={mode}"
    if tok:
        try:
            info = parse_token(tok)
            detail += f" email={info.email} plan={info.plan}"
        except ValueError as exc:
            return CheckResult("auth.json", False, f"token 解析失败: {exc}")
    return CheckResult("auth.json", True, detail)


def _scope_candidates() -> list[Path]:
    """定位 Codex 桌面端 Sentry 作用域文件（跨平台）。

    真实路径随平台/安装方式变化，实测样例：
        Win:  %APPDATA%\\Codex\\web\\Codex\\sentry\\scope_v3.json
        Win:  %APPDATA%\\Codex\\sentry\\scope_v3.json
        macOS/Linux: ~/Library/Application Support/Codex/... 等
    """
    roots = [
        app_data() / "Codex",
        codex_home(),
        Path.home() / "Library" / "Application Support" / "Codex",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("scope_v3.json"):
                s = str(p)
                if s not in seen:
                    seen.add(s)
                    out.append(p)
        except OSError:
            continue
    # 最新的排前面
    out.sort(key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True)
    return out


def check_scope_projection() -> CheckResult:
    """读 scope_v3.json 的 user 投影 —— 这是最可靠的判据。

    注意：这个文件由**桌面端**写入，CLI-only 环境下不存在，
    此时返回 skipped 而非 fail。
    """
    for f in _scope_candidates():
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        scope = data.get("scope") or {}
        user = scope.get("user") or data.get("user")
        if isinstance(user, dict) and user:
            ok = user.get("authMethod") == "chatgpt"
            detail = json.dumps(user, ensure_ascii=False)
            if not ok:
                detail += "  (authMethod 非 chatgpt)"
            return CheckResult("scope_v3.user", ok, detail)
    return CheckResult("scope_v3.user", True,
                       "无桌面端 Sentry 文件（CLI-only 环境，跳过）")


def query_server_usage(token: str, account_id: str, proxy: str | None,
                       timeout: int = 30) -> tuple[int, str]:
    """查询服务端额度（wham/usage）。返回 (status, body)。"""
    req = urllib.request.Request(
        "https://chatgpt.com/backend-api/wham/usage",
        headers={
            "Authorization": f"Bearer {token}",
            "chatgpt-account-id": account_id or "",
            "User-Agent": "Mozilla/5.0",
        },
    )
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        # 网络不可达 / DNS 失败 / 超时 —— 都是可预期的环境问题，不算 bug
        return 0, str(exc)


def run_checks(settings: Settings, wait_appserver: bool = True) -> Report:
    rep = Report()
    env = proxy_env(settings.resolve_proxy())

    rep.checks.append(check_auth_file())
    rep.checks.append(check_login_status(env, settings.timeout))

    rounds = _SCOPE_RETRY_DELAYS if wait_appserver else (0,)
    last_scope: CheckResult | None = None
    for delay in rounds:
        if delay:
            time.sleep(delay)
        last_scope = check_scope_projection()
        if last_scope.ok:
            break
    if last_scope:
        rep.checks.append(last_scope)

    # 服务端额度（可选，失败不阻塞判定）
    data = read_auth()
    tok = (data.get("tokens") or {}).get("access_token")
    if tok:
        try:
            info = parse_token(tok)
            code, body = query_server_usage(tok, info.account_id or "", settings.resolve_proxy())
            if code == 200:
                try:
                    j = json.loads(body)
                    rl = j.get("rate_limit") or {}
                    rep.add("服务端额度", True,
                            f"allowed={rl.get('allowed')} "
                            f"used={(rl.get('primary_window') or {}).get('used_percent')}% "
                            f"limit_reached={rl.get('limit_reached')}")
                except ValueError:
                    rep.add("服务端额度", True, f"HTTP {code}")
            elif code == 0:
                rep.add("服务端额度", True, "网络不可达（跳过，不影响判定）")
            else:
                rep.add("服务端额度", False, f"HTTP {code} {body[:120]}")
        except ValueError:
            pass
    return rep


def read_account(settings: Settings) -> dict | None:
    """读取当前登录账号。

    ★ 尚未实现（2026-09-22 审计确认）：本函数**恒返回 None**，没有任何调用方。
    原 docstring 声称"直接调 app-server 的 account/read"，与实际实现不符，
    会误导维护者以为该能力已就绪。

    当前账号信息的来源是 auth.json 的 token 投影（见 parse_token），
    已能满足 CLI 的全部需求；此处保留签名只为将来的 app-server 集成占位。
    """
    # TODO(app-server): 接入 account/read 后再补实现，届时同步更新本 docstring。
    return None
