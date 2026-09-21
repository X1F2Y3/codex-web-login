# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与
[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.0.0] - 2026-09-22

首个正式版本。

### 新增

- `codex-web-login login` —— 用浏览器网页版 session token 打通桌面端的 ChatGPT 通道
  - `--token` / `--token-file` / `--from-clipboard` 三种取 token 方式
  - `--dry-run` 只读预演，不动任何文件
  - `--proxy` / `--launcher` / `--no-restart` 覆盖项
- `codex-web-login check` —— 4 项判据自检（auth.json / login status / scope_v3.user / 服务端额度）
- `codex-web-login doctor` —— 环境诊断（路径发现、代理探测、进程状态）
- `codex-web-login backups` / `restore` —— 备份列表与一键回滚
- **零硬编码**：所有路径通过 `config.py` 的平台发现函数定位，全部支持环境变量覆盖
- **可插拔启动策略链**：环境变量 → 用户配置 → 快捷方式 → shell 转发 → 直接启动，
  按序尝试、第一个成功即停、单个策略异常不中断整条链
- `scripts/get_token.py` —— 取 token 引导助手（送剪贴板 + 校验）
- 31 个单元测试，覆盖 JWT 解析、auth.json 写入、启动策略链容错

### 安全

- 写入 `auth.json` 前自动备份（带时间戳，保留 20 份），写入后自动校验，失败自动回滚
- 原子写入，保证 **UTF-8 无 BOM**（PowerShell 5.1 的 `Set-Content -Encoding UTF8` 会写 BOM，
  导致 Codex 报 `expected value at line 1 column 1`）
- 零运行时依赖（`dependencies = []`），所有行为可逐行审计
- 无遥测、无数据上传

### 已知限制

- token 约 10 天到期，不会自动续期（需重新从浏览器获取）
- 依赖"客户端只做结构校验"这一实现细节

[Unreleased]: https://github.com/X1F2Y3/codex-web-login/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/X1F2Y3/codex-web-login/releases/tag/v1.0.0
