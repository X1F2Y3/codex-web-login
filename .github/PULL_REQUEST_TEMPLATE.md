<!--
感谢提交 PR！请花一分钟填一下，能让 review 快很多。
Thanks for the PR! Filling this in makes review much faster.
-->

## 这个 PR 做了什么

<!-- 一句话说清。涉及多个不相关的改动请拆成多个 PR。 -->

## 为什么

<!-- 说清动机。是修 bug（附现象 + 复现步骤）还是加功能（附使用场景）？
     链接相关 Issue：Fixes #123 -->

## 改了哪些文件

<!-- 列出主要变更文件，方便 review 定位 -->

## 自测情况

- [ ] `pytest` 全绿
- [ ] `ruff check .` 无新增告警
- [ ] 新增/修改的逻辑有对应测试
- [ ] 已更新 `CHANGELOG.md`（涉及行为变更时）

## 平台实测

<!-- 特别是非 Windows 平台，非常欢迎填写 -->

| 项目 | 值 |
|:--|:--|
| 操作系统 | <!-- 如 Windows 11 24H2 / macOS 15.1 / Ubuntu 24.04 --> |
| Python 版本 | <!-- 如 3.13.1 --> |
| Codex 桌面端版本 | |
| 是否用了第三方管理器 | <!-- 如 Codex App Manager，或「无」 --> |

## 复选框

- [ ] 我没有硬编码任何绝对路径（所有路径走 `config.py` 的发现函数）
- [ ] 我提交的代码里没有真实 token / 邮箱 / 账号 ID
- [ ] 修改 `auth.json` 的逻辑保证原子写入且无 BOM
