"""codex-web-login: 用浏览器网页版 accessToken 打通 Codex 的 ChatGPT 通道。

命令行入口见 `cli.py`。
"""

from .token import TokenInfo, parse_token  # noqa: F401
from .config import Settings  # noqa: F401

__version__ = "1.0.0"
__all__ = ["TokenInfo", "parse_token", "Settings", "__version__"]
