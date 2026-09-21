"""平台级启动器：用可插拔策略链拉起 Codex 桌面端。

核心设计
--------
**不硬编码任何路径**。启动交给一串 `LaunchStrategy`，按序尝试，第一个成功即停：

1. `UserLauncherStrategy`   —— 用户在 `~/.codex/web-login-launchers.json` 里登记的启动器
2. `EnvLauncherStrategy`    —— `CODEX_WEB_LOGIN_LAUNCHER` 环境变量
3. `ShortcutStrategy`       —— 扫描开始菜单/桌面上的 `.lnk`（Windows）
4. `ShellProtocolStrategy`  —— `explorer.exe <app>` / `open -a` （GUI 转发）
5. `DirectSpawnStrategy`    —— 最后兜底直接 spawn

为什么要有 `ShellProtocolStrategy`：
    在受限环境（沙箱、无 GUI 会话）里直接 `CreateProcess` 拉起 Electron 会失败
    （报 `该进程没有程序包标识符` / `bootstrap failed`）。用系统 shell 转发可绕过。

每个策略返回 `LaunchResult`，记录是否成功以及方式，便于诊断。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import (
    Settings,
    app_data,
    find_codex_app,
    is_windows,
    load_user_launchers,
)

# Windows 下不弹控制台窗口 + 分离进程。
# 显式加括号：`|` 的优先级**低于**条件表达式，若写成
#   `0x8 | 0x200 if is_windows() else 0`
# 语义上虽然恰好等价（被解析为 `(0x8|0x200) if ... else 0`），但极易被误读成
# `0x8 | (0x200 if ... else 0)`，改错一个符号就是静默的 flag 丢失。
_DETACHED = (0x00000008 | 0x00000200) if is_windows() else 0


@dataclass
class LaunchResult:
    ok: bool
    method: str
    detail: str = ""

    def __str__(self) -> str:
        mark = "OK " if self.ok else "FAIL"
        return f"[{mark}] {self.method}: {self.detail}"


# --------------------------------------------------------------------------
# 策略实现
# --------------------------------------------------------------------------
def _spawn(argv: list[str], env: dict[str, str] | None = None) -> bool:
    try:
        subprocess.Popen(
            argv,
            env=env,
            creationflags=_DETACHED,
            close_fds=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return True
    except (OSError, ValueError):
        return False


def strat_user_launcher(s: Settings, env: dict[str, str]) -> LaunchResult:
    for raw in load_user_launchers():
        p = Path(raw).expanduser()
        if not p.exists():
            continue
        if p.suffix.lower() == ".lnk":
            # .lnk 需要 shell 解析。不能用 explorer.exe —— 它会另起进程树、
            # **不继承我们注入的 env**，代理环境变量会静默丢失（与本文档承诺不符）。
            # `cmd /c start "" "p"` 由 cmd 解析快捷方式，且 start 继承父进程 env。
            if _spawn(["cmd", "/c", "start", "", str(p)], env):
                return LaunchResult(True, "user-launcher", str(p))
            continue
        if p.suffix.lower() in (".bat", ".cmd"):
            # 批处理必须由 cmd 执行；直接 Popen 会因不是可执行映像而失败。
            # 显式传 env，否则代理变量丢失。
            if _spawn(["cmd", "/c", str(p)], env):
                return LaunchResult(True, "user-launcher", str(p))
            continue
        if _spawn([str(p)], env):
            return LaunchResult(True, "user-launcher", str(p))
    return LaunchResult(False, "user-launcher", "无可用条目")


def strat_env_launcher(s: Settings, env: dict[str, str]) -> LaunchResult:
    if not s.launcher:
        return LaunchResult(False, "env-launcher", "未设置")
    if not s.launcher.exists():
        return LaunchResult(False, "env-launcher", f"不存在: {s.launcher}")
    if _spawn([str(s.launcher)], env):
        return LaunchResult(True, "env-launcher", str(s.launcher))
    return LaunchResult(False, "env-launcher", "spawn 失败")


def _iter_shortcuts() -> Iterable[Path]:
    if not is_windows():
        # 生成器函数里裸 `return` 等价于 StopIteration，合法但容易被读成"返回 None"。
        # 显式 `return iter(())`... 在生成器中同样只是终止；这里保留 `return`
        # 但加注释说明意图：非 Windows 平台没有 .lnk 概念，直接产出空序列。
        return
    roots = [
        app_data() / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path.home() / "Desktop",
    ]
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("*.lnk"):
                name = p.name.lower()
                if ("codex" in name or "chatgpt" in name) and str(p) not in seen:
                    seen.add(str(p))
                    yield p
        except OSError:
            continue


def strat_shortcut(s: Settings, env: dict[str, str]) -> LaunchResult:
    found = []
    for lnk in _iter_shortcuts():
        found.append(lnk)
        # 同 strat_user_launcher：explorer.exe 不继承我们注入的 env，
        # 换 `cmd /c start "" "lnk"` 才能把代理环境带进去。
        if _spawn(["cmd", "/c", "start", "", str(lnk)], env):
            return LaunchResult(True, "shortcut", str(lnk))
    if found:
        return LaunchResult(False, "shortcut", f"扫描 {len(found)} 个快捷方式，均失败")
    return LaunchResult(False, "shortcut", "无快捷方式")


def strat_shell_protocol(s: Settings, env: dict[str, str]) -> LaunchResult:
    """用系统 shell 转发启动 —— 绕开直接 spawn GUI 的限制。"""
    target = s.codex_app or find_codex_app()
    if not target or not target.exists():
        return LaunchResult(False, "shell-protocol", "未找到应用")
    if is_windows():
        shell = shutil.which("explorer.exe") or "explorer.exe"
        if _spawn([shell, str(target)], env):
            return LaunchResult(True, "shell-protocol", f"explorer -> {target.name}")
    else:
        if _spawn(["open", "-a", str(target)], env):
            return LaunchResult(True, "shell-protocol", f"open -a {target.name}")
    return LaunchResult(False, "shell-protocol", "shell 转发失败")


def strat_direct(s: Settings, env: dict[str, str]) -> LaunchResult:
    target = s.codex_app or find_codex_app()
    if not target or not target.exists():
        return LaunchResult(False, "direct-spawn", "未找到应用")
    if _spawn([str(target)], env):
        return LaunchResult(True, "direct-spawn", target.name)
    return LaunchResult(False, "direct-spawn", "直接启动失败")


STRATEGIES: tuple[Callable[[Settings, dict[str, str]], LaunchResult], ...] = (
    strat_env_launcher,
    strat_user_launcher,
    strat_shortcut,
    strat_shell_protocol,
    strat_direct,
)


def launch(settings: Settings, env: dict[str, str], verbose: bool = True) -> LaunchResult:
    """按策略链依次尝试，返回第一个成功的结果。"""
    results: list[LaunchResult] = []
    for fn in STRATEGIES:
        try:
            r = fn(settings, env)
        except Exception as exc:  # 任一策略异常不应中断整条链
            r = LaunchResult(False, fn.__name__, f"异常: {exc}")
        results.append(r)
        if verbose:
            print(f"    {r}")
        if r.ok:
            return r
    return results[-1] if results else LaunchResult(False, "none", "无策略可用")
