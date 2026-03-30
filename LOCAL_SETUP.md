# 本地启动说明

本文只说明这个项目如何在本地机器上跑起来，不包含 Docker。

如果你只是想先把服务启动成功，按下面顺序做：

1. 安装 `Python 3.13+`
2. 安装 `uv`
3. 准备 Telegram 账号、`api_id`、`api_hash`
4. 复制 `config.example.json` 为 `config.json`
5. 执行一次登录
6. 启动本地服务

## 项目用途

这个项目会使用你的 Telegram 用户会话登录指定 bot，把 bot 菜单操作包装成 HTTP API，供本地或内网系统调用。

当前主要能力：

- 激活 Plus
- 激活 Team
- 查询余额
- 兑换卡密
- 取消当前菜单
- 定时自动兑换卡密

接口字段和调用示例请看 `API_BRIEF.md`，本文只关心本地启动。

## 本地需要安装什么

启动前至少要准备这些东西：

- `Python 3.13` 或更高版本
- `uv`
- `PowerShell 7+`
- 一个可正常登录的 Telegram 账号
- Telegram 开发者配置里的 `api_id` 和 `api_hash`
- 目标 bot 的用户名，例如 `@gptnocard_bot`

如果你本地访问 Telegram 需要代理，还需要准备可用的 `socks5` 或 `http` 代理地址。

## 1. 安装 Python

项目在 [pyproject.toml](./pyproject.toml) 里要求：

```toml
requires-python = ">=3.13"
```

先确认本机版本：

```powershell
python --version
```

如果你的机器上 `python` 命令不可用，也可以试：

```powershell
py --version
```

## 2. 安装 uv

如果你本机还没有 `uv`，可以先安装：

```powershell
py -m pip install uv
```

安装完成后确认：

```powershell
uv --version
```

## 3. 安装项目依赖

进入项目根目录后执行：

```powershell
uv sync
```

这一步会安装项目依赖，包括：

- `Telethon`
- `FastAPI`
- `Uvicorn`
- 代理相关依赖 `python-socks`、`PySocks`

## 4. 准备配置文件

先复制一份配置模板：

```powershell
Copy-Item .\config.example.json .\config.json
```

然后编辑 `config.json`，至少填这些字段：

- `api_id`：Telegram 开发者后台的应用 ID
- `api_hash`：Telegram 开发者后台的应用 Hash
- `phone`：你的 Telegram 手机号，带国家区号
- `session_name`：本地会话文件名，不带扩展名
- `bot_username`：目标 bot 用户名
- `api.api_key`：调用本地 HTTP API 时使用的密钥

如果你需要代理，再继续填：

- `proxy.enabled`
- `proxy.proxy_type`
- `proxy.addr`
- `proxy.port`
- `proxy.username`
- `proxy.password`

一个最小可运行配置大致如下：

```json
{
  "api_id": 12345678,
  "api_hash": "replace_with_your_api_hash",
  "phone": "+8613800000000",
  "session_name": "gpt_bot_session",
  "bot_username": "@your_bot_username",
  "api": {
    "host": "127.0.0.1",
    "port": 8000,
    "api_key": "replace_with_your_api_key",
    "queue_max_size": 10
  },
  "proxy": {
    "enabled": false,
    "proxy_type": "socks5",
    "addr": "127.0.0.1",
    "port": 7890,
    "username": "",
    "password": "",
    "rdns": true
  }
}
```

## 5. 关于定时兑换

项目现在支持定时自动调用兑换流程。如果你只是先把服务跑起来，建议先确认这段配置是不是你想要的：

```json
"scheduled_redeem": {
  "enabled": true,
  "card_code": "SHARED-1D8286F94F66",
  "times": [
    "00:00",
    "00:05"
  ]
}
```

如果你不希望本地服务启动后自动执行兑换，把它改成：

```json
"scheduled_redeem": {
  "enabled": false,
  "card_code": "",
  "times": [
    "00:00",
    "00:05"
  ]
}
```

## 6. 首次登录 Telegram

首次运行前，先做一次交互式登录：

```powershell
uv run .\main.py login --config .\config.json
```

执行过程中可能会提示你输入：

- Telegram 验证码
- 二次验证密码，如果账号开启了 2FA

登录成功后，项目根目录会生成这些文件：

- `你的 session_name.session`
- `你的 session_name.session-journal`

如果这一步没做成功，后面的服务启动通常也会失败。

## 7. 启动本地服务

前台运行：

```powershell
uv run .\main.py serve --config .\config.json
```

也可以省略 `serve`，效果一样：

```powershell
uv run .\main.py --config .\config.json
```

默认监听地址来自 `config.json`：

- `api.host`
- `api.port`

例如默认就是：

- `127.0.0.1`
- `8000`

## 8. Windows 后台常驻运行

如果你希望在本机后台运行：

启动：

```powershell
uv run .\main.py daemon start --config .\config.json
```

查看状态：

```powershell
uv run .\main.py daemon status --config .\config.json
```

停止：

```powershell
uv run .\main.py daemon stop --config .\config.json
```

后台运行会生成：

- `.runtime/gpt-bot.pid`
- `.runtime/gpt-bot.log`

## 9. 启动后怎么验证

先检查健康接口：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/healthz"
```

正常情况下会返回：

```json
{
  "status": "ok"
}
```

再检查服务状态接口：

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/status" -Headers @{
  "X-API-Key" = "你的 api.api_key"
}
```

如果服务正常，你还可以直接打开：

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

## 10. 本地常用命令

首次安装依赖：

```powershell
uv sync
```

执行登录：

```powershell
uv run .\main.py login --config .\config.json
```

前台启动：

```powershell
uv run .\main.py serve --config .\config.json
```

后台启动：

```powershell
uv run .\main.py daemon start --config .\config.json
```

后台状态：

```powershell
uv run .\main.py daemon status --config .\config.json
```

后台停止：

```powershell
uv run .\main.py daemon stop --config .\config.json
```

## 11. 常见问题

`uv` 命令不存在：

- 先确认已经安装 `uv`
- 安装后重新打开一个新的 PowerShell 窗口再试

提示缺少 `api.api_key`：

- 在 `config.json` 里填写 `api.api_key`
- 或设置环境变量 `GPT_BOT_API_KEY`

服务启动时要求登录，但我不想在后台输入验证码：

- 先单独执行一次 `uv run .\main.py login --config .\config.json`
- 登录成功后再执行 `serve` 或 `daemon start`

代理开了但连不上 Telegram：

- 先确认代理本身可用
- 再确认 `proxy_type`、`addr`、`port` 填写正确
- 如果本机不需要代理，直接把 `proxy.enabled` 改成 `false`

修改了 `config.json` 但服务没有生效：

- 需要重启服务
- 如果是后台模式，先 `daemon stop` 再 `daemon start`

本地启动后自动执行兑换了：

- 检查 `scheduled_redeem.enabled`
- 如果只是调试环境，建议先关掉

## 12. 不建议提交的文件

这些文件通常不应该提交到仓库：

- `config.json`
- `*.session`
- `*.session-journal`
- `.runtime/*`

## 13. 下一步看哪里

服务跑起来以后，如果你要对接接口，请继续看：

- `API_BRIEF.md`
