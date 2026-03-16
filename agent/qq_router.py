import re
import time

from config import BOT_ALIASES


BOT_ALIAS_TOKENS = tuple(
    dict.fromkeys(alias.strip().lower() for alias in BOT_ALIASES if alias.strip())
)
BOT_PREFIX_TOKENS = tuple(
    token for alias in BOT_ALIAS_TOKENS for token in (alias, f"/{alias}")
)


class QQRouter:
    def __init__(
        self,
        state_store,
        logger,
        cooldown_seconds: int = 45,
        llm_cooldown_seconds: int = 15,
        duplicate_reply_cooldown_seconds: int = 600,
    ):
        self.state_store = state_store
        self.logger = logger
        self.cooldown_seconds = cooldown_seconds
        self.llm_cooldown_seconds = llm_cooldown_seconds
        self.duplicate_reply_cooldown_seconds = duplicate_reply_cooldown_seconds
        self.runtime = {}

    def _runtime_for_group(self, group_id: str):
        key = str(group_id)
        if key not in self.runtime:
            self.runtime[key] = {
                "last_reply_at": 0.0,
                "last_llm_at": 0.0,
                "llm_backoff_until": 0.0,
                "llm_consecutive_failures": 0,
                "recent_bot_context_until": 0.0,
                "observed_count": 0,
                "reply_count": 0,
                "last_audit_observed_count": 0,
                "last_audit_reply_count": 0,
                "recent_messages": [],
                "last_duplicate_reply_text": "",
                "last_duplicate_reply_at": 0.0,
            }
        return self.runtime[key]

    def _duplicate_reply_allowed(self, runtime: dict, text: str, now: float):
        normalized = " ".join((text or "").split())
        if not normalized:
            return False
        last_text = str(runtime.get("last_duplicate_reply_text", "") or "")
        last_at = float(runtime.get("last_duplicate_reply_at", 0.0) or 0.0)
        if normalized != last_text:
            return True
        return (now - last_at) >= self.duplicate_reply_cooldown_seconds

    def _high_signal_state_hints(self, text: str):
        lowered = (text or "").lower()
        hints = []

        affection_patterns = [
            "喜欢你",
            "爱你",
            "想你",
            "表白",
            "抱抱",
            "亲亲",
            "最喜欢你",
            "あなたが好き",
        ]
        appreciation_patterns = ["谢谢", "多谢", "辛苦了", "你真好", "谢啦", "感谢"]
        trusting_patterns = [
            "只敢和你说",
            "只能和你说",
            "不要告诉别人",
            "替我保密",
            "其实我想",
            "我想和你说个秘密",
        ]
        supportive_patterns = [
            "我支持你",
            "我站你这边",
            "我会陪你",
            "我帮你说话",
            "我信你",
        ]
        apology_patterns = ["对不起", "抱歉", "是我错了", "我错了", "不好意思"]
        dismissive_patterns = ["算了吧", "随便你", "懒得理你"]
        insulting_patterns = ["傻逼", "弱智", "烦死了", "滚", "有病", "你真恶心"]
        naming_patterns = [
            "以后叫我",
            "改叫我",
            "你可以叫我",
            "别叫我",
            "称呼我",
            "怎么叫我",
        ]
        memory_patterns = ["记一下", "记住", "别忘了", "记着", "帮我记"]

        if any(pattern in lowered for pattern in affection_patterns):
            hints.append("affectionate")
        if any(pattern in lowered for pattern in appreciation_patterns):
            hints.append("appreciative")
        if any(pattern in lowered for pattern in trusting_patterns):
            hints.append("trusting")
        if any(pattern in lowered for pattern in supportive_patterns):
            hints.append("supportive")
        if any(pattern in lowered for pattern in apology_patterns):
            hints.append("sincere_apology")
        if any(pattern in lowered for pattern in dismissive_patterns):
            hints.append("dismissive")
        if any(pattern in lowered for pattern in insulting_patterns):
            hints.append("insulting")
        if any(pattern in lowered for pattern in naming_patterns):
            hints.append("naming_update")
        if any(pattern in lowered for pattern in memory_patterns):
            hints.append("memory_candidate")

        return hints

    def _track_duplicate_message(
        self, runtime: dict, user_id: str, text: str, now: float
    ):
        normalized = " ".join((text or "").split())
        history = runtime.setdefault("recent_messages", [])
        history.append({"time": now, "user_id": str(user_id), "text": normalized})
        runtime["recent_messages"] = [
            item
            for item in history[-30:]
            if now - float(item.get("time", 0.0)) <= 300 and item.get("text")
        ]

        if not normalized:
            return {
                "duplicate_message_count": 0,
                "duplicate_distinct_users": 0,
                "duplicate_repeat_candidate": False,
                "duplicate_text": "",
            }

        matches = [
            item
            for item in runtime["recent_messages"]
            if item.get("text") == normalized
        ]
        distinct_users = {
            item.get("user_id") for item in matches if item.get("user_id")
        }
        raw_repeat_candidate = len(matches) >= 2 and len(normalized) <= 60
        repeat_allowed = raw_repeat_candidate and self._duplicate_reply_allowed(
            runtime, normalized, now
        )
        return {
            "duplicate_message_count": len(matches),
            "duplicate_distinct_users": len(distinct_users),
            "duplicate_repeat_candidate": repeat_allowed,
            "duplicate_repeat_blocked": raw_repeat_candidate and not repeat_allowed,
            "duplicate_text": normalized if raw_repeat_candidate else "",
        }

    def _consume_periodic_audit(self, runtime: dict):
        observed_count = int(runtime.get("observed_count", 0))
        reply_count = int(runtime.get("reply_count", 0))
        last_observed = int(runtime.get("last_audit_observed_count", 0))
        last_reply = int(runtime.get("last_audit_reply_count", 0))
        needs_audit = (observed_count - last_observed) >= 12 or (
            reply_count - last_reply
        ) >= 5
        if needs_audit:
            runtime["last_audit_observed_count"] = observed_count
            runtime["last_audit_reply_count"] = reply_count
        return needs_audit

    def _contains_name(self, text: str):
        lowered = text.lower()
        return any(token in lowered for token in BOT_ALIAS_TOKENS)

    def _mentions_persona_topics(self, text: str):
        keywords = [
            "医院",
            "病房",
            "天台",
            "楼顶",
            "钢栏",
            "栏杆",
            "橘子",
            "消毒水",
            "梦",
            "昏迷",
            "醒来",
            "同学",
            "坠落",
            "坠楼",
            "跳楼",
            "rooftop",
            "hospital",
            "coma",
            "orange",
            "oranges",
            "dream",
        ]
        lowered = text.lower()
        return any(keyword in text or keyword in lowered for keyword in keywords)

    def _is_question(self, text: str):
        return any(
            token in text
            for token in ["?", "？", "吗", "嘛", "呢", "怎么看", "怎么", "为什么"]
        )

    def _is_emotional_followup(self, text: str):
        keywords = [
            "好感",
            "感动",
            "难过",
            "开心",
            "委屈",
            "喜欢",
            "想你",
            "在吗",
            "在不",
            "陪我",
        ]
        return any(token in text for token in keywords)

    def _asks_for_help(self, text: str):
        keywords = [
            "帮",
            "看看",
            "这是啥",
            "什么",
            "能不能",
            "可以吗",
            "你会",
            "你能",
            "解释",
            "复述",
            "回忆",
            "整理",
        ]
        return any(token in text for token in keywords)

    def _addresses_second_person(self, text: str):
        keywords = [
            "你来",
            "你看",
            "你觉得",
            "你说",
            "你能",
            "你会",
            "你帮",
            "你去",
            "你要不",
            "给我",
            "帮我",
            "跟你说",
            "问你",
        ]
        return any(token in text for token in keywords)

    def _looks_like_command(self, text: str):
        stripped = text.strip().lower()
        return (
            stripped.startswith("/")
            or stripped.startswith(".")
            or stripped.startswith("!")
        )

    def _clean_message(self, text: str):
        text = re.sub(r"\[CQ:reply,id=\d+\]", "", text)
        text = re.sub(r"\[CQ:at,qq=\d+[^\]]*\]", "", text)
        text = re.sub(r"\[CQ:image,[^\]]*\]", " [图片] ", text)
        return text.strip()

    def filter_event(
        self, event: dict, bot_user_id: str, reply_context: dict | None = None
    ):
        group_id = str(event.get("group_id", ""))
        if not group_id:
            return False, "missing_group_id", None, None
        if not self.state_store.is_group_allowed(group_id):
            return False, "group_not_allowed", None, None

        user_id = str(event.get("user_id", ""))
        if user_id and bot_user_id and user_id == str(bot_user_id):
            return False, "ignore_self", None, None

        raw_message = event.get("raw_message") or ""
        cleaned = self._clean_message(raw_message)
        if not cleaned:
            return False, "empty_message", None, None

        runtime = self._runtime_for_group(group_id)
        now = time.time()
        runtime["observed_count"] = int(runtime.get("observed_count", 0)) + 1
        at_ids = re.findall(r"\[CQ:at,qq=(\d+)[^\]]*\]", raw_message)
        bot_id = str(bot_user_id) if bot_user_id else ""
        is_at = bool(bot_id) and bot_id in at_ids
        at_other_users = [at_id for at_id in at_ids if not bot_id or at_id != bot_id]
        at_other_only = bool(at_other_users) and not is_at
        has_reply = bool(re.search(r"\[CQ:reply,id=\d+\]", raw_message))
        reply_targets_bot = bool((reply_context or {}).get("reply_targets_bot"))
        has_image = "[CQ:image," in raw_message
        starts_with_prefix = cleaned.lower().startswith(BOT_PREFIX_TOKENS)
        contains_name = self._contains_name(cleaned)
        persona_topic_signal = self._mentions_persona_topics(cleaned)
        direct_question = self._is_question(cleaned)
        asks_for_help = self._asks_for_help(cleaned)
        addresses_second_person = self._addresses_second_person(cleaned)
        looks_like_command = self._looks_like_command(cleaned)
        recent_context = now < runtime["recent_bot_context_until"]
        emotional_followup = self._is_emotional_followup(cleaned)
        direct_engagement = (
            is_at or starts_with_prefix or contains_name or reply_targets_bot
        )
        targeted_question = direct_question and (
            is_at
            or contains_name
            or reply_targets_bot
            or asks_for_help
            or has_image
            or recent_context
        )
        contextual_engagement = recent_context and (
            direct_question or emotional_followup or contains_name or reply_targets_bot
        )
        short_contextual_followup = (
            recent_context and len(cleaned) <= 6 and not looks_like_command
        )
        relevant_message = (
            direct_engagement
            or targeted_question
            or contextual_engagement
            or short_contextual_followup
        )
        if at_other_only and not (
            starts_with_prefix or contains_name or reply_targets_bot
        ):
            return (
                False,
                "at_other_user",
                cleaned,
                {
                    "is_at": is_at,
                    "at_other_only": True,
                    "at_other_user_ids": at_other_users,
                    "has_reply": has_reply,
                    "reply_targets_bot": reply_targets_bot,
                    "starts_with_prefix": starts_with_prefix,
                    "contains_name": contains_name,
                    "store_as_context": False,
                },
            )
        high_signal_hints = self._high_signal_state_hints(cleaned)
        duplicate_signal = self._track_duplicate_message(runtime, user_id, cleaned, now)
        periodic_self_audit = self._consume_periodic_audit(runtime)

        trigger_reason = "observe_all"
        if is_at or starts_with_prefix:
            trigger_reason = "direct_trigger"
        elif reply_targets_bot:
            trigger_reason = "reply_trigger"
        elif contains_name and direct_question:
            trigger_reason = "named_question"
        elif has_image and direct_question:
            trigger_reason = "image_question"
        elif addresses_second_person and direct_question and recent_context:
            trigger_reason = "second_person_question"
        elif asks_for_help and direct_question and (recent_context or contains_name):
            trigger_reason = "help_request"
        elif recent_context and direct_question:
            trigger_reason = "context_question"
        elif recent_context and emotional_followup:
            trigger_reason = "context_emotional_followup"
        elif short_contextual_followup:
            trigger_reason = "context_short_followup"
        elif persona_topic_signal:
            trigger_reason = "persona_topic"
        elif duplicate_signal["duplicate_repeat_candidate"]:
            trigger_reason = "duplicate_message"

        metadata = {
            "is_at": is_at,
            "at_other_only": at_other_only,
            "at_other_user_ids": at_other_users,
            "starts_with_prefix": starts_with_prefix,
            "contains_name": contains_name,
            "has_reply": has_reply,
            "reply_targets_bot": reply_targets_bot,
            "reply_sender_id": (reply_context or {}).get("reply_sender_id"),
            "reply_sender_name": (reply_context or {}).get("reply_sender_name"),
            "has_image": has_image,
            "direct_question": direct_question,
            "asks_for_help": asks_for_help,
            "addresses_second_person": addresses_second_person,
            "looks_like_command": looks_like_command,
            "recent_context": recent_context,
            "emotional_followup": emotional_followup,
            "cooldown_active": now - runtime["last_reply_at"] < self.cooldown_seconds,
            "llm_cooldown_active": (
                now - runtime["last_llm_at"] < self.llm_cooldown_seconds
                or now < float(runtime.get("llm_backoff_until", 0.0) or 0.0)
            ),
            "direct_engagement": direct_engagement,
            "targeted_question": targeted_question,
            "contextual_engagement": contextual_engagement,
            "short_contextual_followup": short_contextual_followup,
            "persona_topic_signal": persona_topic_signal,
            "rule_relevant": relevant_message,
            "ordinary_message_candidate": not (
                direct_engagement
                or targeted_question
                or contextual_engagement
                or short_contextual_followup
                or persona_topic_signal
                or high_signal_hints
                or duplicate_signal.get("duplicate_repeat_candidate")
            ),
            "observed_count": runtime.get("observed_count", 0),
            "reply_count": runtime.get("reply_count", 0),
            "periodic_self_audit": periodic_self_audit,
            "high_signal_hints": high_signal_hints,
            **duplicate_signal,
            "store_as_context": True,
        }

        return True, trigger_reason, cleaned, metadata

    def mark_llm_checked(self, group_id: str):
        runtime = self._runtime_for_group(group_id)
        runtime["last_llm_at"] = time.time()

    def mark_llm_succeeded(self, group_id: str):
        runtime = self._runtime_for_group(group_id)
        runtime["llm_backoff_until"] = 0.0
        runtime["llm_consecutive_failures"] = 0

    def mark_llm_failed(self, group_id: str):
        runtime = self._runtime_for_group(group_id)
        now = time.time()
        failures = int(runtime.get("llm_consecutive_failures", 0)) + 1
        runtime["llm_consecutive_failures"] = failures
        runtime["last_llm_at"] = now
        backoff_seconds = self.llm_cooldown_seconds * min(failures, 3)
        runtime["llm_backoff_until"] = now + backoff_seconds
        return backoff_seconds

    def should_skip_llm(self, group_id: str, metadata: dict | None = None):
        runtime = self._runtime_for_group(group_id)
        now = time.time()
        if now >= float(runtime.get("llm_backoff_until", 0.0) or 0.0):
            return False
        metadata = metadata or {}
        if metadata.get("direct_engagement"):
            return False
        return bool(metadata.get("ordinary_message_candidate"))

    def mark_replied(self, group_id: str, duplicate_text: str | None = None):
        runtime = self._runtime_for_group(group_id)
        now = time.time()
        runtime["last_llm_at"] = now
        runtime["last_reply_at"] = now
        runtime["recent_bot_context_until"] = now + 60
        runtime["reply_count"] = int(runtime.get("reply_count", 0)) + 1
        normalized = " ".join((duplicate_text or "").split())
        if normalized:
            runtime["last_duplicate_reply_text"] = normalized
            runtime["last_duplicate_reply_at"] = now
        self.state_store.touch_group_activity(group_id, bot_replied=True)
