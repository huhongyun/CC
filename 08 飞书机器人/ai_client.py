import anthropic
from config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL, SYSTEM_PROMPT


def ask_ai(user_text: str) -> str:
    """调用 MiMo V2.5 API，返回 AI 回复文本。"""
    try:
        client = anthropic.Anthropic(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL,
        )
        message = client.messages.create(
            model=MIMO_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
        )
        # MiMo 返回 thinking + text 两种 block，取 text block
        for block in message.content:
            if block.type == "text":
                return block.text
        return "未收到有效回复。"
    except anthropic.APITimeoutError:
        return "AI 请求超时，请稍后重试。"
    except anthropic.RateLimitError:
        return "AI 服务繁忙，请稍后重试。"
    except Exception as e:
        return f"AI 调用出错：{e}"
