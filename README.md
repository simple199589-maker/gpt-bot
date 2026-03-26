# Telegram 激活与兑换 API 服务

这个项目基于 Telegram 用户账号会话和 Telethon，把 bot 菜单操作包装成可供外部系统调用的 HTTP API，并支持本地运行、后台运行和 Docker 部署。

当前支持的内部业务动作：

- `⚡️ 激活plus母号`
- `👥 激活team母号`
- `💰 查余额`
- `🎟 兑换卡密`
- `⬅️ 返回`

## 功能概览

- 首次手动登录 Telegram，会话保存到本地 `.session`
- 前台启动 API 服务，便于调试和看日志
- 后台启动 API 服务，适合 Windows 本机长期常驻
- Docker 前台常驻运行，适合服务器或面板部署
- API Key 鉴权
- 串行队列执行 Telegram 流程，避免并发请求导致对话串台
- 可配置队列上限，队满后直接拒绝新请求
- 支持按 `requestId` 查询任务状态与最终结果

## 目录说明

- `main.py`
  CLI 入口，支持 `serve`、`login`、`daemon`
- `api_server.py`
  FastAPI 接口层
- `telegram_service.py`
  Telegram 会话、消息监听与消息发送
- `workflow_service.py`
  激活、查询余额、兑换卡密工作流
- `job_queue.py`
  串行任务队列
- `config.example.json`
  配置模板

## 本地安装

```powershell
uv sync
```

## 配置

先复制配置模板：

```powershell
Copy-Item .\config.example.json .\config.json
```

然后填写这些关键字段：

- `api_id`
- `api_hash`
- `phone`
- `bot_username`
- `proxy`
- `api.api_key`

### 配置说明

- `api.host`
  API 监听地址，默认 `127.0.0.1`
- `api.port`
  API 监听端口，默认 `8000`
- `api.api_key`
  外部调用接口时使用的鉴权密钥
- `api.queue_max_size`
  最大等待队列长度，当前正在执行的任务不计入这里
- `workflow.prompt_timeout_seconds`
  等待 bot 返回“请输入 accessToken / 卡密”提示的超时时间
- `workflow.result_timeout_seconds`
  提交 accessToken 或卡密后等待最终结果的超时时间
- `workflow.back_text`
  流程结束后用于返回主菜单的文本，默认 `⬅️ 返回`

### API Key 环境变量

如果你不想把真实 API Key 写进配置文件，也可以使用环境变量：

```powershell
$env:GPT_BOT_API_KEY = "replace_with_your_api_key"
```

当 `config.json` 里的 `api.api_key` 为空时，程序会自动读取 `GPT_BOT_API_KEY`。

## 首次登录

首次运行时，需要先完成 Telegram 登录授权。你可以直接用主入口：

```powershell
uv run .\main.py
```

如果当前本地还没有授权会话，启动过程中会要求输入：

- 登录验证码
- 二次验证密码，如果账号开启了 2FA

你也可以显式执行登录命令：

```powershell
uv run .\main.py login --config .\config.json
```

登录成功后，会在当前目录生成本地会话文件，例如：

- `gpt_bot_session.session`

## 本地运行

前台运行，适合调试：

```powershell
uv run .\main.py serve --config .\config.json
```

如果你省略 `serve`，默认也会进入前台服务模式：

```powershell
uv run .\main.py --config .\config.json
```

## 本地后台运行

后台运行命令：

```powershell
uv run .\main.py daemon start --config .\config.json
```

查看状态：

```powershell
uv run .\main.py daemon status --config .\config.json
```

停止后台服务：

```powershell
uv run .\main.py daemon stop --config .\config.json
```

后台运行时会使用：

- PID 文件：`.runtime/gpt-bot.pid`
- 日志文件：`.runtime/gpt-bot.log`

## Docker 部署

Docker 方案默认把运行数据放到容器内的 `/data` 目录。你只需要把本地 `./data` 挂载进去，就能同时持久化：

- `config.json`
- `.session` 会话文件
- `.runtime` 日志和 PID 文件

### 1. 准备运行目录

```powershell
New-Item -ItemType Directory -Force .\data
Copy-Item .\config.example.json .\data\config.json
Copy-Item .\.env.example .\.env
```

然后编辑：

- `.\data\config.json`
- `.\.env`

建议做法：

- `data/config.json` 里可以把 `api.api_key` 留空
- 真实 API Key 放到 `.env` 的 `GPT_BOT_API_KEY`

### 2. 构建镜像

```powershell
docker build -t gpt-bot .
```

### 3. 首次登录

首次必须先登录一次，生成 Telegram 会话文件：

```powershell
docker compose run --rm -it gpt-bot login --config /data/config.json
```

登录成功后，会话文件会写到本地 `.\data\` 目录。

### 4. 启动服务

```powershell
docker compose up -d
```

查看日志：

```powershell
docker compose logs -f gpt-bot
```

停止服务：

```powershell
docker compose down
```

### 5. 容器默认启动命令

镜像默认执行：

```bash
uv run python main.py serve --config /data/config.json --non-interactive --host 0.0.0.0
```

说明：

- 容器内不建议使用 `daemon`
- 容器场景直接前台运行即可，由 Docker 负责拉起和重启
- `--non-interactive` 会阻止服务模式下弹出交互登录，所以首次一定要先执行 `login`

## GitHub 自动构建镜像

如果你本地没有 Docker 环境，可以直接使用仓库里的 GitHub Actions 自动构建镜像。

工作流文件：

- `.github/workflows/docker-publish.yml`

触发方式：

- 推送到 `main` 或 `master`
- 推送 `v*` 标签
- 在 GitHub Actions 页面手动点 `Run workflow`

镜像会被发布到：

```text
ghcr.io/你的GitHub用户名/你的仓库名
```

例如你的仓库是 `https://github.com/foo/gpt-bot`，镜像地址就是：

```text
ghcr.io/foo/gpt-bot:latest
```

### 使用 GitHub 自动构建的步骤

1. 把当前项目代码 push 到 GitHub。
2. 打开仓库的 `Actions` 页面。
3. 等待 `Publish Docker Image` 工作流执行完成。
4. 到仓库右侧或个人主页的 `Packages` 查看镜像。
5. 如果你想让别人无需登录直接拉取，把这个 package 改成 `Public`。

### 拉取镜像

如果镜像是公开的，别人可以直接拉取：

```bash
docker pull ghcr.io/你的GitHub用户名/你的仓库名:latest
```

如果镜像是私有的，需要先登录：

```bash
docker login ghcr.io
docker pull ghcr.io/你的GitHub用户名/你的仓库名:latest
```

### 远程服务器运行示例

别人拉到镜像后，可以这样运行：

```bash
docker run -d \
  --name gpt-bot \
  -p 8000:8000 \
  -e GPT_BOT_API_KEY=your_api_key \
  -v $(pwd)/data:/data \
  ghcr.io/你的GitHub用户名/你的仓库名:latest
```

首次登录仍然需要交互式执行一次：

```bash
docker run --rm -it \
  -v $(pwd)/data:/data \
  ghcr.io/你的GitHub用户名/你的仓库名:latest \
  login --config /data/config.json
```

### 6. 代理配置注意事项

如果你本地配置写的是：

```json
{
  "proxy": {
    "enabled": true,
    "addr": "127.0.0.1",
    "port": 7890
  }
}
```

那么在 Docker 里通常不能直接使用宿主机的 `127.0.0.1`。Windows 和 Docker Desktop 常见做法是把代理地址改成：

- `host.docker.internal`

例如：

```json
{
  "proxy": {
    "enabled": true,
    "proxy_type": "http",
    "addr": "host.docker.internal",
    "port": 7890
  }
}
```

## GitHub 上传前注意事项

这些文件不要提交到仓库：

- `config.json`
- `*.session`
- `*.session-journal`
- `.env`
- `.runtime/`
- `.venv/`

当前仓库已经通过 `.gitignore` 和 `.dockerignore` 处理了这些常见敏感文件。

推荐上传的文件包括：

- `main.py`
- `api_server.py`
- `telegram_service.py`
- `workflow_service.py`
- `job_queue.py`
- `app_config.py`
- `schemas.py`
- `pyproject.toml`
- `uv.lock`
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `config.example.json`
- `.env.example`
- `README.md`

## API 鉴权

所有业务接口都需要 API Key。

推荐请求头：

```http
X-API-Key: your_api_key
```

也支持：

```http
Authorization: Bearer your_api_key
```

## API 接口

### 1. 激活 plus 母号

```http
POST /api/v1/activate/plus
Content-Type: application/json
X-API-Key: your_api_key
```

请求体：

```json
{
  "accessToken": "your_access_token"
}
```

内部流程：

1. 发送 `⚡️ 激活plus母号`
2. 等待 `请发送 accessToken 或付款链接`
3. 发送 `accessToken`
4. 等待处理结果
5. 自动发送 `⬅️ 返回`
6. 返回结果给 API 调用方

### 2. 激活 team 母号

```http
POST /api/v1/activate/team
Content-Type: application/json
X-API-Key: your_api_key
```

请求体：

```json
{
  "accessToken": "your_access_token"
}
```

内部流程与 plus 激活一致，只是入口按钮不同。

### 3. 查询余额

```http
GET /api/v1/balance
X-API-Key: your_api_key
```

内部流程：

1. 发送 `💰 查余额`
2. 等待余额结果
3. 返回余额文本

### 4. 兑换卡密

```http
POST /api/v1/redeem
Content-Type: application/json
X-API-Key: your_api_key
```

请求体：

```json
{
  "cardCode": "your_card_code"
}
```

内部流程：

1. 发送 `🎟 兑换卡密`
2. 等待 `请发送卡密`
3. 发送卡密参数
4. 等待兑换结果
5. 自动发送 `⬅️ 返回`
6. 返回结果给 API 调用方

### 5. 服务状态

```http
GET /api/v1/status
X-API-Key: your_api_key
```

返回当前：

- Telegram 是否已连接
- 当前等待队列长度
- 队列上限
- 正在执行的请求 ID
- 正在执行的动作名称

### 6. 按 requestId 查询任务状态

```http
GET /api/v1/requests/{requestId}
X-API-Key: your_api_key
```

返回状态可能包括：

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`

### 7. 健康检查

```http
GET /healthz
```

这个接口不需要鉴权，只返回进程存活状态。

## cURL 示例

### 激活 plus

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/activate/plus" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d "{\"accessToken\":\"your_access_token\"}"
```

### 查询余额

```bash
curl "http://127.0.0.1:8000/api/v1/balance" \
  -H "X-API-Key: your_api_key"
```

### 查询 requestId 状态

```bash
curl "http://127.0.0.1:8000/api/v1/requests/your_request_id" \
  -H "X-API-Key: your_api_key"
```

### 兑换卡密

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/redeem" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d "{\"cardCode\":\"your_card_code\"}"
```

## 注意事项

- 这个项目使用的是 Telegram 用户账号会话，不是 Bot Token
- 同一时间只允许一个 Telegram 工作流在执行，其他请求会排队
- 如果等待队列达到 `api.queue_max_size`，新请求会直接返回 `429`
- 如果 bot 长时间不返回下一步提示或最终结果，接口会返回超时错误
- 如果客户端自己超时断开，可以继续用 `requestId` 轮询任务状态和最终结果
- 若当前网络无法直连 Telegram，需要正确配置代理
- 代理模式下如果依赖不完整，请重新执行 `uv sync`
- 当前环境下首次登录一定要先生成 `.session`，否则 `serve --non-interactive` 会直接报未授权
