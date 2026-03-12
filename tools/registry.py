import json
import ast
from datetime import datetime


class ToolRegistry:
    def __init__(self, skill_store, state_store, logger):
        self.skill_store = skill_store
        self.state_store = state_store
        self.logger = logger
        self.user_context = {
            "group_id": "local-group",
            "group_name": "CLI",
            "user_id": "local-user",
            "user_name": "对方",
            "card": "",
        }
        self.schemas = [
            {
                "type": "function",
                "function": {
                    "name": "ignore_group_message",
                    "description": "Explicitly choose silence for the current QQ group message. Use this only when the message is truly unrelated, too weak, or silence clearly fits better than speaking.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thought": {
                                "type": "string",
                                "description": "Optional short internal thought for logs and session context. This is never sent to the group.",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reply_group_message",
                    "description": "Reply to the current QQ group. Use this when 未郁 decides the current message deserves a response. If the message directly engages 未郁, asks her something, greets her, welcomes her, reacts to her last message, or offers an obvious social opening, prefer replying over silence. Prefer 1-3 short message bubbles. Default to plain messages without quote-reply when context is already clear. Set reply_to_message_id only when the target would otherwise be ambiguous, when answering one buffered older message, or when quoting is necessary to keep context clear. Use @ only when you want to explicitly pull someone in.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "messages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "One to three short QQ-style messages to send in order.",
                            },
                            "mention_user": {
                                "type": "boolean",
                                "description": "Whether to @ the current user in the first outgoing message.",
                            },
                            "mention_user_id": {
                                "type": "string",
                                "description": "Optional specific QQ user id to @ in the first outgoing message. If provided, it overrides mention_user.",
                            },
                            "reply_to_message_id": {
                                "type": "string",
                                "description": "Optional QQ message id to quote-reply. Leave this empty by default. Use it only when you need to anchor the reply to a specific message because context would otherwise be unclear.",
                            },
                        },
                        "required": ["messages"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_skill_sections",
                    "description": "List the available sections and short previews for a skill before loading full sections.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_id": {"type": "string"},
                        },
                        "required": ["skill_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "load_skill_section",
                    "description": "Load only the relevant sections of a skill instead of the whole skill file.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_id": {"type": "string"},
                            "section_names": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional sections like Guidance, Do, Avoid, Examples.",
                            },
                        },
                        "required": ["skill_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_character_profile",
                    "description": "Read the current roleplay background, interests, habits, and persona facts.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mutate_character_profile",
                    "description": "Add, rewrite, or delete character persona facts. Use set for scalar rewrite, add for list append, remove for deleting a value or field.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "operation": {"type": "string", "enum": ["set", "add", "remove"]},
                            "field": {"type": "string"},
                            "value": {
                                "description": "Required for set and add. For remove, pass the list item to delete or omit to remove a scalar field."
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["operation", "field", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_persona_state",
                    "description": "Read 未郁's current persona state.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_persona_state",
                    "description": "Update one persona field such as mood, tone, or speaking_style.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "value": {},
                            "reason": {"type": "string"},
                        },
                        "required": ["field", "value", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "apply_relationship_event",
                    "description": "Apply a predefined relationship event to the current user in the current group. Use this when the current message clearly raises or lowers closeness, trust, or favorability.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_type": {
                                "type": "string",
                                "enum": [
                                    "supportive",
                                    "appreciative",
                                    "trusting",
                                    "affectionate",
                                    "respectful_boundary",
                                    "cooperative",
                                    "sincere_apology",
                                    "dismissive",
                                    "provocative",
                                    "insulting",
                                    "hostile"
                                ]
                            },
                            "reason": {
                                "type": "string",
                                "description": "Short explanation tied to the current message, such as what the user said or did."
                            }
                        },
                        "required": ["event_type", "reason"]
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_relationship_state",
                    "description": "Read the current relationship state between 未郁 and the current user in the current group.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "update_relationship_state",
                    "description": "Update one relationship field for the current user in the current group, such as user_name, relationship_tag, intimacy, or interaction_style.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "value": {},
                            "reason": {"type": "string"},
                        },
                        "required": ["field", "value", "reason"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_recent_event",
                    "description": "Record a recent interesting event for the current group.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "mood": {"type": "string"},
                            "importance": {"type": "number"},
                        },
                        "required": ["summary", "mood", "importance"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_recent_events",
                    "description": "List recent interesting events in the current group.",
                    "parameters": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer"}},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Get the current local time.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": [],
                    },
                },
            },
        ]

    def _compact_log_value(self, value, limit: int = 240):
        try:
            if isinstance(value, str):
                text = value
            else:
                text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            text = str(value)

        text = text.replace("\n", "\\n").replace("\r", "")
        if len(text) > limit:
            return f"{text[: limit - 3]}..."
        return text

    def set_user_context(
        self,
        user_id: str,
        user_name: str | None = None,
        group_id: str = "local-group",
        group_name: str = "CLI",
        card: str | None = None,
    ):
        self.user_context = {
            "group_id": str(group_id),
            "group_name": group_name,
            "user_id": str(user_id),
            "user_name": user_name or self.user_context.get("user_name") or "对方",
            "card": card or "",
        }

    def execute(self, tool_call):
        tool_call_id = tool_call.get("id", "unknown")
        name = tool_call["function"]["name"]
        raw_arguments = tool_call["function"].get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            try:
                arguments = ast.literal_eval(raw_arguments)
            except Exception as exc:
                self.logger.error("tool_argument_parse_failed tool=%s raw=%s error=%s", name, raw_arguments, exc)
                raise
        self.logger.info(
            "tool_call id=%s name=%s args=%s",
            tool_call_id,
            name,
            self._compact_log_value(arguments),
        )

        if name == "ignore_group_message":
            thought = str(arguments.get("thought", "")).strip()
            result = {
                "_final_action": "ignore_group_message",
                "thought": thought,
            }
        elif name == "reply_group_message":
            messages = [str(item).strip() for item in arguments.get("messages", []) if str(item).strip()]
            mention_user_id = arguments.get("mention_user_id")
            reply_to_message_id = arguments.get("reply_to_message_id")
            result = {
                "_final_action": "reply_group_message",
                "messages": messages,
                "mention_user": bool(arguments.get("mention_user", False)),
                "mention_user_id": str(mention_user_id).strip() if mention_user_id is not None and str(mention_user_id).strip() else None,
                "reply_to_message_id": str(reply_to_message_id).strip() if reply_to_message_id is not None and str(reply_to_message_id).strip() else None,
            }
        elif name == "list_skill_sections":
            result = self.skill_store.list_skill_sections(arguments["skill_id"])
        elif name == "load_skill_section":
            result = self.skill_store.load_skill_section(arguments["skill_id"], arguments.get("section_names"))
        elif name == "get_character_profile":
            result = self.state_store.get_character_profile()
        elif name == "mutate_character_profile":
            result = self.state_store.mutate_character_profile(
                arguments["operation"],
                arguments["field"],
                arguments["reason"],
                arguments.get("value"),
            )
        elif name == "get_persona_state":
            result = self.state_store.get_persona_state()
        elif name == "update_persona_state":
            result = self.state_store.update_persona_state(arguments["field"], arguments["value"], arguments["reason"])
        elif name == "get_relationship_state":
            result = self.state_store.get_relationship_state(
                self.user_context["group_id"],
                self.user_context["user_id"],
                self.user_context.get("user_name"),
                self.user_context.get("card"),
            )
        elif name == "apply_relationship_event":
            result = self.state_store.apply_relationship_event(
                self.user_context["group_id"],
                self.user_context["user_id"],
                arguments["event_type"],
                arguments["reason"],
                self.user_context.get("user_name"),
                self.user_context.get("card"),
            )
        elif name == "update_relationship_state":
            result = self.state_store.update_relationship_state(
                self.user_context["group_id"],
                self.user_context["user_id"],
                arguments["field"],
                arguments["value"],
                arguments["reason"],
                self.user_context.get("user_name"),
                self.user_context.get("card"),
            )
        elif name == "add_recent_event":
            result = self.state_store.add_recent_event(
                self.user_context["group_id"],
                arguments["summary"],
                arguments["mood"],
                arguments["importance"],
            )
        elif name == "list_recent_events":
            result = self.state_store.list_recent_events(self.user_context["group_id"], arguments.get("limit", 5))
        elif name == "get_time":
            result = {
                "city": arguments.get("city", "local"),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        else:
            result = {"error": f"unknown tool: {name}"}

        ok = not (isinstance(result, dict) and result.get("error"))
        self.logger.info(
            "tool_result id=%s name=%s ok=%s result=%s",
            tool_call_id,
            name,
            ok,
            self._compact_log_value(result, limit=320),
        )
        return result
