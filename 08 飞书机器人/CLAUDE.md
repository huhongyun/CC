# 飞书机器人 + MiMo AI

## 架构
飞书用户 → 飞书服务器 → WebSocket长连接(Stream模式) → Python服务 → MiMo API → 飞书回复

## 技术选型
- **消息接收**：`lark-oapi` SDK 的 `ws.Client`（WebSocket 长连接，无需公网 IP）
- **AI 后端**：`mimo-v2.5`（小写），使用 `anthropic` Python SDK + 自定义 `base_url`
- **消息回复**：`lark-oapi` 的 `api_client.im.v1.message.reply`

## 文件结构
- `bot.py` — 主入口：启动 WebSocket + 事件分发
- `handlers.py` — 消息处理：区分私聊/群聊，提取文本，event_id 去重
- `ai_client.py` — MiMo API 封装（Anthropic SDK + base_url）
- `config.py` — 配置加载（从 .env 读取）
- `.env` — 实际密钥（不进 git）

## 开发规范
- 密钥、token、密码不进代码、不进 commit
- `.env` 已在 `.gitignore` 中排除
- 每条消息独立处理（第一版无记忆）

## 已知 SDK 踩坑（lark-oapi 1.6.5 + Python 3.14）
- **回调签名**：`register_p2_im_message_receive_v1` 的回调只传 1 个参数 `(event)`，不是 `(ctx, event)`
- **事件重试**：SDK 处理超时会重试投递同一 `event_id`，必须在 handler 里做去重
- **MiMo 响应格式**：返回 `thinking` + `text` 两种 block，不能直接取 `content[0].text`，需遍历找 `text` block
- **模型名**：必须小写 `mimo-v2.5`，大写会 400
