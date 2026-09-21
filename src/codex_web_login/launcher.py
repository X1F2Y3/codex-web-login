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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .config import (
    Settings,
    app_data,
    find_codex_app,
    is_windows,
    load_user_launchers,
)

# Windows 下不弹控制台窗口 + 分离进程
_DETACHED = 0x00000008 | 0x00000200 if is_windows() else 0


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
        if p.suffix.lower() in (".lnk", ".bat", ".cmd"):
            # 交给 shell 处理
            if _spawn(["explorer.exe", str(p) if not str(p).endswith(".lnk") else str(p)]):
                return LaunchResult(True, "user-launcher", str(p))
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
        return
    roots = [
        app_data() / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("ProgramData", "C:/ProgramData"))
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
        if _spawn(["explorer.exe", str(lnk)]):
            return LaunchResult(True, "shortcut", str(lnk))
    return LaunchResult(False, "shortcut", f"扫描 {len(found)} 个快捷方式，均失败" if found else "无快捷方式")


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
