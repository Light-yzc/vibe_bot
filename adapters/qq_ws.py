import html
import json
import re
import time
import uuid

import requests
from websocket import WebSocketConnectionClosedException, create_connection


class NapCatWebSocketAdapter:
    def __init__(self, ws_url, token, logger, state_store, router, agent, multi_msg_delay: float = 0.6):
        self.ws_url = ws_url
        self.token = token
        self.logger = logger
        self.state_store = state_store
        self.router = router
        self.agent = agent
        self.multi_msg_delay = multi_msg_delay
        self.ws = None
        self.api_ws = None
        self.bot_user_id = ""
        self.pending_context = {}

    def _headers(self):
        return [f"Authorization: Bearer {self.token}"]

    def connect(self):
        self.logger.info("=== qq_connect ===")
        self.logger.info("connecting_to=%s", self.ws_url)
        self.ws = create_connection(self.ws_url, header=self._headers(), timeout=60)
        self.api_ws = create_connection(self.ws_url, header=self._headers(), timeout=60)
        self.logger.info("qq_connected=true")
        self.bot_user_id = self.fetch_login_info().get("user_id", "")
        self.logger.info("self_id=%s", self.bot_user_id)

    def call_api(self, action: str, params: dict | None = None, timeout: float = 10.0):
        if self.api_ws is None:
            raise RuntimeError("websocket is not connected")
        api_ws = self.api_ws
        echo = f"call-{uuid.uuid4().hex}"
        payload = {"action": action, "params": params or {}, "echo": echo}
        api_ws.settimeout(timeout)
        api_ws.send(json.dumps(payload, ensure_ascii=False))
        while True:
            raw = api_ws.recv()
            result = json.loads(raw)
            if result.get("echo") == echo:
                return result.get("data", {})

    def fetch_login_info(self):
        return self.call_api("get_login_info")

    def fetch_group_info(self, group_id: str):
        return self.call_api("get_group_info_ex", {"group_id": int(group_id)})

    def fetch_group_member_info(self, group_id: str, user_id: str):
        return self.call_api("get_group_member_info", {"group_id": int(group_id), "user_id": int(user_id), "no_cache": False})

    def fetch_message(self, message_id: str):
        return self.call_api("get_msg", {"message_id": int(message_id)})

    def fetch_image(self, file_name: str):
        return self.call_api("get_image", {"file": file_name})

    def send_group_message(self, group_id: str, message: str):
        self.logger.info("=== qq_send ===")
        self.logger.info("group_id=%s message=%s", group_id, message)
        return self.call_api("send_group_msg", {"group_id": int(group_id), "message": message})

    def _split_reply_messages(self, text: str):
        normalized = (text or "").replace("\r\n", "\n").strip()
        if not normalized:
            return []

        paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
        chunks = []

        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
            if not lines:
                continue

            if len(lines) <= 2:
                chunks.append("\n".join(lines))
                continue

            current = []
            for line in lines:
                current.append(line)
                if len(current) >= 2:
                    chunks.append("\n".join(current))
                    current = []
            if current:
                chunks.append("\n".join(current))

        return chunks or [normalized]

    def _content_to_text(self, content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        parts.append(text)
                elif block.get("type") == "image_url":
                    parts.append("[image]")
            return "\n".join(parts)
        return str(content)

    def _append_pending_context(self, group_id: str, item):
        key = str(group_id)
        if not item:
            return
        summary = str(item.get("summary", "")).strip() if isinstance(item, dict) else str(item).strip()
        if not summary:
            return
        bucket = self.pending_context.setdefault(key, [])
        if isinstance(item, dict):
            normalized = {
                "message_id": str(item.get("message_id", "")).strip() or None,
                "user_name": str(item.get("user_name", "")).strip() or "某人",
                "summary": summary,
            }
        else:
            normalized = {"message_id": None, "user_name": "某人", "summary": summary}
        bucket.append(normalized)
        self.pending_context[key] = bucket[-6:]
        self.logger.info("pending_context_push group_id=%s size=%s", key, len(self.pending_context[key]))

    def _pop_pending_context(self, group_id: str):
        return self.pending_context.pop(str(group_id), [])

    def _merge_pending_context(self, pending_contexts, current_content, current_message_id: str | None = None):
        if not pending_contexts:
            return current_content

        context_text = "在冷却或忙碌期间收到的补充上下文：\n" + "\n".join(
            f"- [message_id={item.get('message_id') or 'unknown'}] {item.get('user_name', '某人')}: {item.get('summary', '')}"
            for item in pending_contexts
            if item.get("summary", "").strip()
        )
        if current_message_id:
            context_text += f"\n\n当前触发消息的 message_id={current_message_id}"
        if isinstance(current_content, list):
            merged = [{"type": "text", "text": context_text}]
            merged.extend(current_content)
            return merged
        if current_content:
            return f"{context_text}\n\n当前触发消息：\n{current_content}"
        return context_text

    def send_group_reply(
        self,
        group_id: str,
        text_or_messages,
        user_id: str | None = None,
        mention_user: bool = False,
        mention_user_id: str | None = None,
        reply_to_message_id: str | None = None,
    ):
        if isinstance(text_or_messages, list):
            parts = [str(item).strip() for item in text_or_messages if str(item).strip()]
        else:
            parts = self._split_reply_messages(str(text_or_messages))
        mention_target = None
        if mention_user_id:
            mention_target = str(mention_user_id)
        elif mention_user and user_id:
            mention_target = str(user_id)
        prefixes = []
        if reply_to_message_id:
            prefixes.append(f"[CQ:reply,id={reply_to_message_id}]")
        if mention_target:
            prefixes.append(f"[CQ:at,qq={mention_target}]")
        if prefixes and parts:
            parts[0] = "".join(prefixes) + "\n" + parts[0]
        for index, part in enumerate(parts, start=1):
            self.logger.info("qq_send_part=%s/%s", index, len(parts))
            self.send_group_message(group_id, part)
            if index < len(parts):
                time.sleep(self.multi_msg_delay)

    def _extract_user_name(self, event: dict, member_info: dict | None = None):
        sender = event.get("sender") or {}
        card = sender.get("card") or (member_info or {}).get("card") or ""
        nickname = sender.get("nickname") or (member_info or {}).get("nickname") or ""
        return (nickname or card or str(event.get("user_id", ""))), card

    def _extract_group_name(self, event: dict, group_info: dict | None = None):
        return (group_info or {}).get("group_name") or event.get("group_name") or str(event.get("group_id", ""))

    def _strip_cq_codes(self, text: str):
        text = re.sub(r"\[CQ:reply,id=\d+\]", "", text)
        text = re.sub(r"\[CQ:at,qq=\d+[^\]]*\]", "", text)
        text = re.sub(r"\[CQ:image,[^\]]*\]", "", text)
        return text.strip()

    def _summarize_replied_message(self, raw_message: str):
        cleaned = self._strip_cq_codes(raw_message or "")
        return cleaned or "[引用了一条非文本消息]"

    def _extract_at_mentions(self, raw_message: str):
        mentions = []
        for at_id in re.findall(r"\[CQ:at,qq=(\d+)[^\]]*\]", raw_message or ""):
            if self.bot_user_id and str(at_id) == str(self.bot_user_id):
                mentions.append("未郁")
            else:
                mentions.append(f"qq={at_id}")
        return mentions

    def _extract_reply_context(self, event: dict):
        raw_message = event.get("raw_message") or ""
        reply_match = re.search(r"\[CQ:reply,id=(\d+)\]", raw_message)
        if not reply_match:
            return None

        reply_id = reply_match.group(1)
        context = {
            "reply_id": reply_id,
            "reply_sender_id": None,
            "reply_sender_name": "某人",
            "quoted_text": f"引用消息 id={reply_id}",
            "reply_targets_bot": False,
        }
        try:
            reply_data = self.fetch_message(reply_id)
            sender = reply_data.get("sender") or {}
            sender_name = sender.get("nickname") or sender.get("card") or "某人"
            sender_id = reply_data.get("user_id") or sender.get("user_id")
            quoted = self._summarize_replied_message(reply_data.get("raw_message", ""))
            context.update(
                {
                    "reply_sender_id": str(sender_id) if sender_id is not None else None,
                    "reply_sender_name": sender_name,
                    "quoted_text": f"引用消息（来自{sender_name}）：{quoted}",
                    "reply_targets_bot": bool(self.bot_user_id) and str(sender_id) == str(self.bot_user_id),
                }
            )
        except Exception as exc:
            self.logger.warning("fetch_reply_message_failed=%s", exc)
        return context

    def _render_message_for_llm(self, event: dict, cleaned_text: str, reply_context: dict | None = None):
        raw_message = event.get("raw_message") or ""
        parts = []
        image_urls = []
        at_mentions = self._extract_at_mentions(raw_message)

        if reply_context:
            parts.append(str(reply_context.get("quoted_text") or f"引用消息 id={reply_context.get('reply_id', 'unknown')}"))
        if at_mentions:
            parts.append(f"消息中@了：{', '.join(at_mentions)}")

        image_matches = re.findall(r"\[CQ:image,([^\]]+)\]", raw_message)
        for image_raw in image_matches:
            file_match = re.search(r"file=([^,\]]+)", image_raw)
            url_match = re.search(r"url=([^,\]]+)", image_raw)
            file_name = file_match.group(1) if file_match else "unknown"
            image_info = None
            if file_name and file_name != "unknown":
                try:
                    image_info = self.fetch_image(file_name)
                except Exception as exc:
                    self.logger.warning("fetch_image_failed file=%s error=%s", file_name, exc)
            image_url = None
            if image_info:
                image_url = image_info.get("url")
                file_name = image_info.get("file_name") or file_name
                file_size = image_info.get("file_size")
            else:
                image_url = html.unescape(url_match.group(1)) if url_match else None
                file_size = None

            description = f"用户发送了一张图片，文件名：{file_name}"
            if file_size:
                description += f"，大小：{file_size}字节"
            if image_url:
                description += f"，图片URL：{image_url}"
                image_urls.append(image_url)
            parts.append(description)

        text = self._strip_cq_codes(raw_message)
        if text:
            parts.append(f"用户文本：{text}")
        elif cleaned_text and not parts:
            parts.append(f"用户文本：{cleaned_text}")

        text_part = "\n".join(parts) if parts else cleaned_text
        if image_urls:
            content = []
            if text_part:
                content.append({"type": "text", "text": text_part})
            for image_url in image_urls:
                content.append({"type": "image_url", "image_url": {"url": image_url}})
            return content
        return text_part

    def _build_pending_context_summary(self, event: dict, user_name: str, cleaned_text: str, reply_context: dict | None = None):
        rendered = self._render_message_for_llm(event, cleaned_text, reply_context=reply_context)
        summary = self._content_to_text(rendered).replace("\n", " | ").strip()
        return {
            "message_id": str(event.get("message_id", "")).strip() or None,
            "user_name": user_name,
            "summary": summary or "[empty]",
        }

    def _handle_group_message(self, event: dict):
        group_id = str(event.get("group_id", ""))
        user_id = str(event.get("user_id", ""))
        self.bot_user_id = str(event.get("self_id") or self.bot_user_id)
        member_info = None
        group_info = None
        sender = event.get("sender") or {}
        if not sender.get("nickname") and group_id and user_id:
            try:
                member_info = self.fetch_group_member_info(group_id, user_id)
            except Exception as exc:
                self.logger.warning("fetch_group_member_info_failed=%s", exc)
        known_group = self.state_store.get_group_state(group_id)
        if not known_group.get("group_name") or known_group.get("group_name") == group_id:
            try:
                group_info = self.fetch_group_info(group_id)
            except Exception as exc:
                self.logger.warning("fetch_group_info_failed=%s", exc)

        user_name, card = self._extract_user_name(event, member_info)
        group_name = self._extract_group_name(event, group_info)
        self.state_store.touch_group_activity(group_id, group_name)
        self.state_store.get_relationship_state(group_id, user_id, user_name, card)

        self.logger.info("=== qq_event ===")
        self.logger.info(
            "group_id=%s group_name=%s user_id=%s user_name=%s card=%s raw_message=%s",
            group_id,
            group_name,
            user_id,
            user_name,
            card,
            event.get("raw_message", ""),
        )

        reply_context = self._extract_reply_context(event)
        allowed, reason, cleaned_text, metadata = self.router.filter_event(event, self.bot_user_id, reply_context=reply_context)
        self.logger.info("router_decision group_id=%s allowed=%s reason=%s metadata=%s", group_id, allowed, reason, json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True))
        current_entry = self._build_pending_context_summary(event, user_name, cleaned_text, reply_context=reply_context)
        if not allowed:
            if (metadata or {}).get("store_as_context"):
                self._append_pending_context(group_id, current_entry)
            return

        self.router.mark_llm_checked(group_id)

        llm_text = self._render_message_for_llm(event, cleaned_text, reply_context=reply_context)
        pending_contexts = self._pop_pending_context(group_id)
        if pending_contexts:
            self.logger.info("pending_context_drain group_id=%s size=%s", group_id, len(pending_contexts))
            llm_text = self._merge_pending_context(pending_contexts, llm_text, current_entry.get("message_id"))

        try:
            decision = self.agent.handle_passive_message(
                llm_text,
                user_id=user_id,
                user_name=user_name,
                group_id=group_id,
                group_name=group_name,
                card=card,
                session_id=f"group:{group_id}",
                trigger_reason=reason,
                trigger_metadata={
                    **(metadata or {}),
                    "current_message_id": current_entry.get("message_id"),
                    "buffered_message_ids": [item.get("message_id") for item in pending_contexts if item.get("message_id")],
                },
            )
        except requests.HTTPError as exc:
            should_retry_text_only = isinstance(llm_text, list) and exc.response is not None and exc.response.status_code == 400
            if should_retry_text_only:
                self.logger.warning("multimodal_request_rejected_retrying_text_only group_id=%s", group_id)
                text_only = self._content_to_text(llm_text)
                decision = self.agent.handle_passive_message(
                    text_only,
                    user_id=user_id,
                    user_name=user_name,
                    group_id=group_id,
                    group_name=group_name,
                    card=card,
                    session_id=f"group:{group_id}",
                    trigger_reason=reason,
                    trigger_metadata={
                        **(metadata or {}),
                        "multimodal_fallback": True,
                        "current_message_id": current_entry.get("message_id"),
                        "buffered_message_ids": [item.get("message_id") for item in pending_contexts if item.get("message_id")],
                    },
                )
            else:
                restore = pending_contexts + [current_entry]
                for item in restore:
                    self._append_pending_context(group_id, item)
                self.logger.warning("recoverable_llm_error_preserved_context group_id=%s", group_id)
                return
        except requests.RequestException:
            restore = pending_contexts + [current_entry]
            for item in restore:
                self._append_pending_context(group_id, item)
            self.logger.warning("recoverable_llm_error_preserved_context group_id=%s", group_id)
            return
        reply_messages = decision.get("reply_messages", [])
        mention_user = decision.get("mention_user", False)
        mention_user_id = decision.get("mention_user_id")
        reply_to_message_id = decision.get("reply_to_message_id")
        if reply_messages:
            duplicate_text = None
            if (metadata or {}).get("duplicate_repeat_candidate"):
                duplicate_text = str((metadata or {}).get("duplicate_text", "") or "").strip()
            self.send_group_reply(
                group_id,
                reply_messages,
                user_id=user_id,
                mention_user=mention_user,
                mention_user_id=mention_user_id,
                reply_to_message_id=reply_to_message_id,
            )
            self.router.mark_replied(group_id, duplicate_text=duplicate_text)

    def serve_forever(self):
        while True:
            try:
                if self.ws is None:
                    self.connect()
                ws = self.ws
                if ws is None:
                    continue
                raw = ws.recv()
                if not raw:
                    continue
                payload = json.loads(raw)
                if payload.get("post_type") == "message" and payload.get("message_type") == "group":
                    self._handle_group_message(payload)
            except WebSocketConnectionClosedException:
                self.logger.warning("qq_connection_closed=true")
                self.ws = None
                self.api_ws = None
                time.sleep(3)
            except requests.RequestException as exc:
                self.logger.exception("qq_request_error=%s", exc)
                time.sleep(1)
            except Exception as exc:
                self.logger.exception("qq_loop_error=%s", exc)
                self.ws = None
                self.api_ws = None
                time.sleep(3)
