#!/usr/bin/env python3
"""取 token 引导助手（可选）。

降低"取 token"这一步的摩擦：把该复制的 JS 放进剪贴板，
并检测剪贴板里是否已经有 JWT。
"""

from __future__ import annotations

import re
import sys

SNIPPET = (
    "fetch('/api/auth/session').then(r=>r.json())"
    ".then(d=>console.log(d.accessToken))"
)
JWT_RE = re.compile(r"^[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+$")


def to_clipboard(text: str) -> bool:
    try:
        import tkinter

        r = tkinter.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        pass
    try:
        import subprocess

        subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
        return True
    except Exception:
        return False


def from_clipboard() -> str | None:
    try:
        import tkinter

        r = tkinter.Tk()
        r.withdraw()
        t = r.clipboard_get()
        r.destroy()
        return t
    except Exception:
        return None


def main() -> int:
    print("=" * 62)
    print("  取 accessToken 引导")
    print("=" * 62)
    print()
    print("第 1 步：浏览器登录 https://chatgpt.com/ 并确认能正常聊天")
    print()
    print("第 2 步：按 F12 打开 DevTools → 切到 Console")
    print()
    print("第 3 步：粘贴下面这行并回车（已帮你复制到剪贴板）：")
    print()
    print("    " + SNIPPET)
    print()

    if to_clipboard(SNIPPET):
        print("  [已复制到剪贴板]")
    else:
        print("  [复制失败，请手动选中上面那行]")
    print()
    print("第 4 步：控制台会打印一串 JWT，复制它")
    print()
    input("完成后按回车，我来检测剪贴板内容 ... ")

    text = (from_clipboard() or "").strip()
    if not text:
        print("\n  剪贴板为空 —— 请确认已复制 token 后重跑本脚本。")
        return 1

    if JWT_RE.match(text):
        print(f"\n  ✓ 检测到 JWT（{len(text)} 字符）")
        print("\n  下一步：")
        print("      codex-web-login login --from-clipboard")
        return 0

    print(f"\n  ✗ 剪贴板内容看起来不是 JWT（{len(text)} 字符，开头 {text[:24]!r}）")
    print("     常见原因：复制的是输出整行、或还没执行那行 JS。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
