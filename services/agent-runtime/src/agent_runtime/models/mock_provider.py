import re

from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.provider import ModelProvider


class MockModelProvider(ModelProvider):
    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        text = request.input_text.strip()
        if not text:
            return "收到，請再提供更多訊息讓我更好幫助您。"

        is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in text)
        meal_match = re.search(r"我今天早餐吃(?P<food>[^。.!!?！？\n]*)", text)
        if meal_match:
            food = meal_match.group("food").strip().strip("。.!!?！？")
            if not food:
                return "知道了，您今天早餐有吃清楚的東西了。還有其他想和我分享的事情嗎？"
            return f"知道了，您今天早餐吃了{food}。還有其他想和我分享的事情嗎？"

        if is_chinese:
            return f"謝謝您和我分享「{text}」。還有其他想和我聊聊的嗎？"

        if language.lower().startswith("en"):
            return f"Thanks for sharing: {text}. Is there anything else you'd like to tell me?"

        return f"Thanks, I received: {text}"
