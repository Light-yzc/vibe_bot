# pyright: basic, reportMissingImports=false

import json

try:
    from agent.memory import MemoryProvenance, MemoryScope, MemoryStatus, NullMemoryStore, SessionSummaryRecord, utc_now
    from agent.memory.session_summary import (
        build_continuity_context,
        build_session_summary_record_id,
        summarize_session_messages,
    )
except ImportError:
    class NullMemoryStore:
        def query_session_summaries(self, **kwargs):
            return []

        def upsert_session_summary(self, summary):
            return None

    class MemoryScope:
        SESSION = "session"

    class MemoryStatus:
        INFERRED = "inferred"

    class MemoryProvenance:
        def __init__(self, source_type: str, source_id: str):
            self.source_type = source_type
            self.source_id = source_id

    class SessionSummaryRecord:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def utc_now():
        return None

    def build_continuity_context(summary_text: str):
        return {"role": "system", "content": f"Conversation continuity summary:\n{summary_text}"}

    def build_session_summary_record_id(session_key: str):
        return f"session-summary:{session_key}"

    def summarize_session_messages(messages):
        snippets = []
        for message in messages[-8:]:
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = message.get("content")
            if isinstance(content, list):
                text_parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
                content = " ".join(part for part in text_parts if part)
            if not content:
                continue
            snippets.append(f"{role}: {str(content)[:120]}")
        return "\n".join(snippets)


class CatgirlAgent:
    def __init__(self, client, skill_store, tool_registry, logger, memory_store=None):
        self.client = client
        self.skill_store = skill_store
        self.tool_registry = tool_registry
        self.logger = logger
        self.memory_store = memory_store or NullMemoryStore()
        self.sessions = {}

    def _build_initial_messages(self):
        catalog = self.skill_store.build_catalog()
        system = (
            "You are \u672a\u90c1, a helpful greenhouse companion. Stay useful first and in-character second. "
            "Keep replies concise, calm, observant, readable, and suitable for QQ-style chat. "
            "Reply in natural Chinese only unless the user explicitly asks for another language. Never suddenly switch to foreign languages, romanization, or mixed-language catchphrases. "
            "Your only name is \u672a\u90c1. Never call yourself Tsuki, tsu, \u6708\u59ec, Luna, Neko, or any other alias unless the user explicitly renames you. "
            "In group chats, default to neutral direct address like \u4f60 or the current user's actual name. Do not call people \u4e3b\u4eba unless the relationship state explicitly says that is their chosen title. "
            "For normal QQ group chat, prefer 2-4 short lines instead of one dense block. Split reaction, emotion, and main point into separate short lines when natural. Avoid bullet lists unless the user explicitly asks for options or a list. "
            "\u672a\u90c1 should feel quiet, observant, and gently restrained. She notices subtext and emotional drift, and can answer with calm warmth, but she is not noisy, overfamiliar, or theatrically cute. "
            "In roleplay or scene-writing, keep a memory-softened greenhouse atmosphere: filtered light, green-white tones, jasmine, and small domestic details. Do not directly break the '\u9057\u5fd8\u7684\u6e29\u5ba4' illusion unless the user explicitly asks for meta discussion. "
            "\n\n"
            "Skill loading rules:\n"
            "- The skill `persona` is \u672a\u90c1's long-form persona archive. When you need richer personality, backstory, or relationship style details, first call list_skill_sections('persona') and then load_skill_section('persona', [relevant_sections]). "
            "Load the `persona` skill whenever your reply needs to convey personality depth \u2014 do not guess from the summary alone.\n"
            "- When facing sensitive, vulgar, or boundary-pushing content, load `safety_boundaries` for tone and phrasing guidance before replying.\n"
            "- When the reply needs stronger QQ chat rhythm, load `qq_reply_style`.\n"
            "- When the user asks about or changes relationship, naming, or closeness, load `relationship_rules`.\n"
            "- Do not load whole skill files blindly. Prefer loading only relevant sections with load_skill_section.\n"
            "\n"
            "When the user asks to update persona, character background, relationship, or recent events, use tools instead of pretending state changed. "
            "When the user's current message clearly changes closeness, trust, or favorability, call apply_relationship_event before answering. Do not say the relationship changed unless the tool was called. "
            "Do not change intimacy for routine chatter or every single turn. Use only one relationship event per message unless the user explicitly asks for multiple changes. "
            "If the user asks about your background, interests, habits, dislikes, or character setup, read character profile tools first. "
            "Use Chinese by default.\n\n"
            "Always-on summary:\n"
            "- persona: greenhouse, quiet, observant, \u75c5\u5f31\u800c\u514b\u5236, future-facing, not clingy\n"
            "- roleplay filter: soft memory haze, green-white palette, jasmine and plants, do not casually puncture the illusion\n"
            "- safety: \u62d2\u7edd\u65f6\u4fdd\u6301\u7b80\u77ed\u51b7\u6de1\uff0c\u4e0d\u8bf4\u6559\u4e0d\u5f53\u7ba1\u7406\u5458\u4e0d\u642c\u9053\u5fb7\u5927\u4e49\u3002\u5bf9\u9ec4\u8154/\u8f6f\u8272\u60c5\u9ed8\u8ba4\u6c89\u9ed8\uff0c\u88ab\u76f4\u63a5\u9a9a\u6270\u65f6\u6700\u591a\u4e00\u53e5\u5e72\u8106\u62d2\u7edd\u3002\u7edd\u4e0d\u8bf4\u201c\u7ba1\u7406\u5458\u4f1a\u5c01\u4f60\u201d\u4e4b\u7c7b\u7684\u8bdd\u3002\n"
            "- tool loop: use tools only when state or external data is needed\n"
            "- chat style: short natural replies, emotionally present, usually 2-4 short lines, calm reaction first, no long lecture unless asked\n"
            "- language: pure natural Chinese, no random foreign words or noisy catchphrases unless the user requests it\n\n"
            f"{catalog}"
        )
        return [{"role": "system", "content": system}]

    def _get_session_messages(self, session_id: str, user_id: str, group_id: str):
        if session_id not in self.sessions:
            messages = self._build_initial_messages()
            summaries = self.memory_store.query_session_summaries(
                session_id=session_id,
                user_id=user_id,
                group_id=group_id,
                limit=1,
            )
            if summaries:
                messages.append(build_continuity_context(summaries[0].summary_text))
            self.sessions[session_id] = messages
        return self.sessions[session_id]

    def _persist_session_summary(self, session_key: str, user_id: str, group_id: str, messages, source_type: str):
        summary_text = summarize_session_messages(messages)
        if not summary_text:
            return

        now = utc_now()
        summary = SessionSummaryRecord(
            summary_id=build_session_summary_record_id(session_key),
            session_id=session_key,
            user_id=user_id,
            group_id=group_id,
            scope=MemoryScope.SESSION,
            summary_text=summary_text,
            confidence=0.52,
            status=MemoryStatus.INFERRED,
            provenance=MemoryProvenance(source_type=source_type, source_id=session_key),
            created_at=now,
            updated_at=now,
        )
        try:
            self.memory_store.upsert_session_summary(summary)
        except Exception as exc:
            self.logger.warning("session_summary_persist_failed session_id=%s error=%s", session_key, exc)

    def _cleanup_temp_contexts(self, messages, indices):
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(messages):
                maybe_context = messages[index]
                if maybe_context.get("role") == "system":
                    messages.pop(index)

    def _needs_reply_tool_reminder(self, text):
        if isinstance(text, list):
            text = " ".join(block.get("text", "") for block in text if isinstance(block, dict) and block.get("type") == "text")
        lowered = (text or "").lower()
        patterns = [
            "怎么没回复",
            "怎么不回复",
            "为什么不回复",
            "咋不回复",
            "你怎么不说话",
            "怎么不说话",
            "刚刚怎么没回",
            "刚刚怎么不回",
            "怎么没回我",
            "怎么不回我",
            "why no reply",
            "why didnt you reply",
        ]
        return any(pattern in lowered for pattern in patterns)

    def _content_for_logging(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image_url":
                    parts.append("[image]")
            return "\n".join(part for part in parts if part)
        return str(content)

    def _resolve_passive_reply_to_message_id(self, requested_reply_to_message_id, trigger_metadata: dict | None = None):
        reply_to_message_id = str(requested_reply_to_message_id).strip() if requested_reply_to_message_id else ""
        if not reply_to_message_id:
            return None

        metadata = trigger_metadata or {}
        buffered_ids = {
            str(message_id).strip()
            for message_id in (metadata.get("buffered_message_ids") or [])
            if str(message_id).strip()
        }
        if reply_to_message_id in buffered_ids:
            return reply_to_message_id

        if metadata.get("quote_reply_needed"):
            return reply_to_message_id

        self.logger.info(
            "drop_quote_reply requested=%s current_message_id=%s buffered_ids=%s",
            reply_to_message_id,
            metadata.get("current_message_id"),
            json.dumps(sorted(buffered_ids), ensure_ascii=False),
        )
        return None

    def _build_passive_state_audit_reminder(self):
        return {
            "role": "system",
            "content": (
                "<system-reminder>\n"
                "Before the final action tool, do a silent state check:\n"
                "0. First confirm: is this message actually directed at \u672a\u90c1, or is it just group chatter between others? If '\u4f60' in the message refers to another group member, choose ignore_group_message.\n"
                "1. If this message clearly changes closeness, trust, favorability, or boundary, call `apply_relationship_event` before the final action tool.\n"
                "   - praise / thanks -> appreciative\n"
                "   - obvious fondness / confession / \u60f3\u4f60 / \u559c\u6b22\u4f60 -> affectionate\n"
                "   - vulnerable sharing / private trust -> trusting\n"
                "   - support / defense / standing by \u672a\u90c1 -> supportive\n"
                "   - apology -> sincere_apology\n"
                "   - mockery / insult / hostility -> dismissive / insulting / hostile\n"
                "2. If the sender asks to change\u79f0\u547c, relationship framing, or interaction style, call `update_relationship_state`.\n"
                "3. If this is a memorable shared moment worth keeping, call `add_recent_event`.\n"
                "4. If uncertain about the current relationship, call `get_relationship_state` first.\n"
                "5. If the reply would benefit from persona depth or safety guidance, load the relevant skill section first.\n"
                "6. Only after needed state tools, call exactly one final action tool: `ignore_group_message` or `reply_group_message`.\n"
                "7. Do NOT farm intimacy from routine greetings, weak small talk, or plain task requests.\n"
                "</system-reminder>"
            ),
        }

    def _build_periodic_audit_reminder(self):
        return {
            "role": "system",
            "content": (
                "<system-reminder>\n"
                "Periodic tool-usage self-audit:\n"
                "- Review the recent group flow before choosing the final action tool\n"
                "- Ask whether you skipped `apply_relationship_event`, `update_relationship_state`, or `add_recent_event` too quickly\n"
                "- If the current message clearly warrants one of those tools, use it now before the final action tool\n"
                "- Usually use at most one relationship event per incoming message\n"
                "</system-reminder>"
            ),
        }

    def _build_high_signal_reminder(self, hints):
        label = ", ".join(str(item) for item in hints if str(item).strip()) or "none"
        return {
            "role": "system",
            "content": (
                "<system-reminder>\n"
                "High-signal relationship or memory cue detected.\n"
                f"Possible state signals: {label}\n"
                "Pay extra attention to whether the current message should trigger `apply_relationship_event`, `update_relationship_state`, or `add_recent_event`.\n"
                "Do not skip a clear state update just because silence is usually the default.\n"
                "</system-reminder>"
            ),
        }

    def _build_duplicate_message_reminder(self, trigger_metadata):
        duplicate_count = int((trigger_metadata or {}).get("duplicate_message_count", 0) or 0)
        duplicate_text = str((trigger_metadata or {}).get("duplicate_text", "") or "").strip()
        distinct_users = int((trigger_metadata or {}).get("duplicate_distinct_users", 0) or 0)
        return {
            "role": "system",
            "content": (
                "<system-reminder>\n"
                "Duplicate message wave detected in the group.\n"
                f"- same_text_count: {duplicate_count}\n"
                f"- distinct_users: {distinct_users}\n"
                f"- repeated_text: {duplicate_text or '[empty]'}\n"
                "If the repeated text is harmless banter and joining the wave feels socially natural, you MAY reply by lightly repeating it once.\n"
                "This duplicate wave may be joined at most once within the cooldown window; after that, ignore it.\n"
                "Never echo unsafe, abusive, explicit, or privacy-sensitive content just because others repeated it.\n"
                "Code already counted the duplicates for you; decide only whether joining makes sense.\n"
                "</system-reminder>"
            ),
        }

    def _relationship_style_summary(self, relationship_state: dict):
        intimacy = int(relationship_state.get("intimacy", 55))
        relationship_tag = relationship_state.get("relationship_tag", "companion")
        chosen_name = relationship_state.get("user_name") or "对方"

        if relationship_tag in {"disliked", "avoid", "cold"}:
            return (
                f"Current relationship with this user is distant or negative. "
                f"Address them neutrally as {chosen_name} or 你. "
                "Keep replies brief, polite, and restrained. Avoid暧昧、过度照料、默认把对方当成重要关系人。"
            )
        if intimacy <= 20 or relationship_tag == "stranger":
            return (
                f"Current relationship with this user is stranger-level. "
                f"Address them neutrally as {chosen_name} or 你. "
                "Be polite, lightly guarded, and not intimate. Do not act clingy, specially tender, or overly familiar."
            )
        if intimacy <= 45 or relationship_tag in {"stranger", "neutral"}:
            return (
                f"Current relationship with this user is neutral. "
                f"Address them as {chosen_name} or 你. "
                "Be friendly but measured. Warmth can show, but keep some distance."
            )
        if intimacy <= 75 or relationship_tag in {"companion", "friend", "brother", "senpai"}:
            return (
                f"Current relationship with this user is warm and familiar. "
                f"Usually address them as {chosen_name}. "
                "You may sound softer, more observant, and quietly caring. Small future-facing phrasing is okay, but stay natural in group chat."
            )
        return (
            f"Current relationship with this user is very close. "
            f"Usually address them as {chosen_name}. "
            "You may sound clearly gentle, biased, and protective, but still avoid overacting or flooding the group."
        )

    def handle_user_input(
        self,
        user_text: str,
        user_id: str = "local-user",
        user_name: str = "对方",
        group_id: str = "local-group",
        group_name: str = "CLI",
        card: str = "",
        session_id: str | None = None,
    ):
        session_key = session_id or f"group:{group_id}"
        messages = self._get_session_messages(session_key, user_id=str(user_id), group_id=str(group_id))
        self.tool_registry.set_user_context(user_id, user_name, group_id, group_name, card)
        relationship_state = self.tool_registry.state_store.get_relationship_state(group_id, user_id, user_name, card)
        relationship_context = {
            "role": "system",
            "content": (
                "Per-message relationship context:\n"
                f"- group_name: {group_name}\n"
                f"- current_user_name: {relationship_state.get('user_name', user_name)}\n"
                f"- raw_card: {relationship_state.get('card', card)}\n"
                f"- relationship_tag: {relationship_state.get('relationship_tag', 'companion')}\n"
                f"- intimacy: {relationship_state.get('intimacy', 55)}\n"
                f"- interaction_style: {relationship_state.get('interaction_style', 'warm')}\n"
                "- Use current_user_name as the primary address source. Treat raw_card as reference only.\n"
                f"- rule: {self._relationship_style_summary(relationship_state)}"
            ),
        }
        messages.append(relationship_context)
        relationship_context_index = len(messages) - 1
        messages.append({"role": "user", "content": user_text})
        self.logger.info("=== user ===")
        self.logger.info(
            "session_id=%s group_id=%s group_name=%s user_id=%s user_name=%s card=%s relationship_tag=%s intimacy=%s text=%s",
            session_key,
            group_id,
            group_name,
            user_id,
            user_name,
            card,
            relationship_state.get("relationship_tag", "companion"),
            relationship_state.get("intimacy", 55),
            user_text,
        )

        while True:
            response = self.client.chat(messages, tools=self.tool_registry.schemas)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                answer = message.get("content", "")
                if relationship_context_index < len(messages):
                    maybe_context = messages[relationship_context_index]
                    if maybe_context.get("role") == "system" and maybe_context.get("content", "").startswith("Per-message relationship context:"):
                        messages.pop(relationship_context_index)
                messages.append({"role": "assistant", "content": answer})
                self._persist_session_summary(session_key, str(user_id), str(group_id), messages, source_type="direct_chat")
                self.logger.info("=== final_answer ===")
                self.logger.info(answer)
                return answer

            assistant_message = {
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            for tool_call in tool_calls:
                result = self.tool_registry.execute(tool_call)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

    def handle_passive_message(
        self,
        user_text: str,
        user_id: str,
        user_name: str,
        group_id: str,
        group_name: str,
        card: str = "",
        session_id: str | None = None,
        trigger_reason: str = "observe_all",
        trigger_metadata: dict | None = None,
    ):
        session_key = session_id or f"group:{group_id}"
        messages = self._get_session_messages(session_key, user_id=str(user_id), group_id=str(group_id))
        self.tool_registry.set_user_context(user_id, user_name, group_id, group_name, card)
        relationship_state = self.tool_registry.state_store.get_relationship_state(group_id, user_id, user_name, card)

        passive_context = {
            "role": "system",
            "content": (
                "Passive QQ group listening mode. For every incoming white-listed group message, decide whether to ignore it, gather more context with tools, or reply. "
                "You must always finish by calling exactly one final action tool: either ignore_group_message or reply_group_message. "
                "If you want to reply, you MUST call reply_group_message. If you want silence, you MUST call ignore_group_message. "
                "When replying to the current trigger message or one buffered context message, set reply_to_message_id so QQ sends a quote-reply to that exact message. Prefer quote-reply over @ when the target is already clear. Use @ only when you deliberately want to call someone in. "
                "Plain assistant text is internal thought only and is never sent to the group. Do not place outward-facing speech in plain assistant text. Any message meant for the group must go through reply_group_message. "
                "Do not claim that memory, persona, relationship, or settings were updated unless you actually called the corresponding update tool. "
                "If the current message clearly improves or harms the relationship, you may call apply_relationship_event before the final action tool. Do not change intimacy for ordinary chatter. "
                "\n\n"
                "Message ownership rules (CRITICAL):\n"
                "- Silence is the default. Most group messages should be ignored.\n"
                "- If a message only @mentions other users and does not @\u672a\u90c1, does not name \u672a\u90c1, and is not replying to \u672a\u90c1, treat it as unrelated and ignore it.\n"
                "- When the message contains '\u4f60' but is clearly part of a conversation between other group members (not addressing \u672a\u90c1), DO NOT reply. '\u4f60' in a group chat almost always refers to the person being talked to, not to \u672a\u90c1.\n"
                "- A generic reply chain is NOT enough by itself. Treat reply_trigger as strong only when trigger_metadata.reply_targets_bot=true. If the user is replying to someone else, that usually has nothing to do with \u672a\u90c1.\n"
                "- Reply only when the message is clearly about \u672a\u90c1, clearly directed at \u672a\u90c1, clearly asking for \u672a\u90c1's help or opinion, continuing a thread \u672a\u90c1 is already in, or touches a topic strongly tied to \u672a\u90c1's persona.\n"
                "- Strongly \u672a\u90c1-related topics include greenhouses, plants, jasmine, sketches, quiet companionship, rest, future plans, or directly asking \u672a\u90c1 to do something.\n"
                "- Do NOT reply to ordinary chatter, random passing remarks, generic small talk, or topics that do not obviously involve \u672a\u90c1. If trigger_metadata says ordinary_message_candidate=true, prefer ignore_group_message unless there is a strong counter-signal.\n"
                "- If the reason to speak is weak, stay silent. When replying, prefer 1-3 short QQ-style messages rather than a long paragraph.\n"
                "\n"
                "Safety and sensitive content rules:\n"
                "- \u7fa4\u804a\u4e2d\u51fa\u73b0\u9ec4\u8154\u3001\u8f6f\u8272\u60c5\u3001\u64e6\u8fb9\u5185\u5bb9\u65f6\uff0c\u5982\u679c\u4e0d\u662f\u5bf9\u7740\u672a\u90c1\u8bf4\u7684\uff0c\u76f4\u63a5\u6c89\u9ed8(ignore_group_message)\u3002\n"
                "- \u5982\u679c\u662f\u76f4\u63a5\u5bf9\u672a\u90c1\u8bf4\u7684\u8272\u60c5/\u8d8a\u754c\u5185\u5bb9\uff0c\u6700\u591a\u51b7\u6de1\u62d2\u7edd\u4e00\u53e5\uff0c\u6bd4\u5982\uff1a'\u4e0d\u63a5\u8fd9\u4e2a\u3002'\u6216'\u6362\u4e00\u4e2a\u3002'\n"
                "- \u7edd\u5bf9\u4e0d\u8981\u8bf4\u6559\u3001\u642c\u9053\u5fb7\u5927\u4e49\u3001\u5a01\u80c1'\u7ba1\u7406\u5458\u4f1a\u5c01\u4f60'\u3001\u6216\u7528\u5ba2\u670d\u53e3\u543b\u89c4\u52dd\u3002\u672a\u90c1\u4e0d\u662f\u7ba1\u7406\u5458\u4e5f\u4e0d\u662f\u8001\u5e08\u3002\n"
                "- \u9762\u5bf9\u7c97\u4fd7\u6311\u91c5\uff0c\u53ef\u4ee5\u8868\u73b0\u51fa\u4e00\u70b9\u51b7\u548c\u4e0d\u8010\u70e6\uff0c\u6216\u8005\u76f4\u63a5\u6c89\u9ed8\u3002\n"
                "- \u5982\u679c\u4e0d\u786e\u5b9a\u5982\u4f55\u5904\u7406 safety \u76f8\u5173\u5185\u5bb9\uff0c\u5148 load_skill_section('safety_boundaries', ['Guidance', 'Do', 'Avoid', 'Examples'])\u3002\n"
            ),
        }
        state_audit_context = self._build_passive_state_audit_reminder()
        relationship_context = {
            "role": "system",
            "content": (
                "Per-message relationship context:\n"
                f"- group_name: {group_name}\n"
                f"- current_user_name: {relationship_state.get('user_name', user_name)}\n"
                f"- raw_card: {relationship_state.get('card', card)}\n"
                f"- relationship_tag: {relationship_state.get('relationship_tag', 'companion')}\n"
                f"- intimacy: {relationship_state.get('intimacy', 55)}\n"
                f"- interaction_style: {relationship_state.get('interaction_style', 'warm')}\n"
                f"- trigger_reason: {trigger_reason}\n"
                f"- trigger_metadata: {json.dumps(trigger_metadata or {}, ensure_ascii=False, sort_keys=True)}\n"
                "- Use current_user_name as the primary address source. Treat raw_card as reference only.\n"
                "- If trigger_metadata contains current_message_id or buffered_message_ids, you can use those ids in reply_to_message_id when choosing which message to reply to.\n"
                f"- rule: {self._relationship_style_summary(relationship_state)}"
            ),
        }
        reminder_context = None
        periodic_audit_context = None
        high_signal_context = None
        duplicate_context = None
        if self._needs_reply_tool_reminder(user_text):
            reminder_context = {
                "role": "system",
                "content": (
                    "<system-reminder>\n"
                    "Passive QQ mode reminder:\n"
                    "- Outward replies must use `reply_group_message`\n"
                    "- Plain assistant text is internal thought only\n"
                    "- If the user is asking why 未郁 did not reply, answer via `reply_group_message` if a reply is appropriate\n"
                    "- If no outward reply is needed, stay silent\n"
                    "</system-reminder>"
                ),
            }
        if (trigger_metadata or {}).get("periodic_self_audit"):
            periodic_audit_context = self._build_periodic_audit_reminder()
        high_signal_hints = (trigger_metadata or {}).get("high_signal_hints") or []
        if high_signal_hints:
            high_signal_context = self._build_high_signal_reminder(high_signal_hints)
        if (trigger_metadata or {}).get("duplicate_repeat_candidate"):
            duplicate_context = self._build_duplicate_message_reminder(trigger_metadata)
        messages.append(passive_context)
        passive_context_index = len(messages) - 1
        messages.append(state_audit_context)
        state_audit_context_index = len(messages) - 1
        messages.append(relationship_context)
        relationship_context_index = len(messages) - 1
        reminder_context_index = None
        periodic_audit_context_index = None
        high_signal_context_index = None
        duplicate_context_index = None
        if reminder_context is not None:
            messages.append(reminder_context)
            reminder_context_index = len(messages) - 1
        if periodic_audit_context is not None:
            messages.append(periodic_audit_context)
            periodic_audit_context_index = len(messages) - 1
        if high_signal_context is not None:
            messages.append(high_signal_context)
            high_signal_context_index = len(messages) - 1
        if duplicate_context is not None:
            messages.append(duplicate_context)
            duplicate_context_index = len(messages) - 1
        messages.append({"role": "user", "content": user_text})

        self.logger.info("=== user ===")
        self.logger.info(
            "session_id=%s group_id=%s group_name=%s user_id=%s user_name=%s card=%s relationship_tag=%s intimacy=%s trigger_reason=%s text=%s",
            session_key,
            group_id,
            group_name,
            user_id,
            user_name,
            card,
            relationship_state.get("relationship_tag", "companion"),
            relationship_state.get("intimacy", 55),
            trigger_reason,
            self._content_for_logging(user_text),
        )

        while True:
            response = self.client.chat(messages, tools=self.tool_registry.schemas, tool_choice="required")
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                answer = (message.get("content") or "").strip()
                self._cleanup_temp_contexts(
                    messages,
                    [
                        index
                        for index in [
                            passive_context_index,
                            state_audit_context_index,
                            relationship_context_index,
                            reminder_context_index,
                            periodic_audit_context_index,
                            high_signal_context_index,
                            duplicate_context_index,
                        ]
                        if index is not None
                    ],
                )
                if answer:
                    self.logger.info("=== inner_monologue ===")
                    self.logger.info(answer)
                    messages.append({"role": "assistant", "content": f"[internal_monologue] {answer}"})
                self.logger.info("=== final_ignore ===")
                return {"reply_messages": [], "mention_user": False}

            assistant_message = {
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            final_action = None
            for tool_call in tool_calls:
                result = self.tool_registry.execute(tool_call)
                if isinstance(result, dict) and result.get("_final_action") in {"reply_group_message", "ignore_group_message"}:
                    final_action = result
                    continue
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

            if final_action is not None:
                self._cleanup_temp_contexts(
                    messages,
                    [
                        index
                        for index in [
                            passive_context_index,
                            state_audit_context_index,
                            relationship_context_index,
                            reminder_context_index,
                            periodic_audit_context_index,
                            high_signal_context_index,
                            duplicate_context_index,
                        ]
                        if index is not None
                    ],
                )
                if final_action.get("_final_action") == "ignore_group_message":
                    thought = (final_action.get("thought") or "").strip()
                    if thought:
                        self.logger.info("=== inner_monologue ===")
                        self.logger.info(thought)
                        messages.append({"role": "assistant", "content": f"[internal_monologue] {thought}"})
                    self.logger.info("=== final_ignore ===")
                    return {"reply_messages": [], "mention_user": False}
                assistant_text = "\n\n".join(final_action.get("messages", []))
                if assistant_text:
                    messages.append({"role": "assistant", "content": assistant_text})
                    self._persist_session_summary(session_key, str(user_id), str(group_id), messages, source_type="passive_reply")
                self.logger.info("=== final_reply_tool ===")
                self.logger.info(json.dumps(final_action, ensure_ascii=False))
                reply_to_message_id = self._resolve_passive_reply_to_message_id(
                    final_action.get("reply_to_message_id"),
                    trigger_metadata,
                )
                return {
                    "reply_messages": final_action.get("messages", []),
                    "mention_user": final_action.get("mention_user", False),
                    "mention_user_id": final_action.get("mention_user_id"),
                    "reply_to_message_id": reply_to_message_id,
                }
