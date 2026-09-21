"""进程管理：关闭 / 等待 Codex 相关进程。

必须在写 auth.json 前杀干净进程，否则：
- 桌面端退出时会把内存里的旧 auth 回写，覆盖我们的修改；
- cookie / 配置文件被独占锁定。
"""

from __future__ import annotations

import subprocess
import time

from .config import is_windows

# 覆盖桌面端、CLI、第三方管理器（管理器通常是宿主守护进程，要先杀它）
PROCESS_NAMES = (
    "ChatGPT.exe",
    "Codex.exe",
    "codex.exe",
    "codex-app-manager.exe",
    "LaunchCodex.exe",
)

# 管理器排在前面 —— 它是拉起者，先杀它才能断掉"杀完又被拉起"的循环
_KILL_ORDER = (
    "codex-app-manager.exe",
    "LaunchCodex.exe",
    "ChatGPT.exe",
    "Codex.exe",
    "codex.exe",
)


def _tasklist() -> list[str]:
    try:
        r = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=20,
            creationflags=0x08000000 if is_windows() else 0,
        )
        return (r.stdout or b"").decode("gbk", "replace").splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def running_processes() -> list[str]:
    """返回当前在跑的、与我们相关的进程名。"""
    alive = []
    text = "\n".join(_tasklist()).lower()
    for name in PROCESS_NAMES:
        if name.lower() in text:
            alive.append(name)
    return alive


def kill_all(timeout: float = 20.0) -> list[str]:
    """结束所有相关进程，返回实际被杀掉的名单。"""
    if not is_windows():
        # POSIX 兜底
        for name in ("codex", "ChatGPT", "Codex"):
            subprocess.run(["pkill", "-f", name], capture_output=True)
        time.sleep(1.0)
        return []

    killed: list[str] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive = running_processes()
        if not alive:
            break
        for name in _KILL_ORDER:
            if name in alive:
                subprocess.run(
                    ["taskkill", "/F", "/IM", name],
                    capture_output=True,
                    creationflags=0x08000000,
                )
                killed.append(name)
        time.sleep(0.8)
    return killed


def wait_until_gone(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not running_processes():
            return True
        time.sleep(0.5)
    return not running_processes()
