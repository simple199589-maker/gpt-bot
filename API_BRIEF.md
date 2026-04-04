# API 对接简版

适用项目：`gpt-bot`

这份文档只保留调用方对接时必须知道的内容：怎么调用、怎么轮询、怎么判成功失败。

## 基础信息

- Host：`https://bot.joini.cloud`
- Content-Type：`application/json`
- 鉴权：
  - `X-API-Key: your_api_key`
  - 或 `Authorization: Bearer your_api_key`
- 免鉴权接口：
  - `GET /healthz`

## 对接流程

激活 `plus` / `team` 的标准流程：

1. 调用 `POST /api/v1/activate/plus` 或 `POST /api/v1/activate/team`
2. 如果接口返回 `success: true` 且 `status: processing`，表示机器人已接单，任务进入处理中
3. 记录返回的 `requestId`
4. 继续调用 `GET /api/v1/requests/{request_id}` 轮询最终结果
5. 按任务查询结果判断成功或失败

关键点：

- 激活接口返回 `processing` 不代表最终成功
- 激活接口现在也会返回 `state`，处理中通常是 `running`，若首个响应已拿到终态则可能直接是 `completed`
- 最终结果只以 `GET /api/v1/requests/{request_id}` 为准
- 激活流程不会在 `POST /api/v1/activate/*` 结束时立即复原菜单
- 当调用 `GET /api/v1/requests/{request_id}` 且任务已进入终态时，服务会触发一次 `⬅️ 返回`，用于把 bot 菜单复原
- 这个返回动作按 `requestId` 只会触发一次

## 状态判定

`GET /api/v1/requests/{request_id}` 的核心字段：

- `state`
- `success`
- `status`
- `message`
- `rawMessage`
- `errorMessage`
- `errorType`

调用方建议按下面规则判断：

| 场景 | 判定条件 | 说明 |
| --- | --- | --- |
| 继续轮询 | `state = queued` 或 `state = running` | 任务还没结束 |
| 最终成功 | `state = completed` 且 `success = true` 且 `status = success` | 激活已成功 |
| 最终失败 | `state = completed` 且 `success = false` | 任务已结束，但业务结果失败 |
| 最终失败 | `state = failed` | 服务执行失败 |
| 最终失败 | `state = cancelled` | 任务已取消 |

补充口径：

- 当 `state` 是 `queued` 或 `running` 时，`success` 会返回 `null`
- 处理中阶段请主要看 `state/status/message`
- `completed` 只表示任务执行结束，不代表一定成功

## 激活文案判定

当前激活流程按下面文案分类：

### 中间态文案

命中后会让激活接口立即返回：

- `已收到请求`
- `正在生成`
- `生成支付链接`
- `正在处理`
- `处理中`
- `当前状态`
- `次查询`
- `请稍候`
- `请等待`
- 以及匹配：
  - `当前状态：...`
  - `第 n 次查询`

对应表现：

- `POST /api/v1/activate/*`
  - `success = true`
  - `status = processing`
- `GET /api/v1/requests/{request_id}` 轮询中
  - `state = queued` 或 `running`
  - `success = null`

### 成功文案

命中后最终会落成：

- `state = completed`
- `success = true`
- `status = success`

当前成功文案：

- 配置关键词：
  - `升级成功`
  - `激活成功`
  - `已升级`
  - `升级完成`
- 代码兜底：
  - 文案包含 `成功`
  - 或包含 `已升级`
  - 或包含 `升级完成`
  - 但文案里不能包含 `请求`

### 失败文案

命中后最终会落成：

- `state = completed`
- `success = false`
- `status = invalid_access_token`

当前失败文案：

- 配置关键词：
  - `Token 无效或已过期`
  - `Token 无效`
  - `额度已退回`
  - `重新获取后再试`
  - `激活失败`
- 代码兜底：
  - 文案包含 `无效`
  - `过期`
  - `退回`
  - `失败`
  - `重试`
  - `重新获取`

### 取消文案

命中后最终会落成：

- `state = completed`
- `success = false`
- `status = cancelled`

当前取消文案：

- `已取消`

### 未识别文案

只要不是中间态，也不匹配成功、失败、取消，就直接按失败处理。

对应表现：

- `state = completed`
- `success = false`
- `status = unknown`

示例：

- `余额不足。可点击 ⭐ 获取额度 进行充值，或联系 @Pehlicg 获取充值码。`

## 接口清单

### 1. 激活 Plus

- 方法：`POST`
- 路径：`/api/v1/activate/plus`

请求体：

```json
{
  "accessToken": "your_access_token"
}
```

返回重点：

- 处理中时：`success=true, status=processing`
- 最终结果请继续查 `requestId`

### 2. 激活 Team

- 方法：`POST`
- 路径：`/api/v1/activate/team`

请求体：

```json
{
  "accessToken": "your_access_token"
}
```

返回口径与 Plus 相同。

### 3. 查询任务状态

- 方法：`GET`
- 路径：`/api/v1/requests/{request_id}`

这是激活流程最终判定的唯一依据。

### 4. 查询余额

- 方法：`GET`
- 路径：`/api/v1/balance`

### 5. 兑换卡密

- 方法：`POST`
- 路径：`/api/v1/redeem`

请求体：

```json
{
  "cardCode": "your_card_code"
}
```

### 6. 取消当前菜单

- 方法：`POST`
- 路径：`/api/v1/cancel`

说明：

- 直接发送 `⬅️ 返回`
- 不进入工作流队列
- 不等待 bot 返回结果

### 7. 服务状态

- 方法：`GET`
- 路径：`/api/v1/status`

### 8. 健康检查

- 方法：`GET`
- 路径：`/healthz`

## 最小示例

### 激活 Team

```bash
curl -X POST "https://bot.joini.cloud/api/v1/activate/team" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d "{\"accessToken\":\"your_access_token\"}"
```

处理中响应示例：

```json
{
  "requestId": "your_request_id",
  "action": "activate_team",
  "state": "running",
  "success": true,
  "status": "processing",
  "message": "已收到请求，处理中...",
  "rawMessage": "已收到请求，处理中...",
  "balance": null,
  "queuePosition": 1,
  "queuedAt": "2026-04-03T00:00:00+08:00"
}
```

### 查询任务状态

```bash
curl "https://bot.joini.cloud/api/v1/requests/your_request_id" \
  -H "X-API-Key: your_api_key"
```

成功示例：

```json
{
  "requestId": "your_request_id",
  "action": "activate_team",
  "state": "completed",
  "success": true,
  "status": "success",
  "message": "✅ 激活成功",
  "rawMessage": "✅ 激活成功"
}
```

处理中示例：

```json
{
  "requestId": "your_request_id",
  "action": "activate_team",
  "state": "running",
  "success": null,
  "status": "processing",
  "message": "已收到请求，处理中...",
  "rawMessage": "已收到请求，处理中..."
}
```

失败示例：

```json
{
  "requestId": "your_request_id",
  "action": "activate_team",
  "state": "completed",
  "success": false,
  "status": "unknown",
  "message": "余额不足。可点击 ⭐ 获取额度 进行充值，或联系 @Pehlicg 获取充值码。",
  "rawMessage": "余额不足。可点击 ⭐ 获取额度 进行充值，或联系 @Pehlicg 获取充值码。"
}
```

## 备注

- 线上 OpenAPI 路径参数名是 `request_id`
- 如果客户端自己超时或断开，仍可继续用 `requestId` 轮询
- 队列满时接口会返回 `429`
- 如需完整字段定义，可直接查看 `https://bot.joini.cloud/openapi.json`
