"""集中配置与路径发现。

设计原则：
- **零硬编码**：所有路径都通过环境变量 / 平台默认值 / 运行时发现得到。
- 用户可通过 env 或 CLI 覆盖任何一项。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# 环境变量名（用户覆盖入口）
# --------------------------------------------------------------------------
ENV_CODEX_HOME = "CODEX_HOME"
ENV_PROXY = "CODEX_WEB_LOGIN_PROXY"
ENV_LAUNCHER = "CODEX_WEB_LOGIN_LAUNCHER"
ENV_CODEX_APP = "CODEX_WEB_LOGIN_APP"

DEFAULT_PROXY_CANDIDATES = (
    "http://127.0.0.1:7890",
    "http://127.0.0.1:10809",
    "http://127.0.0.1:11119",
    "http://127.0.0.1:8080",
)


def codex_home() -> Path:
    """Codex 配置目录。优先级：env > ~/.codex"""
    env = os.environ.get(ENV_CODEX_HOME)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".codex"


def auth_path() -> Path:
    return codex_home() / "auth.json"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def local_app_data() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return Path.home() / ".local" / "share"


def app_data() -> Path:
    if is_windows():
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return Path.home() / ".config"


# --------------------------------------------------------------------------
# Codex 安装发现（不硬编码盘符）
# --------------------------------------------------------------------------
def find_codex_cli() -> Path | None:
    """定位 codex CLI 可执行文件，按平台惯例依次探测。"""
    names = ["codex.exe", "codex.cmd", "codex"] if is_windows() else ["codex"]
    roots: list[Path] = []

    if is_windows():
        roots += [
            local_app_data() / "Programs" / "Codex" / "resources",
            local_app_data() / "Programs" / "Codex",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Codex" / "resources",
        ]
    else:
        roots += [
            Path("/usr/local/lib/codex"),
            Path("/opt/codex"),
            Path.home() / ".local" / "lib" / "codex",
        ]

    for root in roots:
        for name in names:
            cand = root / name
            if cand.is_file():
                return cand

    # 最后回退到 PATH
    from shutil import which

    for name in names:
        found = which(name)
        if found:
            return Path(found)
    return None


def find_codex_app() -> Path | None:
    """定位 Codex 桌面端主程序（用于无 launcher 时兜底启动）。"""
    env = os.environ.get(ENV_CODEX_APP)
    if env:
        p = Path(env).expanduser()
        return p if p.exists() else None

    names = (
        ["ChatGPT.exe", "Codex.exe", "LaunchCodex.exe"]
        if is_windows()
        else ["Codex", "ChatGPT"]
    )
    roots: list[Path] = []
    if is_windows():
        roots += [
            local_app_data() / "Programs" / "Codex",
            local_app_data() / "Programs" / "ChatGPT",
        ]
    else:
        roots += [
            Path("/Applications/Codex.app/Contents/MacOS"),
            Path("/Applications/ChatGPT.app/Contents/MacOS"),
        ]

    for root in roots:
        for name in names:
            cand = root / name
            if cand.is_file():
                return cand
    return None


@dataclass
class Settings:
    """一次运行的全部可变项。所有字段都可被 env / CLI 覆盖。"""

    proxy: str | None = None
    launcher: Path | None = None
    codex_app: Path | None = None
    no_restart: bool = False
    timeout: int = 30
    launch_wait: int = 9
    backups: int = 20
    _warnings: list[str] = field(default_factory=list, repr=False)

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls()
        s.proxy = os.environ.get(ENV_PROXY) or None
        lch = os.environ.get(ENV_LAUNCHER)
        if lch:
            s.launcher = Path(lch).expanduser()
        return s

    def resolve_proxy(self) -> str | None:
        """未显式指定时，自动探测本机常见代理端口。"""
        if self.proxy:
            return self.proxy
        import socket

        for cand in DEFAULT_PROXY_CANDIDATES:
            try:
                host_port = cand.split("//", 1)[1]
                host, port = host_port.rsplit(":", 1)
                with socket.create_connection((host, int(port)), timeout=0.35):
                    return cand
            except OSError:
                continue
        return None


def proxy_env(proxy: str | None) -> dict[str, str]:
    """构造给子进程用的代理环境变量。"""
    env = dict(os.environ)
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
    env.setdefault("NO_PROXY", "localhost,127.0.0.1")
    env.setdefault("no_proxy", "localhost,127.0.0.1")
    return env


# --------------------------------------------------------------------------
# 用户自定义启动器（launchers.json）——解决"每个人启动方式不同"
# --------------------------------------------------------------------------
def launchers_file() -> Path:
    return codex_home() / "web-login-launchers.json"


def load_user_launchers() -> list[str]:
    """读取用户自定义启动器列表（按顺序尝试）。"""
    p = launchers_file()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("launchers", [])
    if not isinstance(data, list):
        return []
    return [str(x) for x in data if isinstance(x, (str, os.PathLike))]
