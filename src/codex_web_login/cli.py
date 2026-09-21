"""CLI 入口。

用法
----
    codex-web-login login --token-file token.txt      # 用文件里的 token 登录
    codex-web-login login                            # 从剪贴板读 token
    codex-web-login check                            # 只做自检，不改动任何东西
    codex-web-login backups                          # 列出备份
    codex-web-login restore <关键词>                  # 回滚到某个备份
    codex-web-login doctor                           # 环境诊断
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import (
    ENV_CODEX_HOME,
    ENV_LAUNCHER,
    ENV_PROXY,
    Settings,
    auth_path,
    codex_home,
    find_codex_app,
    find_codex_cli,
    proxy_env,
)
from .launcher import launch
from .process import kill_all, running_processes, wait_until_gone
from .token import (
    backup_auth,
    build_chatgpt_auth,
    list_backups,
    parse_token,
    read_auth,
    restore_backup,
    atomic_write_auth,
)
from .verify import run_checks

BANNER = f"codex-web-login {__version__}"


# --------------------------------------------------------------------------
# 输入
# --------------------------------------------------------------------------
def _read_clipboard() -> str | None:
    try:
        import tkinter

        r = tkinter.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return text
    except Exception:
        pass
    try:
        import subprocess

        r = subprocess.run(["pbpaste"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "replace")
    except Exception:
        pass
    return None


def _obtain_token(args) -> str | None:
    if args.token:
        return args.token
    if args.token_file:
        p = Path(args.token_file).expanduser()
        if not p.is_file():
            print(f"  ! 文件不存在: {p}")
            return None
        return p.read_text(encoding="utf-8").strip()
    if args.from_clipboard or not sys.stdin.isatty():
        if not args.from_clipboard:
            piped = sys.stdin.read().strip()
            if piped:
                return piped
        tok = _read_clipboard()
        if tok:
            print("  已从剪贴板读取 token")
            return tok.strip()
    return None


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------
def cmd_login(args) -> int:
    settings = Settings.from_env()
    if args.proxy:
        settings.proxy = args.proxy
    if args.launcher:
        settings.launcher = Path(args.launcher).expanduser()

    token = _obtain_token(args)
    if not token:
        print("无法获取 token。请用 --token / --token-file / --from-clipboard 提供。")
        return 2

    # 1. 先解析（不合法就立刻失败，不碰任何文件）
    try:
        info = parse_token(token)
    except ValueError as exc:
        print(f"token 解析失败：{exc}")
        return 2

    print(f"{BANNER}\n\ntoken 解析成功：")
    for line in info.summary().splitlines():
        print("  " + line)
    if info.is_expired:
        print("\n  ! 这个 token 已过期，请重新从浏览器获取。")
        return 2

    prev = read_auth()
    prev_acct = (prev.get("tokens") or {}).get("account_id")
    if prev_acct and prev_acct != info.account_id:
        print(f"\n  换账号：{prev_acct}  ->  {info.account_id}")

    if args.dry_run:
        print("\n--dry-run：仅解析，未改动任何文件。")
        return 0

    # 2. 杀进程
    print("\n[1/5] 关闭 Codex 进程 ...")
    killed = kill_all()
    if killed:
        print("      已结束: " + ", ".join(sorted(set(killed))))
    wait_until_gone()
    print("      OK")

    # 3. 备份
    print("[2/5] 备份现有 auth.json ...")
    bak = backup_auth(tag="pre-login", keep=settings.backups)
    print(f"      {bak.name if bak else '（无现有文件）'}")

    # 4. 写入
    print("[3/5] 写入 chatgpt 形态 auth.json ...")
    data = build_chatgpt_auth(info)
    p = atomic_write_auth(data)
    b = p.read_bytes()
    print(f"      OK  {len(b)}B  head={list(b[:4])}")

    # 5. 校验
    print("[4/5] 校验 login status ...")
    env = proxy_env(settings.resolve_proxy())
    rep = run_checks(settings, wait_appserver=False)
    status = next((c for c in rep.checks if c.name == "codex login status"), None)
    print(f"      {status}" if status else "      ?")

    if status and not status.ok:
        print("\n  校验未通过，正在回滚 ...")
        if bak:
            restore_backup(bak.name)
            print(f"  已恢复 {bak.name}")
        return 1

    # 6. 启动
    if settings.no_restart or args.no_restart:
        print("[5/5] 跳过启动（--no-restart）")
    else:
        print("[5/5] 启动桌面端 ...")
        r = launch(settings, env)
        if r.ok:
            import time

            time.sleep(settings.launch_wait)

    print("\ndone. 用 `codex-web-login check` 复查（桌面端起来后等 20 秒再看）。")
    return 0


def cmd_check(args) -> int:
    settings = Settings.from_env()
    if args.proxy:
        settings.proxy = args.proxy
    rep = run_checks(settings, wait_appserver=not args.no_wait)
    print(rep.render())
    return 0 if rep.passed else 1


def cmd_backups(args) -> int:
    items = list_backups()
    if not items:
        print("没有备份。")
        return 0
    print(f"{len(items)} 个备份（新 -> 旧）：")
    for b in items:
        import time

        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(b.stat().st_mtime))
        print(f"  {ts}  {b.stat().st_size:>7}B  {b.name}")
    return 0


def cmd_restore(args) -> int:
    settings = Settings.from_env()
    print(f"{BANNER}\n\n关闭 Codex 进程 ...")
    kill_all()
    wait_until_gone()
    try:
        src = restore_backup(args.keyword)
    except FileNotFoundError as exc:
        print(f"  ! {exc}")
        return 2
    print(f"已从 {src.name} 恢复。")
    print("\n复查：")
    rep = run_checks(settings, wait_appserver=False)
    print(rep.render())
    return 0


def cmd_doctor(args) -> int:
    print(f"{BANNER}\n")
    print(f"CODEX_HOME        = {codex_home()}   (env {ENV_CODEX_HOME})")
    print(f"auth.json         = {auth_path()}  exists={auth_path().is_file()}")
    print(f"codex CLI         = {find_codex_cli()}")
    print(f"Codex app         = {find_codex_app()}")
    s = Settings.from_env()
    print(f"代理              = {s.resolve_proxy()}   (env {ENV_PROXY})")
    print(f"自定义启动器      = {s.launcher}   (env {ENV_LAUNCHER})")
    print(f"在跑的相关进程    = {running_processes() or '（无）'}")
    print()
    print("启动器配置文件    =", codex_home() / "web-login-launchers.json")
    return 0


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="codex-web-login",
        description="用浏览器网页版 accessToken 打通 Codex 的 ChatGPT 通道",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=BANNER)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("login", help="写入 token 并登录")
    a.add_argument("--token", help="直接给 JWT")
    a.add_argument("--token-file", help="从文件读 JWT")
    a.add_argument("--from-clipboard", action="store_true", help="从剪贴板读")
    a.add_argument("--proxy", help="代理地址，如 http://127.0.0.1:7890")
    a.add_argument("--launcher", help="自定义启动器路径")
    a.add_argument("--no-restart", action="store_true", help="不启动桌面端")
    a.add_argument("--dry-run", action="store_true", help="只解析，不改动")
    a.set_defaults(func=cmd_login)

    b = sub.add_parser("check", help="自检（只读）")
    b.add_argument("--proxy", help="代理地址")
    b.add_argument("--no-wait", action="store_true", help="不等待 app-server")
    b.set_defaults(func=cmd_check)

    c = sub.add_parser("backups", help="列出备份")
    c.set_defaults(func=cmd_backups)

    d = sub.add_parser("restore", help="回滚到备份")
    d.add_argument("keyword", help="备份名关键词")
    d.set_defaults(func=cmd_restore)

    e = sub.add_parser("doctor", help="环境诊断")
    e.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
