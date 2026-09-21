# 机制说明：为什么这能成立

> 本文是**源码级**证据，不是推测。代码从本机 Codex 桌面端
> `resources/app.asar` 反编译得到。

## 解包方法

```python
# asar 头结构：
#   [4B u32][4B u32 headerPickleSize][4B u32 jsonSize][json 索引][数据区]
# 数据区起点 = 8 + headerPickleSize + jsonSize

with open(ASAR, "rb") as f:
    f.read(4); f.read(4)
    hs = struct.unpack("<I", f.read(4))[0]
    js_size = struct.unpack("<I", f.read(4))[0]
    data_start = 8 + hs + js_size
    f.seek(16)
    index = json.loads(f.read(js_size).decode("utf-8"))
```

两个易踩的坑：
- 索引里的 key 是**纯文件名**，完整路径在**父级目录的 key** 上（递归时要拼前缀）。
- 条目的 `offset` 是**字符串**，要 `int()`；目录条目没有 `offset`，要跳过。

关键文件：
- `/.vite/build/main-*.js`（主进程，本机约 3.75 MB）
- `/webview/assets/app-initial-*.js`（渲染层，本机约 12.1 MB）

---

## 证据 1：判定函数只验结构，不验签

主进程里 Codex 判定登录态的**唯一**函数：

```js
function UN(e){
  return e == null ? `response_null`
    : e.authMethod !== `chatgpt` && e.authMethod !== `chatgptAuthTokens`
        ? `auth_method_not_chatgpt`
    : e.authToken == null ? `auth_token_missing`
    : null
}
```

只做三件事：**判空 → 判字符串相等 → 判非 null**。

没有签名验证、没有 `iss`/`aud` 白名单、没有在线校验调用。

---

## 证据 2：本地解码只解 payload

```js
function nei(e){
  let t = e.split(`.`)[1];                    // 只取第二段
  if (t == null) return null;
  try {
    let e = JSON.parse(rei(t));               // base64url 解码
    let n = e[`https://api.openai.com/auth`];  // 档位 / account_id
    let r = e[`https://api.openai.com/profile`]; // email / name
    return {
      accountId: n?.chatgpt_account_id ?? n?.account_id ?? null,
      userId:    n?.user_id ?? n?.chatgpt_user_id ?? null,
      email:     r?.email ?? null,
      planType:  iei(n?.chatgpt_plan_type),
      ...
    }
  } catch { return null }
}

function rei(e){                              // base64url → 明文
  let t = e.replaceAll(`-`,`+`).replaceAll(`_`,`/`);
  let n = (4 - t.length % 4) % 4;
  return globalThis.atob(`${t}${`=`.repeat(n)}`);
}
```

**第三段（签名）从头到尾没被碰过。** `atob` 是纯解码，不是验签。

### 由此推出的两个关键点

**① `id_token` 必须是 string。**
填 `null` 会报：
```
Error checking login status: invalid type: null, expected a string at line 5 column 20
```
填任意合法 JWT 即通过。所以同一个 token 可以同时占 `id_token` 和 `access_token`。

**② email / planType 来自嵌套 claim，不是顶层。**
```
顶层 JWT.email              -> 不存在
JWT[".../profile"].email    -> 真实邮箱        ← Codex 读这里
JWT[".../auth"].chatgpt_plan_type -> 档位       ← 和这里
```
任何 ChatGPT 网页 session 的 accessToken 都带这两个 claim —— **所以换任意账号都成立**。

---

## 证据 3：界面分支由服务端返回的 `type` 决定

渲染层：

```js
n.getAccount().then(([n, i]) => {
  let o = n.account;
  e.set(Tq, t,
    i === `chatgpt` && o?.type === `chatgpt`
      ? { email: o.email, planType: o.planType }   // ← 显示账号信息
      : null                                        // ← 只显示 "Logged in with API key"
  )
})
```

配套映射：

```js
function iui(e){
  if (e == null) return null;
  let t = e.type;
  return t === `apiKey` ? `apikey`                 // 服务端返回 type=apiKey
       : (t === `amazonBedrock` || t === `chatgpt`) ? t
       : null
}
```

**`e.type` 是服务端给的**，不是客户端推断的。所以：

| token 放在哪 | 服务端返回 `type` | 界面表现 |
|---|---|---|
| `OPENAI_API_KEY` | `apiKey` | 「已通过 API 密钥登录」，无账号信息 |
| `tokens.access_token` | `chatgpt` | 真实邮箱 + 档位 + 额度条 + 插件市场 |

> 这也解释了很多人遇到的困惑：用 `codex login --with-api-key` 灌 token，
> 官方 CLI 只会写 `OPENAI_API_KEY` 字段 —— 于是永远停留在 apikey 分支。
> **`auth.json` 是可以手写的**，手写 `tokens` 段就走另一条协议分支。

---

## 证据 4：登录态的存续由 `refresh_token` 决定，不是 `access_token.exp`

> 本节是 **2026-09-22 的修正**。早期文档写过「token 约 10 天过期、不会自动续期」，
> 这个说法**只对了一半**，会误导使用者。

### 两个 token 的分工

| | 时长 | 作用 |
|:--|:--|:--|
| `access_token` | **10 天**（实测 `iat` + 240h） | 当前这张"票"，每次请求都带上 |
| `refresh_token` | **不固定，通常长期** | **用来换新票** |

实测样本（`fanxiaoyongf@gmail.com`）：

```
iat = 2026-09-22 00:00:57
exp = 2026-10-02 00:00:57
时长 = 240.0 小时 = 10.0 天
```

`access_token` 的 10 天是真的。**但这不等于登录态 10 天后失效。**

### Rust 侧确实会主动刷新

判定逻辑不在 JS 里，而在 `codex.exe`（317 MB 的 Rust 二进制）中。
从二进制里提取到的字符串（`login\src\auth\manager.rs`）：

```
"Refreshing token"                                          ← 它会主动刷新
"last_refresh is in the past"                               ← 触发条件
"Token data is not available."                              ← 拿不到 refresh 数据
"Failed to refresh token: " / "Reloading auth"              ← 刷新失败后重载
"Skipping token refresh because auth changed after
 guarded reload."                                           ← 换账号后的保护
"Your access token could not be refreshed because you have
 since logged out or signed in to another account."         ← 明确错误语义
not_refreshable_auth                                        ← 独立的不可刷新状态
```

刷新端点与请求体（同二进制）：

```
https://auth.openai.com/oauth/token
Content-Type: application/x-www-form-urlencoded
grant_type=refresh_token        ← CreateOAuth2TokenRequestBody 的字段
```

**结论：`access_token` 到期前，Codex 会用 `tokens.refresh_token` 去
`auth.openai.com/oauth/token` 换一张新的并回写 `auth.json`。登录态自己会续。**

### 那什么时候会真的掉登录态？

只有这几种：

| 情况 | 机制 |
|:--|:--|
| 网页端点「退出登录」 | 服务端 revoke，`refresh_token` 当场作废 |
| `refresh_token` 被别处轮换过 | OAuth refresh token 通常一次性轮换，旧的失效即 `invalid_grant` |
| `refresh_token` 不是本账号的 | 刷新换回错账号的票，或直接落到 `not_refreshable_auth` |

### 本工具的短板（如实说明）

浏览器 `/api/auth/session` **只返回 `access_token`，不返回 `refresh_token`**。
所以本工具的 `refresh_token` 是从 `~/.codex/auth.json*` 历史备份里**借**的。

这带来一个真实限制：

> **首次登录 100% 成功**（因为它只依赖 `access_token` 的结构合法性）；
> 但**能否长期免维护，取决于借来的 `refresh_token` 是否属于当前账号。**

因此 2026-09-22 起，借用逻辑改为**账号感知**（`token.py::_borrow_refresh_token`）：

1. 优先借用 `email` **完全相同**的备份 → 刷新路径可用，登录态可长期保持；
2. 没有同账号备份时，退回借异账号的，并在 CLI 里**如实打印来源**；
3. 完全借不到时写入空串（`""`，不是 `null` —— Codex 要求该字段是 string），
   首次登录照常成功，10 天后需重跑。

自测覆盖：`tests/test_token.py::test_borrow_prefers_same_account` 等 5 个用例。

---

## 官方能不能修

**能，但"修"分两个层次：**

| 修复方式 | 位置 | 工作量 | 影响 |
|---|---|---|---|
| 客户端加 `iss`/`aud` 白名单 | 主进程判定函数 | **约 5 行代码** | 不误伤正常 OAuth |
| 服务端签发时打 `client_id` 标，桌面端只认自家 client | 服务端 + 客户端 | **架构级改动** | 可能影响合法的 token 复用场景 |

**为什么短期大概率不修：**

给网页版 `chatgpt.com` 加手机号墙 = 砍掉大量只想要网页聊天的普通用户注册转化。
官方不可能为堵一条小众绕路而牺牲主站注册 —— **这是产品决策，不是安全决策**。

而按"技术可行性"论，客户端加校验随时能做、成本极低。所以：

> **本方案的有效窗口期，取决于官方对免手机号登录的产品策略，而非技术难度。**

届时 `codex-web-login check` 会报错（auth.json / login status 项通过，但账号信息不再渲染）。

---

## 验证判据

```
[1] auth.json          mode=chatgpt，无 BOM，token 可解析
[2] codex login status  ->  Logged in using ChatGPT
[3] scope_v3.user       ->  {"authMethod":"chatgpt","account_id":...}
[4] 服务端额度           ->  HTTP 200（apikey 形态下为 401）
```

**时序坑**：桌面端刚启动时 `account/read` 可能返回 `{}`（app-server 还没握手完）。
`scope_v3.user` 通常先就绪 —— 判定应以它为准，或等 20 秒重试。

`scope_v3.json` 的位置随平台变化，本项目自动发现（Windows 实测在
`%APPDATA%\Codex\web\Codex\sentry\scope_v3.json`）。
