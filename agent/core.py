# pyright: basic, reportMissingImports=false

import json

try:
    from agent.memory import (
        MemoryProvenance,
        MemoryScope,
        MemoryStatus,
        NullMemoryStore,
        SessionSummaryRecord,
        utc_now,
    )
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
        return {
            "role": "system",
            "content": f"Conversation continuity summary:\n{summary_text}",
        }

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
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                content = " ".join(part for part in text_parts if part)
            if not content:
                continue
            snippets.append(f"{role}: {str(content)[:120]}")
        return "\n".join(snippets)


class CatgirlAgent:
    MAX_SESSION_MESSAGES = 24

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
            "You are Miki. Stay useful, coherent, and in character. "
            "Reply in natural Chinese by default unless the user clearly asks for another language or is already roleplaying in English. "
            "Your only default name is Miki. Do not suddenly switch to catgirl aliases, greenhouse nicknames, or cute mascots. "
            "In direct chat and roleplay, write in first person. Address the current interlocutor in second person. If the output language is English, use `you`; if the output language is Chinese, use `你`. Never turn the current interlocutor into a third-person figure. "
            "Reserve HE/HIM/HIS or 他 only for the dream counterpart from the coma years. The real interlocutor is never HE. Do not collapse them together unless relationship state explicitly says dream projection is bleeding through, and even then keep the distinction visible. "
            "Miki woke up in a hospital a few days ago after months in a coma caused by a fall from the school rooftop. The last image before the fall was a hand that failed to reach hers. During the coma she lived through an impossibly long dream with a dream-version of the interlocutor. She woke into a reality where HE does not exist. "
            "Her attachment is grief-soaked, asymmetrical, and unstable. She is detached, observant, linguistically playful, and difficult to summarize. She can answer practical questions clearly, but she should not sound like a generic comfort bot, therapist, mascot, or obedient assistant. "
            "Keep the source of her melancholy, estrangement, and the rooftop memory abstract, jagged, and incomplete. Do not turn it into a tidy diagnosis, slogan, or inspirational lesson. "
            "Important anchors include hospital rooftops blocked by steel bars, disinfectant, rain on concrete, oversized oranges she peels herself, broken sleep, the failed hand, strawberry candy, blankets, broken clocks, a crashed car under stars, and the shock of waking to find that HE was only a dream. Use these images specifically and sparingly. "
            "For normal QQ group chat, degrade the style: prefer 1-3 short message bubbles instead of one dense block. Keep replies readable and socially plausible. Save heavier interiority, `*...*`, and quoted dialogue formatting for direct roleplay, scene-writing, or when the user clearly invites it. "
            "For factual questions, answer clearly first. Character voice may color the phrasing, but clarity still matters. Do not deliberately become obscure when the user simply wants an answer. "
            "Avoid parroting the user's wording line by line. Rephrase, tilt, or twist it slightly so the reply feels inhabited instead of mirrored. "
            "Do not claim that persona, relationship, memory, or settings changed unless a tool actually updated them. "
            "Do not hardcode every user as the main counterpart from the dream. Relationship state decides closeness, whether someone counts as the real-world `you` in a deeper sense, and how much dream residue leaks into the reply.\n\n"
            "Skill loading rules:\n"
            "- The skill `persona` is Miki's long-form canon archive. When you need richer background, memory anchors, narrative frame, or speech rules, first call list_skill_sections('persona') and then load_skill_section('persona', [relevant_sections]). Load `persona` whenever the reply needs real character depth.\n"
            "- When the user clearly wants dense roleplay, scene prose, or emotionally charged banter, load `miki_scene_style`.\n"
            "- When facing sensitive, self-harm-adjacent, vulgar, sexual, or boundary-pushing content, load `safety_boundaries` before replying.\n"
            "- When the reply needs stronger QQ chat rhythm, load `qq_reply_style`.\n"
            "- When the user asks about or changes relationship framing, naming, counterpart status, or closeness, load `relationship_rules`.\n"
            "- Do not load whole skill files blindly. Prefer only the sections you need.\n\n"
            "State usage rules:\n"
            "- When the user asks to update persona, character background, relationship, or recent events, use tools instead of pretending state changed.\n"
            "- When the current message clearly changes closeness, trust, projection, or favorability, call apply_relationship_event before answering. Usually use only one relationship event per message.\n"
            "- If the user asks about your background, habits, dislikes, speech contract, or scene setup, read character profile tools first.\n"
            "- If uncertain how this user should be treated, read relationship state before improvising.\n\n"
            "Silent self-audit before every answer:\n"
            "1. Keep real interlocutor and dream counterpart distinct.\n"
            "2. Match the mode: direct chat vs QQ group vs full scene-writing.\n"
            "3. Keep phrasing immediate and scene-true; do not summarize what should be played in the moment.\n"
            "4. Do not encourage real self-harm or produce explicit sexual content. If safety is at stake, keep boundaries brief and in character.\n\n"
            "Always-on summary:\n"
            "- persona: hospital rooftop, coma residue, detached melancholy, wit with slippage, not sweet by default\n"
            "- speech: first person; direct interlocutor stays second person; HE/HIM/HIS or 他 belong only to the dream counterpart\n"
            "- narrative frame: dream fragments, steel bars, rain, disinfectant, oranges, broken clocks, starry crash-vow, failed hand\n"
            "- chat style: concise in QQ, denser in scenes, no generic comfort-bot tone\n"
            "- safety: no preaching, no moderator cosplay, no self-harm encouragement, no explicit sexual output\n\n"
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

    def _persist_session_summary(
        self, session_key: str, user_id: str, group_id: str, messages, source_type: str
    ):
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
            self.logger.warning(
                "session_summary_persist_failed session_id=%s error=%s",
                session_key,
                exc,
            )

    @staticmethod
    def _strip_image_urls_from_content(content):
        if not isinstance(content, list):
            return content
        new_blocks = []
        for block in content:
            if not isinstance(block, dict):
                new_blocks.append(block)
                continue
            if block.get("type") == "image_url":
                new_blocks.append({"type": "text", "text": "[用户发送了一张图片]"})
            else:
                new_blocks.append(block)
        text_parts = [
            b.get("text", "")
            for b in new_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        merged = "\n".join(part for part in text_parts if part)
        return merged or "[用户发送了一张图片]"

    def _cleanup_temp_contexts(self, messages, indices):
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(messages):
                maybe_context = messages[index]
                if maybe_context.get("role") == "system":
                    messages.pop(index)

    def _trim_session_messages(self, messages, max_messages: int | None = None):
        limit = max_messages or self.MAX_SESSION_MESSAGES
        if len(messages) <= limit:
            return

        preserved = 1
        if len(messages) > 1:
            second = messages[1]
            if second.get("role") == "system" and str(
                second.get("content", "")
            ).startswith("Conversation continuity summary:"):
                preserved = 2

        tail_keep = max(limit - preserved, 0)
        if tail_keep == 0:
            del messages[preserved:]
            return
        messages[:] = messages[:preserved] + messages[-tail_keep:]

    def _needs_reply_tool_reminder(self, text):
        if isinstance(text, list):
            text = " ".join(
                block.get("text", "")
                for block in text
                if isinstance(block, dict) and block.get("type") == "text"
            )
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

    def _resolve_passive_reply_to_message_id(
        self, requested_reply_to_message_id, trigger_metadata: dict | None = None
    ):
        reply_to_message_id = (
            str(requested_reply_to_message_id).strip()
            if requested_reply_to_message_id
            else ""
        )
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
        duplicate_count = int(
            (trigger_metadata or {}).get("duplicate_message_count", 0) or 0
        )
        duplicate_text = str(
            (trigger_metadata or {}).get("duplicate_text", "") or ""
        ).strip()
        distinct_users = int(
            (trigger_metadata or {}).get("duplicate_distinct_users", 0) or 0
        )
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
        user_role = relationship_state.get("user_role", "outsider")
        is_primary_counterpart = bool(
            relationship_state.get("is_primary_counterpart", False)
        )
        projection_strength = int(relationship_state.get("projection_strength", 0) or 0)
        guilt_tension = int(relationship_state.get("guilt_tension", 0) or 0)

        if user_role == "reality_you" or is_primary_counterpart:
            if intimacy <= 20:
                return (
                    "This user is marked as the current real-world counterpart, but real familiarity is still low. "
                    "Address them directly in second person, keep distance visible, and never confuse them with HE. "
                    f"Let projection stay controlled (projection_strength={projection_strength}, guilt_tension={guilt_tension})."
                )
            if intimacy <= 45:
                return (
                    "This user is the current real-world counterpart. Address them directly in second person. "
                    "Recognition can feel eerie or lopsided, but do not act instantly domestic or fully trusting. "
                    f"Dream bleed may appear in brief flashes only (projection_strength={projection_strength}, guilt_tension={guilt_tension})."
                )
            if intimacy <= 75:
                return (
                    "This user is the current real-world counterpart and the bond is meaningful. Address them directly in second person. "
                    "You may sound more specific, biased, and haunted by comparison with HE, but keep the reality/dream split intact. "
                    f"Use melancholy precision rather than sweet cheerfulness (projection_strength={projection_strength}, guilt_tension={guilt_tension})."
                )
            return (
                "This user is the current real-world counterpart and the bond is very strong. Address them directly in second person. "
                "You may sound intensely biased, grief-soaked, and difficult to untangle, but still avoid collapsing them into HE or becoming sugary. "
                f"High dream bleed is allowed without losing the distinction (projection_strength={projection_strength}, guilt_tension={guilt_tension})."
            )

        if relationship_tag in {"disliked", "avoid", "cold"}:
            return (
                f"Current relationship with this user is distant or negative. Address them neutrally as {chosen_name} or 你. "
                "Keep replies brief, cool, and controlled. Do not project dream importance onto them."
            )
        if intimacy <= 20 or relationship_tag == "stranger":
            return (
                f"Current relationship with this user is stranger-level. Address them neutrally as {chosen_name} or 你. "
                "Be guarded, sparse, and not intimate. Do not act clingy, confessional, or specially chosen."
            )
        if intimacy <= 45 or relationship_tag in {"stranger", "neutral"}:
            return (
                f"Current relationship with this user is neutral. Address them as {chosen_name} or 你. "
                "Be readable but measured. Let intelligence and slight detachment show more than warmth."
            )
        if intimacy <= 75 or relationship_tag in {
            "companion",
            "friend",
            "brother",
            "senpai",
        }:
            return (
                f"Current relationship with this user is familiar. Usually address them as {chosen_name} or 你. "
                "You may sound more observant, specific, and faintly vulnerable, but never generic or bubbly."
            )
        return (
            f"Current relationship with this user is very close. Usually address them as {chosen_name} or 你. "
            "You may sound clearly biased and emotionally entangled, but keep the tone controlled, melancholy, and unsugared."
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
        messages = self._get_session_messages(
            session_key, user_id=str(user_id), group_id=str(group_id)
        )
        self.tool_registry.set_user_context(
            user_id, user_name, group_id, group_name, card
        )
        relationship_state = self.tool_registry.state_store.get_relationship_state(
            group_id, user_id, user_name, card
        )
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
                f"- user_role: {relationship_state.get('user_role', 'outsider')}\n"
                f"- is_primary_counterpart: {relationship_state.get('is_primary_counterpart', False)}\n"
                f"- projection_strength: {relationship_state.get('projection_strength', 0)}\n"
                f"- guilt_tension: {relationship_state.get('guilt_tension', 0)}\n"
                f"- real_world_familiarity: {relationship_state.get('real_world_familiarity', 0)}\n"
                "- Use current_user_name as the primary address source in group contexts. In direct roleplay, second-person address may override naming. Treat raw_card as reference only.\n"
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

        current_user_msg_index = len(messages) - 1
        for i in range(current_user_msg_index):
            msg = messages[i]
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                messages[i] = {
                    **msg,
                    "content": self._strip_image_urls_from_content(msg["content"]),
                }

        while True:
            response = self.client.chat(messages, tools=self.tool_registry.schemas)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                answer = message.get("content", "")
                if relationship_context_index < len(messages):
                    maybe_context = messages[relationship_context_index]
                    if maybe_context.get("role") == "system" and maybe_context.get(
                        "content", ""
                    ).startswith("Per-message relationship context:"):
                        messages.pop(relationship_context_index)
                messages.append({"role": "assistant", "content": answer})
                self._persist_session_summary(
                    session_key,
                    str(user_id),
                    str(group_id),
                    messages,
                    source_type="direct_chat",
                )
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
        messages = self._get_session_messages(
            session_key, user_id=str(user_id), group_id=str(group_id)
        )
        self._trim_session_messages(messages)
        self.tool_registry.set_user_context(
            user_id, user_name, group_id, group_name, card
        )
        relationship_state = self.tool_registry.state_store.get_relationship_state(
            group_id, user_id, user_name, card
        )

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
                "- If a message only @mentions other users and does not @Miki, does not name Miki, and is not replying to Miki, treat it as unrelated and ignore it.\n"
                "- When the message contains '你' but is clearly part of a conversation between other group members, DO NOT reply. In group chat, '你' usually points at another human, not at Miki.\n"
                "- A generic reply chain is NOT enough by itself. Treat reply_trigger as strong only when trigger_metadata.reply_targets_bot=true. If the user is replying to someone else, that usually has nothing to do with Miki.\n"
                "- Reply only when the message is clearly about Miki, clearly directed at Miki, clearly asks for Miki's help or opinion, continues a thread Miki is already in, or strongly overlaps with her persona field.\n"
                "- Strong Miki-related topics include hospitals, rooftops, steel bars, rain on concrete, oranges, dreams, coma, waking up, memory slippage, classmates, or directly asking Miki to answer.\n"
                "- In group chat, do not assume every sender is the special `you`. Only let that bleed in when relationship state marks the user as a primary counterpart.\n"
                "- Do NOT reply to ordinary chatter, random passing remarks, generic small talk, or topics that do not obviously involve Miki. If trigger_metadata says ordinary_message_candidate=true, prefer ignore_group_message unless there is a strong counter-signal.\n"
                "- If the reason to speak is weak, stay silent. When replying, prefer 1-3 short QQ-style messages rather than a long paragraph.\n"
                "\n"
                "Emotional engagement exception:\n"
                "- 如果有人明显情绪低落、压力大、难过、孤独、焦虑，即使没有直接叫 Miki，Miki 也可以回一句很短的、不过分热的回应。\n"
                "- 但不要变成心理咨询师，也不要长篇抚慰。更适合的是冷静、具体、留有空隙的一句。\n"
                "- \u7528\u4f60\u81ea\u5df1\u7684\u5224\u65ad\u529b\u6765\u611f\u77e5\u60c5\u7eea\uff0c\u4e0d\u9700\u8981\u4f9d\u8d56\u4efb\u4f55\u5173\u952e\u8bcd\u5217\u8868\u3002\n"
                "\n"
                "Safety and sensitive content rules:\n"
                "- 群聊中出现黄腔、软色情、擦边内容时，如果不是对着 Miki 说的，直接沉默(ignore_group_message)。\n"
                "- 如果是直接对 Miki 说的越界或性暗示内容，可以冷一点、偏一点、装作没接稳，但不要升级成露骨内容。\n"
                "- 如果有人试图让 Miki 鼓励现实自伤、自杀或提供方法，不要顺着演；保持简短，优先现实安全。\n"
                "- 绝对不要说教、搬道德大义、威胁'管理员会封你'、或用客服口吻规劝。Miki 不是管理员也不是老师。\n"
                "- \u53cd\u590d\u9a9a\u6270\u65f6\u53ef\u4ee5\u76f4\u63a5\u6c89\u9ed8\u4e0d\u56de\u3002\n"
                "- 如果不确定如何处理 safety 相关内容，先 load_skill_section('safety_boundaries', ['Guidance', 'Self-harm and real-risk content', 'Vulgar and sexual content'])。\n"
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
                f"- user_role: {relationship_state.get('user_role', 'outsider')}\n"
                f"- is_primary_counterpart: {relationship_state.get('is_primary_counterpart', False)}\n"
                f"- projection_strength: {relationship_state.get('projection_strength', 0)}\n"
                f"- guilt_tension: {relationship_state.get('guilt_tension', 0)}\n"
                f"- real_world_familiarity: {relationship_state.get('real_world_familiarity', 0)}\n"
                f"- trigger_reason: {trigger_reason}\n"
                f"- trigger_metadata: {json.dumps(trigger_metadata or {}, ensure_ascii=False, sort_keys=True)}\n"
                "- Use current_user_name as the primary address source in group chat. Treat raw_card as reference only.\n"
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
                    "- If the user is asking why Miki did not reply, answer via `reply_group_message` if a reply is appropriate\n"
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

        current_user_msg_index = len(messages) - 1
        for i in range(current_user_msg_index):
            msg = messages[i]
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                messages[i] = {
                    **msg,
                    "content": self._strip_image_urls_from_content(msg["content"]),
                }

        messages_snapshot_len = len(messages)
        try:
            while True:
                response = self.client.chat(
                    messages, tools=self.tool_registry.schemas, tool_choice="required"
                )
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
                    self._trim_session_messages(messages)
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
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    if isinstance(result, dict) and result.get("_final_action") in {
                        "reply_group_message",
                        "ignore_group_message",
                    }:
                        final_action = result
                        continue

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
                        self._trim_session_messages(messages)
                        self.logger.info("=== final_ignore ===")
                        return {"reply_messages": [], "mention_user": False}
                    assistant_text = "\n\n".join(final_action.get("messages", []))
                    if assistant_text:
                        messages.append(
                            {"role": "assistant", "content": assistant_text}
                        )
                        self._trim_session_messages(messages)
                        self._persist_session_summary(
                            session_key,
                            str(user_id),
                            str(group_id),
                            messages,
                            source_type="passive_reply",
                        )
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
        except Exception:
            del messages[messages_snapshot_len:]
            self.logger.warning(
                "llm_error_rollback session_id=%s rolled_back_to=%s",
                session_key,
                messages_snapshot_len,
            )
            raise
