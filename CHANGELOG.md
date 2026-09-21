# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)
与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-22

### 新增

- `login` 命令：写入网页 token 并打通 ChatGPT 通道
  - 支持 `--token` / `--token-file` / `--from-clipboard`
  - `--dry-run` 严格只读（仅解析，不触碰任何文件）
  - `--no-restart` 只改配置不启动桌面端
- `check` 命令：4 项判据自检（auth.json / login status / scope_v3 / 服务端额度）
- `backups` / `restore`：备份列表与一键回滚
- `doctor` 命令：环境诊断
- **零硬编码**：所有路径通过平台惯例 + 环境变量 + 运行时发现确定
- **可插拔启动策略链**：自定义启动器 → 快捷方式 → shell 转发 → 直接 spawn
- 自动代理探测（常见本地端口）
- 换账号天然支持：所有字段从 token 重新派生，不依赖旧账号数据
- 写入前自动备份、校验失败自动回滚
- 31 个单元测试

### 已知限制

- token 约 10 天到期，不会自动续期（需重新从浏览器获取）
- 依赖"客户端只做结构校验"这一实现细节

[1.0.0]: https://github.com/USERNAME/codex-web-login/releases/tag/v1.0.0
