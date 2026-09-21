# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与
[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 修正（代码质量审计 — 三技能门禁）

按 `backend-quality-gate` / `lean-implementation` / `frontend-design-guard`
逐文件审计后的修复。

- **★ 回滚后自我污染｜`token.py`**：`restore_backup()` 回滚前会生成
  `auth.json.pre-restore-<ts>.bak`（保存**回滚前**的状态，通常正是那份坏
  token）。该文件名同时命中 `_borrow_refresh_token` 的 `glob("auth.json*")`
  与 `"bak" in name` 判据，且 mtime 最新 → **会被优先借走**，等于把刚回滚掉
  的错误又复活回来。现新增 `_is_tombstone()` 显式排除 `pre-restore` 墓碑快照。
- **★ 启动器丢弃代理环境｜`launcher.py`**：`strat_user_launcher()` 对
  `.lnk/.bat/.cmd` 走 `_spawn(["explorer.exe", p])` **不传 `env`**，而 `.exe`
  分支传了 —— 通过快捷方式启动的 Codex 拿不到注入的代理，与 README 承诺不符。
  现按扩展名分派：`.lnk` 用 `cmd /c start "" "p"`、`.bat/.cmd` 用 `cmd /c p`，
  两者都传 `env`（`start` 会继承父进程环境）。`strat_shortcut()` 同样修正。
- **进程匹配误判/误杀｜`process.py`**：`running_processes()` 原用子串匹配
  （`name.lower() in text`），`codex.exe` 会命中 `mycodex.exe`。现改为解析
  `tasklist` CSV 的 Image Name 列做**精确比对**。POSIX 兜底由 `pkill -f`
  （全命令行正则匹配，易误杀）改为 `pkill -x`（精确进程名）并补
  `check=False` + `timeout=5`。
- **常量双份事实来源｜`process.py`**：`PROCESS_NAMES` 与 `_KILL_ORDER` 内容
  重复、顺序不同，改一处易漏另一处。现 `_KILL_ORDER` 由 `PROCESS_NAMES` 派生。
- **文档与实现不符｜`verify.py`**：`read_account()` 的 docstring 声称"直接调
  app-server 的 `account/read`"，实际是 `return None` 占位且无调用方。现修正
  docstring 为如实描述（恒返回 None 的占位），并标注 TODO。
- 多处函数内 import（`has_bom` / `app_data` / `urllib.*` / `time`）提到模块顶部；
  `verify.py` 的 `rounds = (0, 10, 10)` 魔法数提为 `_SCOPE_RETRY_DELAYS` 常量；
  `query_server_usage` 的过宽 `except Exception` 收窄为
  `(URLError, OSError, TimeoutError)`。
- `launcher.py` 的 `_DETACHED` 加显式括号（原式语义正确但极易被误读为
  `0x8 | (0x200 if ... else 0)`）；`strat_shortcut` / `_iter_shortcuts` 补充
  关于"为何不用 explorer.exe"与生成器 `return` 语义的注释。
- **CLI 日志不再混入 stdout**：新增 `-v/--verbose` 开关，日志一律走 stderr
  且默认静默（CLI 的 stdout 是产品输出，混入日志会破坏可解析性）；
  `_read_clipboard()` 的空 `except: pass` 改为记 debug。

### 变更

- `.gitignore` 修正：移除两条指向不存在文件（`assets/donate-alipay.png`）的
  放行规则，改为注释说明二维码是有意入库；避免与排除规则互相抵消造成困惑。
- README / README.en：`launchers.json` 示例补注「路径换成你自己机器上的」，
  明确 `D:/tools/...` 只是示例。
- `config.py`：在模块 docstring 中把「零硬编码」的边界写清楚 —— 说明两处
  字面路径的性质（环境变量兜底 / 端口探测候选），而非真正的硬编码。
- 文档脱敏：`docs/MECHANISM.md` 的实测样本移除真实账号邮箱。

### 修正

- **文档错误**：早期 README 称「token 约 10 天过期、不会自动续期」，**结论不准确**。
  实测 `access_token` 的 10 天（`iat`+240h）没错，但 Codex 的 Rust 侧
  （`auth/manager.rs`）会用 `tokens.refresh_token` 调
  `auth.openai.com/oauth/token` **自动换新票并回写 `auth.json`** —— 登录态能自续。
  真正决定是否掉登录态的是 `refresh_token` 的有效性，不是 `access_token` 的 `exp`。
- **`refresh_token` 借用改为账号感知**：优先借 `email` 相同的备份（刷新路径可用，
  登录态可长期保持）；无同账号备份时退回异账号并如实标注来源；完全借不到时写空串
  （`""` 而非 `null`，Codex 要求该字段是 string）。首次登录不受影响。
- **CLI 增强**：`login` 现在会打印 `refresh_token` 的来源与续期能力提示，
  并在无刷新能力时明确告知「10 天后需重跑」。

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
