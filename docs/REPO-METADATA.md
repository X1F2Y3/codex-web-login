# 仓库描述（复制到 GitHub 的 "About" 栏）

## Description（仓库简介，建议 120 字符内）

```
Make Codex Desktop show your real account — skip the overseas phone wall. 让 Codex 显示真实账号，绕过海外手机号验证。
```

## Topics（话题标签，GitHub About → Topics）

```
codex
chatgpt
openai
codex-cli
codex-desktop
authentication
auth-token
jwt
python
cli
windows
macos
linux
phone-verification
bypass
developer-tools
```

## Website

```
（留空，或填你的使用文档地址）
```

---

# 首次发布时的 Release 文案（可直接粘贴）

## Tag
```
v1.0.0
```

## Release title
```
v1.0.0 — 首发：让 Codex 显示真实账号
```

## Release notes

```markdown
## ✨ 首发版本

用浏览器网页版的 accessToken 打通 Codex 的 ChatGPT 通道，绕过 `add-phone` 手机号墙。

### 它能做什么

- 🎯 界面显示**真实头像 / 姓名 / 档位**
- 📊 显示**额度条 + 重置日期**
- 🧩 插件市场可用（不再报 `api key auth is not supported`）
- 🔁 **换账号天然支持** —— 所有字段从 token 重新派生，不串号

### 安全设计

- 只读写 `~/.codex/auth.json` 一个文件
- 每次修改前**自动备份**，校验失败**自动回滚**
- 写入保证**无 BOM**（避免 PowerShell 那个经典坑）
- 不注入、不打补丁、不上传数据、无遥测

### 工程特性

- **零硬编码** —— 所有路径通过平台惯例 + 环境变量发现
- **可插拔启动策略链** —— 5 层策略，适配各种启动方式
- **31 个单元测试** 全通过
- 5 个子命令：`login` / `check` / `backups` / `restore` / `doctor`
- `--dry-run` 严格只读预览

### 安装

```bash
pip install git+https://github.com/X1F2Y3/codex-web-login
codex-web-login login --from-clipboard
codex-web-login check
```

### 已知限制

- token 约 10 天过期，不会自动续期
- 额度是账号真实上限，显示账号信息 ≠ 能用
- 依赖「客户端只做结构校验」这一实现细节

详见 [README](README.md) 与 [docs/MECHANISM.md](docs/MECHANISM.md)。
```
