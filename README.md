<div align="center">

# codex-web-login

**用浏览器网页版的 accessToken，打通 Codex 的 ChatGPT 通道**

绕过 `add-phone` 手机号墙 · 让桌面端显示真实账号信息 / 额度条 / 插件市场

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#-环境要求)
[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen.svg)](tests/)

</div>

---

## 这是什么

Codex 桌面端登录时要求**海外手机号验证**（`auth.openai.com/add-phone`，没有跳过按钮）。

但这个手机号墙**只存在于 Codex Desktop 用的那个 OAuth client**。浏览器网页版 `chatgpt.com` 用的是**另一个 OAuth client**，允许 email-OTP 登录，全程不要手机号。

本项目做的事很简单：

> 把浏览器网页版 session 的 `accessToken`（一个标准 JWT），写进 `~/.codex/auth.json` 的 `tokens` 段。

Codex 对 `tokens` 段**只做结构校验、不验签**（源码证据见 [docs/MECHANISM.md](docs/MECHANISM.md)），所以这个 token 会被正常接纳，走 `chatgpt` 协议分支，界面于是显示真实账号信息。

**这不是伪造凭据** —— 用的是你自己账号真实签发的合法 session token，只是把它放到了桌面端期望的位置。

---

## 效果

| 之前（API key 模式） | 之后（网页 token 模式） |
|---|---|
| 「已通过 API 密钥登录」 | **真实头像 + 姓名 + 档位** |
| 看不到额度 | **额度条 + 重置日期** |
| 插件市场报 `api key auth is not supported` | **插件市场可用** |
| `account/read` → `{type:"apiKey"}` | `account/read` → `{type:"chatgpt", email, planType}` |

---

## 快速开始

### 1. 从浏览器拿 accessToken

浏览器登录 <https://chatgpt.com/>（确认能正常聊天），然后 `F12` → Console，粘贴执行：

```js
fetch('/api/auth/session').then(r=>r.json()).then(d=>console.log(d.accessToken))
```

> **别用 `copy()`** —— DevTools 里会报 `copy is not defined`。
> 输出是一串约 1900 字符的 JWT，形如 `eyJhbGciOiJSUzI1NiIs...`。

### 2. 登录

```bash
# 从文件读
codex-web-login login --token-file token.txt

# 或从剪贴板读（先复制 token）
codex-web-login login --from-clipboard
```

脚本会依次完成：解析校验 → 关闭 Codex 进程 → 备份 → 写入 → 校验 → 启动桌面端。

### 3. 复查

```bash
codex-web-login check
```

**判定 PASS 即成功。**

---

## 为什么是"半自动"

「从浏览器复制一行命令的输出」这一步是**设计上的最优解，不是偷懒**。三条自动化路线都实测堵死：

| 路线 | 结果 |
|---|---|
| 读桌面端 cookie 库 → 调 `/api/auth/session` | ❌ `WinError 32` 绝对独占锁，进程运行时读不到 |
| `codex login --with-access-token` | ❌ 报 `agent identity JWT payload is not valid JSON`（它要的是另一种凭据） |
| `codex login --device-auth` | ❌ 卡在 `add-phone` 手机号墙 |

关键点：`/api/auth/session` 走的**正是那个不要手机号的 OAuth client**。所以这一步既是唯一手工环节，也是整个方案能成立的原因。

> 剩下的全部自动化：路径发现、代理探测、进程管理、备份、写入、校验、启动。

---

## 命令

| 命令 | 说明 |
|---|---|
| `login --token-file F` | 用文件里的 token 登录 |
| `login --token T` | 直接给 JWT |
| `login --from-clipboard` | 从剪贴板读 |
| `login --dry-run` | **只解析，不改动任何文件** |
| `login --no-restart` | 改完不启动桌面端 |
| `check` | 只读自检（4 项判据）|
| `backups` | 列出全部备份 |
| `restore <关键词>` | 回滚到某个备份 |
| `doctor` | 环境诊断 |

## 换账号

**同一个流程，只换 token。** 脚本从 token 里自己读出 email / plan / account_id / 有效期，**不依赖旧账号任何数据**，不会串号。

```bash
codex-web-login login --token-file new_account_token.txt
codex-web-login check
```

---

## 配置（全部可选）

**没有任何路径被硬编码。** 所有位置都通过平台惯例自动发现，需要时可覆盖：

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `CODEX_HOME` | Codex 配置目录 | `~/.codex` |
| `CODEX_WEB_LOGIN_PROXY` | 代理地址 | 自动探测常见端口 |
| `CODEX_WEB_LOGIN_LAUNCHER` | 自定义启动器 | 见下方启动策略链 |
| `CODEX_WEB_LOGIN_APP` | Codex 桌面端程序 | 自动发现 |

### 启动策略链

**每个人启动 Codex 的方式不同**，所以启动做成了可插拔策略链，按序尝试、第一个成功即停：

1. `CODEX_WEB_LOGIN_LAUNCHER` 环境变量
2. `~/.codex/web-login-launchers.json`（用户自定义列表）
3. 开始菜单 / 桌面的 `.lnk` 快捷方式（Windows）
4. 系统 shell 转发（`explorer.exe <app>` / `open -a`）
5. 直接 spawn

想让脚本用你自己的启动器，写个 JSON 就行：

```json
{ "launchers": ["D:/tools/codex-manager.exe"] }
```

---

## ⭐ 推荐：Codex App Manager

如果你在用 **Codex App Manager** 管理 Codex，本项目对它是**原生友好**的 —— 启动策略链会自动识别它。

App Manager 相比官方安装方式的优势：

- **下载速度明显更快**，不用等官方那套慢吞吞的更新
- **安装/更新/回滚一条龙**，不用手动处理 MSIX 的坑
- **可配置代理**，网络环境不友好时省事
- **主题/皮肤管理**，官方没有
- 本项目已适配它的进程模型（它作为宿主守护进程，需要优先关闭）

> 本项目 **不依赖** 它 —— 你不用它也能跑。但如果你正好需要个更好的安装方式，值得一试。

---

## ⚠️ 已知限制

1. **额度是账号真实上限。** 显示账号信息 ≠ 能用。免费额度耗尽时依然发不了消息 —— 那是服务端额度池，不是配置问题。
2. **token 约 10 天到期，不会自动续。** 因为它不是 OAuth 换来的，没有有效的 `refresh_token`。到期后重跑一次即可。
3. **服务端可能主动 revoke。** 你在网页端「退出登录」会触发，此时任何文件级恢复都无效，只能重新取 token。
4. **依赖"客户端不验签"这一实现细节。** 官方若加 `iss`/`aud` 校验会失效 —— 届时 `check` 会报错。详见 [docs/MECHANISM.md](docs/MECHANISM.md)。

---

## 安全与合规

- 脚本**只读写 `~/.codex/auth.json`**，每次修改前自动备份，失败自动回滚。
- token 等于你的登录凭据，**请勿分享**；本工具不上传任何数据，无遥测。
- 请仅用于**你自己的账号**。不要用于批量注册、账号交易或规避服务条款的场景。

---

## 开发

```bash
git clone https://github.com/USERNAME/codex-web-login
cd codex-web-login
pip install -e ".[dev]"

pytest          # 31 个单元测试
ruff check .    # lint
```

项目结构：

```
src/codex_web_login/
├── config.py     # 路径发现 / 设置（零硬编码）
├── token.py      # JWT 解析 / auth.json 读写
├── process.py    # 进程管理
├── launcher.py   # 可插拔启动策略链
├── verify.py     # 4 项判据 + 服务端额度查询
└── cli.py        # 命令行入口
```

---

## ❤️ 打赏

如果这个项目帮到了你，可以请我喝杯咖啡 —— 完全自愿，不付费也能用全部功能。

<!-- 把下面的占位符换成你自己的收款方式 -->
- **微信 / 支付宝**：见仓库根目录 `ASSETS/donate.png`
- **USDT (TRC20)**：`T...`（可选）
- **GitHub Sponsors**：<https://github.com/sponsors/USERNAME>

也欢迎 **Star** ⭐ —— 这比打赏更能帮我。

## License

[MIT](LICENSE)
