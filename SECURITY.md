# 安全政策

## 这个项目会碰什么

**只读写一个文件：`~/.codex/auth.json`**（可通过 `CODEX_HOME` 覆盖）。

具体行为：

| 动作 | 说明 |
|:--|:--|
| 读 `auth.json` | 读取当前配置，判断是否是 `chatgpt` 形态 |
| 写 `auth.json` | 原子写入（临时文件 + 替换），`utf-8` 无 BOM |
| 备份 | 写入前把原文件复制为 `auth.json.<tag>.bak`，保留最近 20 份 |
| 杀进程 | 通过 `tasklist` / `kill` 关闭 Codex 相关进程（Windows 上含 `ChatGPT.exe` 等） |
| 启动进程 | 按[启动策略链](../README.md#启动策略链)拉起 Codex 桌面端 |
| 网络请求 | **仅在 `check` 时**向 `chatgpt.com/backend-api/wham/usage` 查询额度，用的是**你自己 token** |

## 这个项目不会做什么

- ❌ 不注入、不 hook、不打补丁、不修改 Codex 程序文件
- ❌ 不读取浏览器 cookie / 数据库 / 密码
- ❌ 不收集遥测，不上传任何数据到第三方
- ❌ 不写注册表、不装驱动、不加开机自启
- ❌ 不伪造凭据 —— 用的是使用者自己账号真实签发的 session token

代码零运行时依赖（`dependencies = []`），所有行为都可以在
[`src/codex_web_login/`](../src/codex_web_login) 里逐行审计。

## 想先确认它会做什么

```bash
codex-web-login login --dry-run    # 只打印计划，不落盘
codex-web-login doctor             # 只看环境，不做修改
codex-web-login check              # 只读自检
```

## 支持版本

只对**最新版本**提供安全修复。本项目是工具，不涉及服务端。

## 报告漏洞

**请不要公开提 Issue。** 用 GitHub 的私密渠道：

→ <https://github.com/X1F2Y3/codex-web-login/security/advisories/new>

请在报告里说明：

1. 影响版本（`codex-web-login --version`）
2. 复现步骤
3. 实际影响（会不会泄露 token / 破坏文件 / 任意代码执行）

**48 小时内**会收到首次回应。

## 关于 token 泄露

如果你担心 token 泄露：

- 到 <https://chatgpt.com/> 点 **退出登录** —— 会触发服务端 revoke，旧 token 立即失效
- 检查 `~/.codex/` 下的 `*.bak` 文件是否被误提交到了公开仓库
  （本项目的 `.gitignore` 已排除 `auth.json` 与 `*.bak`）
