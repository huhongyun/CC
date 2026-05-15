import logging
import sys
import os

# Windows 终端 UTF-8 编码处理
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from config import FEISHU_APP_ID, FEISHU_APP_SECRET
from handlers import handle_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main():
    # 校验配置
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        logger.error("缺少 FEISHU_APP_ID 或 FEISHU_APP_SECRET，请检查 .env 文件")
        sys.exit(1)

    # 构建 API 客户端（用于发送/回复消息）
    api_client = lark.Client.builder() \
        .app_id(FEISHU_APP_ID) \
        .app_secret(FEISHU_APP_SECRET) \
        .log_level(lark.LogLevel.INFO) \
        .build()

    # 事件处理器：收到消息时调用 handle_message
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(
            lambda event: handle_message(event, api_client)
        ) \
        .build()

    # WebSocket 长连接客户端（Stream 模式，无需公网 IP）
    ws_client = lark.ws.Client(
        FEISHU_APP_ID,
        FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    logger.info("飞书机器人启动，正在建立 WebSocket 连接...")
    ws_client.start()


if __name__ == "__main__":
    main()
