import os
from dotenv import load_dotenv

load_dotenv()

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
MIMO_API_KEY = os.getenv("MIMO_API_KEY")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic")
MIMO_MODEL = os.getenv("MIMO_MODEL", "MiMo-V2.5")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "你是一个友好的AI助手。")
