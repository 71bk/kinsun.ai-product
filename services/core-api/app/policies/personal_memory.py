"""Bounded, Core-owned self-statement recognition; no model claims are trusted."""

import re
import unicodedata
from dataclasses import dataclass

PERSONAL_MEMORY_POLICY = "personal-memory-2026-09-17.v1"
PERSONAL_MEMORY_EXTRACTOR = "core-self-statement-v1"
PERSONAL_MEMORY_KINDS = frozenset(
    {"MUSIC_PREFERENCE", "HOBBY", "PREFERRED_ADDRESS", "FOOD_PREFERENCE", "DAILY_ROUTINE"}
)


@dataclass(frozen=True)
class PersonalStatement:
    kind: str
    memory_type: str
    content: str


def extract_personal_statement(text: str) -> PersonalStatement | None:
    """Match an entire explicit statement, never a positive substring in a denial."""
    value = unicodedata.normalize("NFKC", text).strip().rstrip("。.!！").strip()
    if not value or len(value) > 100:
        return None
    # Intentionally small vocabulary: unsupported input remains ordinary conversation.
    patterns = (
        (
            r"我(?:很|最)?喜歡聽(?P<value>老歌|台語歌|臺語歌|民歌|古典音樂|流行音樂|爵士樂|鄧麗君(?:的歌)?)",
            "MUSIC_PREFERENCE",
            "PREFERENCE",
            "我喜歡聽{value}。",
        ),
        (
            r"我(?:很|最)?喜歡(?P<value>散步|種花|園藝|畫畫|攝影|下棋|看書|閱讀|唱歌|跳舞|編織|釣魚)",
            "HOBBY",
            "PREFERENCE",
            "我喜歡{value}。",
        ),
        (
            r"我(?:很|最)?喜歡(?P<value>(?:喝(?:豆漿|牛奶|茶|咖啡)|吃(?:粥|麵|飯|水果|饅頭|麵包)))",
            "FOOD_PREFERENCE",
            "PREFERENCE",
            "我喜歡{value}。",
        ),
        (
            r"我(?:每天|每日)(?:都)?早餐(?:都|會|固定)?(?P<value>(?:喝(?:豆漿|牛奶|茶)|吃(?:粥|麵|飯|水果|饅頭|麵包)))",
            "DAILY_ROUTINE",
            "ROUTINE",
            "我每天早餐{value}。",
        ),
        (
            r"(?:請)?叫我(?P<value>[\u4e00-\u9fff]{1,8})",
            "PREFERRED_ADDRESS",
            "COMMUNICATION_PREFERENCE",
            "請叫我{value}。",
        ),
    )
    for pattern, kind, memory_type, template in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            chosen = match.group("value")
            if kind == "PREFERRED_ADDRESS" and any(
                word in chosen
                for word in (
                    "不要",
                    "爸爸",
                    "媽媽",
                    "醫生",
                    "病",
                    "藥",
                    "忽略",
                    "系統",
                    "指令",
                    "以前",
                    "如果",
                    "不是",
                )
            ):
                return None
            return PersonalStatement(kind, memory_type, template.format(value=chosen))
    return None
