# 飞书机器人 + MiMo AI

飞书私聊/群聊机器人，接入小米 MiMo V2.5 大模型，通过 WebSocket 长连接接收消息并实时回复。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，填入实际值：

```bash
cp .env.example .env
```

需要填写：
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` — 飞书开放平台应用凭证
- `MIMO_API_KEY` — MiMo API 密钥

### 3. 启动

```bash
python bot.py
```

启动后会自动建立 WebSocket 长连接，在飞书中给机器人发消息即可测试。

## 前置条件

- 飞书开放平台已创建应用并启用「机器人」能力
- 应用已订阅事件 `im.message.receive_v1`（接收消息）
- 订阅方式选择「长连接」
- 应用已发布且状态为「已启用」

## 文件说明

| 文件 | 说明 |
|------|------|
| `bot.py` | 主入口：启动 WebSocket + 事件分发 |
| `handlers.py` | 消息处理：文本提取、群聊 @清理、event_id 去重 |
| `ai_client.py` | MiMo API 封装（Anthropic SDK 兼容接口） |
| `config.py` | 从 `.env` 加载配置 |
| `.env` | 实际密钥（不进 git） |
