# 贡献指南

感谢愿意帮忙！提交前请确认：

## 环境

```bash
git clone https://github.com/USERNAME/codex-web-login
cd codex-web-login
pip install -e ".[dev]"
```

## 提交前检查

```bash
pytest          # 必须全绿
ruff check .    # 尽量无告警
```

## 代码约定

- **不要硬编码任何路径。** 需要定位文件时，加到 `config.py` 的发现函数里，
  并且必须支持环境变量覆盖。
- **不要在测试里使用真实凭据。** 用 `tests/test_token.py` 里的 `make_jwt()` 现场构造。
- **修改 `auth.json` 的逻辑必须原子写入**，并保证无 BOM。
- 新增平台支持时，优先走 `config.py` 的平台分支，不要在业务层判断 `sys.platform`。

## 特别欢迎的贡献

1. **非 Windows 平台的实测反馈**（macOS / Linux 的路径发现是否正确）
2. **更多启动器适配**（不同第三方管理器）
3. **新增判据**（如果发现更可靠的验证方式）

## 提交 PR

- 一个 PR 只做一件事
- 说明**为什么**改，而不只是改了什么
- 涉及行为变更的，同步更新 `CHANGELOG.md`
