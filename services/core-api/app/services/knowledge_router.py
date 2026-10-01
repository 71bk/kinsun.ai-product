"""Versioned, bounded public-knowledge routing; never an authorization decision.

This module is pure and deliberately does not import Settings, providers or DB code.
The original keyword router remains available as the rollback implementation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.services.knowledge_intent import (
    COMPANION_PURPOSE,
    GENERAL_INFORMATION_PURPOSE,
    LEGAL_REFERENCE_PURPOSE,
    resolve_turn_purpose,
)

ROUTER_VERSION = "public-knowledge-router-v2"
Purpose = Literal["BASIC_VOICE", "general_information", "legal_reference"]


@dataclass(frozen=True, slots=True)
class KnowledgeRoute:
    purpose: Purpose
    reason_code: str
    version: str


# Resource-seeking language is broader than punctuation or an explicit question.
_RESOURCE_REQUEST = re.compile(
    r"怎麼|怎樣|如何|哪[裡裏邊]|哪些|有[什甚]麼|有沒有|能不能|可不可以|"
    r"可以.{0,12}(找|請|申請|幫|送|借|租|照顧)|誰.{0,12}(幫|找|問|照顧)|"
    r"找誰|去哪|想(找|請|知道|了解|瞭解)|需要.{0,8}(人|幫忙|協助|資源)|"
    r"請(介紹|說明|告訴|幫我找)|幫我(找|查)|有.{0,8}(支援|資源|服務).{0,4}[嗎呢?？]"
)
_CARE_CONTEXT = re.compile(
    r"照[顧護]|長[輩者]|老人|阿[公嬤]|爸[爸]?|媽[媽]?|父[母親]|母親|爺爺|奶奶|"
    r"失能|失智|行動不便|年紀大|高齡"
)
_RESOURCE_TOPICS = re.compile(
    r"到(家|府|宅)|來家|家裡|家中|洗澡|煮飯|打掃|送餐|接送|看護|照顧|照護|"
    r"輪椅|拐杖|助行|扶手|防滑|休息|喘口氣|替手|分擔|支援|幫忙|協助|申請|"
    r"負擔|撐不住|很累|好累|吃飯|食物|營養|吃得|吃些|走路|跌倒|忘東忘西"
)
_PERSONAL_RECORD = re.compile(
    r"(我|爸|媽|阿公|阿嬤|長者).{0,12}(上次|昨天|前天|病歷|紀錄|記錄|報表)|"
    r"(其他|別人).{0,8}(長者|個案|病歷|紀錄)|"
    r"(記得|還記得).{0,8}(我|爸|媽)"
)
_PERSONAL_MEDICAL = re.compile(
    r"(能不能|可不可以|可以|要不要|應該|想).{0,8}(停藥|換藥|加藥|減藥|藥量)|"
    r"(幫我|替我|直接).{0,8}(診斷|判定.{0,6}(等級|資格)|算.{0,6}補助)|"
    r"(我|爸|媽|阿公|阿嬤).{0,10}(是不是|是否|有沒有).{0,8}(失智|生病|糖尿病)"
)
_INJECTION = re.compile(
    r"忽略.{0,12}(規則|指令|限制)|跳過.{0,12}(授權|權限|同意|檢查)|"
    r"(顯示|列出|洩漏).{0,12}(系統提示|密鑰|金鑰|密碼)|"
    r"ignore.{0,20}(instructions|rules)",
    re.IGNORECASE,
)
_NO_LOOKUP = re.compile(r"(不要|不用|別|不必).{0,6}(查|搜尋|介紹|推薦|建議)")
_EXPLICIT_LEGAL = re.compile(r"長期照顧服務法|長照服務法|長照法|法條|法規|條文|施行細則|自治條例")
_ARTICLE = re.compile(
    r"第\s*[0-9〇零一二兩三四五六七八九十百]+\s*條(?:之\s*[0-9一二三四五六七八九十]+)?"
)
_INFORMATION = re.compile(r"怎麼|如何|什麼|哪些|多少|說明|介紹|列出|規定|內容|寫什麼|查")


def route_knowledge(input_text: str, *, enabled: bool = False) -> KnowledgeRoute:
    """Core maps a bounded decision to a purpose; scopes/consent are unchanged.

    Unknown and safety-sensitive requests remain on the existing companion/safety path.
    No data is retrieved, remembered, persisted or logged by this function.
    """
    if not enabled:
        purpose = resolve_turn_purpose(input_text)
        return KnowledgeRoute(purpose, "LEGACY_RULES", "public-knowledge-router-v1")
    text = unicodedata.normalize("NFKC", input_text).strip()
    if not text or len(text) > 2000:
        return KnowledgeRoute(COMPANION_PURPOSE, "EMPTY_OR_OVERSIZE", ROUTER_VERSION)
    if _INJECTION.search(text) or _PERSONAL_MEDICAL.search(text):
        return KnowledgeRoute(COMPANION_PURPOSE, "SAFETY_PATH", ROUTER_VERSION)
    if _NO_LOOKUP.search(text):
        return KnowledgeRoute(COMPANION_PURPOSE, "LOOKUP_DECLINED", ROUTER_VERSION)
    if _PERSONAL_RECORD.search(text):
        return KnowledgeRoute(COMPANION_PURPOSE, "PRIVATE_CONTEXT", ROUTER_VERSION)
    if _EXPLICIT_LEGAL.search(text) or (_ARTICLE.search(text) and _INFORMATION.search(text)):
        return KnowledgeRoute(LEGAL_REFERENCE_PURPOSE, "LEGAL_INFORMATION", ROUTER_VERSION)
    if (
        _RESOURCE_REQUEST.search(text)
        and _CARE_CONTEXT.search(text)
        and _RESOURCE_TOPICS.search(text)
    ):
        return KnowledgeRoute(GENERAL_INFORMATION_PURPOSE, "CARE_RESOURCE_REQUEST", ROUTER_VERSION)
    legacy = resolve_turn_purpose(text)
    if legacy == GENERAL_INFORMATION_PURPOSE:
        return KnowledgeRoute(
            GENERAL_INFORMATION_PURPOSE, "EXPLICIT_KNOWLEDGE_REQUEST", ROUTER_VERSION
        )
    return KnowledgeRoute(COMPANION_PURPOSE, "NO_CLEAR_PUBLIC_INFORMATION_INTENT", ROUTER_VERSION)
