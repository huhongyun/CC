import json
import logging
from collections import OrderedDict

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

from ai_client import ask_ai

logger = logging.getLogger(__name__)

# event_id 去重：SDK 可能因处理超时重试同一事件
_seen_events: OrderedDict = OrderedDict()
_MAX_SEEN = 500


def extract_text(message) -> str:
    """从消息体中提取纯文本内容。"""
    content = json.loads(message.content)
    msg_type = message.message_type

    if msg_type == "text":
        return content.get("text", "").strip()

    # 群聊中 @机器人 会产生 @_user_1 占位符，需要清理
    # 但如果用户发的是纯 @，提取出来可能是空的
    return ""


def clean_mention_text(text: str) -> str:
    """去除飞书群聊中 @机器人 的占位符文本。

    飞书在群聊中 @机器人 时，text 字段会包含 @_user_1 等占位符，
    需要去掉这些占位符，只保留用户实际输入的文本。
    """
    import re
    # 飞书的 @占位符格式：@_user_N，也可能带名字
    cleaned = re.sub(r"@_user_\d+\s*", "", text).strip()
    return cleaned


def handle_message(data: P2ImMessageReceiveV1, api_client: lark.Client):
    """处理接收到的消息事件。"""
    # event_id 去重：SDK 可能因处理超时重试同一事件
    event_id = data.header.event_id
    if event_id in _seen_events:
        logger.debug(f"跳过重复事件: {event_id}")
        return
    _seen_events[event_id] = True
    if len(_seen_events) > _MAX_SEEN:
        _seen_events.popitem(last=False)

    event = data.event
    message = event.message
    sender = event.sender

    chat_type = message.chat_type  # "p2p" 或 "group"
    msg_type = message.message_type

    logger.info(f"收到消息: chat_type={chat_type}, msg_type={msg_type}, "
                f"sender={sender.sender_id.open_id}")

    # 只处理文本消息
    if msg_type != "text":
        _reply_text(api_client, message.message_id, "目前仅支持文本消息，请发送文字内容。")
        return

    # 提取文本
    text = extract_text(message)
    if chat_type == "group":
        text = clean_mention_text(text)

    if not text:
        _reply_text(api_client, message.message_id, "未检测到有效文本，请重新输入。")
        return

    logger.info(f"用户文本: {text}")

    # 调用 AI
    ai_reply = ask_ai(text)
    logger.info(f"AI 回复: {ai_reply[:100]}...")

    # 回复消息
    _reply_text(api_client, message.message_id, ai_reply)


def _reply_text(api_client: lark.Client, message_id: str, text: str):
    """通过飞书 API 回复一条文本消息。"""
    body = ReplyMessageRequestBody.builder() \
        .content(json.dumps({"text": text})) \
        .msg_type("text") \
        .build()

    request = ReplyMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(body) \
        .build()

    response = api_client.im.v1.message.reply(request)

    if not response.success():
        logger.error(f"回复消息失败: code={response.code}, msg={response.msg}")
