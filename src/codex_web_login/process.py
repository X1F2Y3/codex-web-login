"""进程管理：关闭 / 等待 Codex 相关进程。

必须在写 auth.json 前杀干净进程，否则：
- 桌面端退出时会把内存里的旧 auth 回写，覆盖我们的修改；
- cookie / 配置文件被独占锁定。
"""

from __future__ import annotations

import csv
import io
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

# 管理器排在前面 —— 它是拉起者，先杀它才能断掉"杀完又被拉起"的循环。
# 顺序在这里唯一地定义一次；集合本身复用 PROCESS_NAMES，避免两份"事实来源"
# 漂移（改了一处忘了另一处 = 静默漏杀）。
_KILL_ORDER = tuple(
    n for n in ("codex-app-manager.exe", "LaunchCodex.exe") if n in PROCESS_NAMES
) + tuple(n for n in PROCESS_NAMES if n not in ("codex-app-manager.exe", "LaunchCodex.exe"))

# POSIX 兜底的进程名（不带 .exe 后缀）。用 `pkill -x` 做**精确进程名**匹配，
# 不用 `-f`（全命令行正则匹配）——`-f` 会顺带命中命令行里恰好含该词的其他进程，
# 属于误杀。
_POSIX_NAMES = tuple(n[:-4] if n.lower().endswith(".exe") else n for n in PROCESS_NAMES)


def _tasklist() -> list[str]:
    try:
        r = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=20,
            creationflags=0x08000000 if is_windows() else 0,
        )
        # tasklist 的输出跟随**控制台 OEM 代码页**（中文 Windows = cp936/gbk），
        # 不是 ANSI，所以这里必须显式按 gbk 解码，不能用 locale.getpreferredencoding()。
        return (r.stdout or b"").decode("gbk", "replace").splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def _tasklist_names() -> set[str]:
    """从 tasklist 的 CSV 输出里取出**精确**的进程名集合。

    为什么不能用子串匹配：`"codex.exe" in text` 在小写后的整块文本里搜，
    会把 `mycodex.exe` / `codex-helper.exe` 也算成命中 —— 用于"是否在跑"是
    误报，用于杀进程就是误杀。这里按 CSV 第一列（Image Name）精确比对。
    """
    names: set[str] = set()
    for line in _tasklist():
        if not line.strip():
            continue
        try:
            row = next(csv.reader(io.StringIO(line)))
        except (StopIteration, csv.Error):
            continue
        if row:
            names.add(row[0].strip().lower())
    return names


def running_processes() -> list[str]:
    """返回当前在跑的、与我们相关的进程名（精确匹配，保持 PROCESS_NAMES 顺序）。"""
    alive = _tasklist_names()
    return [name for name in PROCESS_NAMES if name.lower() in alive]


def kill_all(timeout: float = 20.0) -> list[str]:
    """结束所有相关进程，返回实际被杀掉的名单。"""
    if not is_windows():
        # POSIX 兜底：`-x` 精确匹配进程名，`check=False` + timeout 防止
        # 目标不存在时抛错或挂住整条链。
        for name in dict.fromkeys(_POSIX_NAMES):
            try:
                subprocess.run(
                    ["pkill", "-x", name],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                continue
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
