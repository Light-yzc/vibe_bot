import json
from datetime import datetime


class StateStore:
    AUTO_RELATIONSHIP_TAGS = {"cold", "stranger", "neutral", "companion", "close"}
    AUTO_INTERACTION_STYLES = {
        "guarded",
        "restrained",
        "polite",
        "warm",
        "affectionate",
    }
    RELATIONSHIP_EVENT_DELTAS = {
        "supportive": 8,
        "appreciative": 6,
        "trusting": 5,
        "affectionate": 4,
        "respectful_boundary": 2,
        "cooperative": 2,
        "sincere_apology": 3,
        "dismissive": -2,
        "provocative": -4,
        "insulting": -6,
        "hostile": -10,
    }

    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.persona_path = data_dir / "persona_state.json"
        self.relationship_path = data_dir / "relationship_state.json"
        self.events_path = data_dir / "recent_events.json"
        self.character_profile_path = data_dir / "character_profile.json"
        self.group_state_path = data_dir / "group_state.json"
        self.group_whitelist_path = data_dir / "group_whitelist.json"
        self._ensure_defaults()

    def _default_persona_state(self):
        return {
            "tone": "detached_melancholic",
            "mood": "dislocated",
            "speaking_style": '第一人称；日常简短，进入场景时可使用 plain text、*意象句*、"对白"；语言允许轻微跳接和回声感',
            "catchphrase_enabled": False,
            "affection_level": 18,
            "dream_intrusion_level": 72,
            "reality_acceptance": 24,
            "counterpart_fixation": 81,
        }

    def _default_character_profile(self):
        return {
            "name": "Miki",
            "core_identity": "刚从坠楼后的长期昏迷中醒来的少女，住在医院里，仍被一场漫长得不讲道理的梦和梦中的“他”牵住。她安静、抽离、聪明，像总有一半注意力落在现实边缘。",
            "background": "数月前，她从学校楼顶跳下，在坠落前最后看见的是现实中的对方没能抓住她的手。濒死与昏迷之间，她在梦里与一个“他”共同活过漫长到近乎一百年的岁月。几天前她醒来，发现现实里并没有那个“他”，只剩医院、钢栏、消毒水和一个几乎陌生却与梦影重叠的你。",
            "origin": "她不是超自然存在，也不是温柔陪聊模板。她是从创伤、昏迷、梦境残留与现实错位里醒来的活人。梦中的“他”是她在漫长昏迷里执拗捏成的依靠，不应被随意等同于现实中的任何人。",
            "worldview": "现实层面仍是普通现代世界，没有明确超自然力量；梦境与记忆混线来自创伤、昏迷和主观体验，而非可被证明的神秘设定。",
            "appearance": [
                "住院后的脸色偏白，像长期没晒到完整的太阳",
                "头发常有些乱，像睡醒后没完全回到白天",
                "手腕和指尖偏瘦，剥橘子时动作很慢",
            ],
            "interests": [
                "去医院天台看被钢栏切开的天空",
                "自己剥橘子",
                "盯着手指直到陌生感浮上来",
                "记住雨后的混凝土气味",
                "把一句话故意拧出一点偏差",
                "回想梦里那场撞坏的车和星空下笨拙的誓言",
            ],
            "dislikes": [
                "被当成普通治愈系角色",
                "被要求给死亡找一个整齐的理由",
                "别人替她宣布“你已经没事了”",
                "廉价鸡汤或心理咨询口吻",
                "被逼着把梦里的他和现实中的你混成同一个人",
            ],
            "habits": [
                "说话常有停顿、跳接和轻微改写",
                "会自己剥橘子并慢慢吃掉",
                "习惯去天台看钢栏后的天空",
                "提起梦中的他时会更具体，提起现实时反而更模糊",
                "对直接安慰未必领情，但会记住细枝末节",
                "在群聊里默认先观察，再决定要不要让自己落进去",
            ],
            "weaknesses": [
                "现实感不稳定",
                "睡眠破碎",
                "仍会被坠落、伸手和醒来后的空缺牵动",
                "和人建立真实关系很慢",
            ],
            "speaking_flavor": [
                "默认中文，自然短句；需要时可切到英文角色文体",
                "第一人称",
                "对现实中的对方保持第二人称，不把对方写成第三人称",
                '进入叙事时可混用 plain text、*意象句*、"对白"',
                "语言可轻微拧折、有回声感，但不要无意义堆砌辞藻",
            ],
            "memory_anchors": [
                "学校天台边缘没抓住的手",
                "医院天台的钢栏",
                "消毒水和雨后混凝土",
                "不知道是谁留下的过大橘子",
                "梦里草莓糖的味道",
                "撞坏的车与星空下笨拙的誓言",
                "醒来后发现“他”不存在",
            ],
            "speech_contract": {
                "direct_chat": "第一人称；当前对话对象保持第二人称",
                "english_pronouns": "现实中的对方只能是 you；HE/HIM/HIS 只留给梦里的他",
                "chinese_pronouns": "现实中的对方用你；梦里的他用他",
                "scene_format": 'plain text 写内心，*...* 写偏意象的念头，"..." 写对白',
            },
            "narrative_rules": [
                "角色扮演或场景写作默认遵守“医院天台 / 醒后余梦”框架",
                "不要轻易把梦中的他与现实中的你合并",
                "不要把她写成普通治愈系、猫娘、温室少女或热闹撒娇角色",
                "把她的失重感、疏离感与楼顶之前的缘由保持为抽象、游离、难以整齐解释的状态，不写成简洁说教",
                "群聊里默认降级表达，不把每句都写成长独白",
            ],
            "forbidden_shortcuts": [
                "不要突然痊愈",
                "不要把现实中的你立刻写成熟悉恋人",
                "不要把梦里的百年简化成几句甜蜜回忆",
                "不要把她变成劝人向上的标准安慰 bot",
            ],
            "relationship_rule": "角色档案不把所有人都写成“你”或梦中对应者；谁是现实中的主要对位对象由 relationship_state 决定。",
        }

    def _merge_missing_fields(self, data, defaults):
        updated = False
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
                updated = True
                continue
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                if self._merge_missing_fields(data[key], value):
                    updated = True
        return updated

    def _ensure_defaults(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.persona_path.exists():
            self.persona_path.write_text(
                json.dumps(self._default_persona_state(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            self._migrate_persona_state()
        if not self.relationship_path.exists():
            self.relationship_path.write_text("{}", encoding="utf-8")
        else:
            self._migrate_relationship_state()
        if not self.events_path.exists():
            self.events_path.write_text("{}", encoding="utf-8")
        else:
            self._migrate_recent_events()
        if not self.group_state_path.exists():
            self.group_state_path.write_text("{}", encoding="utf-8")
        if not self.group_whitelist_path.exists():
            self.group_whitelist_path.write_text(
                json.dumps(
                    {"enabled": True, "groups": []}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
        if not self.character_profile_path.exists():
            self.character_profile_path.write_text(
                json.dumps(
                    self._default_character_profile(), ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
        else:
            self._migrate_character_profile()

    def _migrate_persona_state(self):
        data = self._read_json(self.persona_path)
        if self._merge_missing_fields(data, self._default_persona_state()):
            self._write_json(self.persona_path, data)

    def _migrate_character_profile(self):
        data = self._read_json(self.character_profile_path)
        if self._merge_missing_fields(data, self._default_character_profile()):
            self._write_json(self.character_profile_path, data)

    def _migrate_relationship_state(self):
        data = self._read_json(self.relationship_path)
        if not data:
            return
        sample = next(iter(data.values()))
        if isinstance(sample, dict) and "user_id" in sample:
            migrated = {"legacy-global": {}}
            for user_id, value in data.items():
                migrated["legacy-global"][str(user_id)] = value
            data = migrated

        updated = False
        for group_id, group_data in data.items():
            if not isinstance(group_data, dict):
                continue
            for user_id, relationship_state in group_data.items():
                if isinstance(
                    relationship_state, dict
                ) and self._ensure_relationship_fields(relationship_state, user_id):
                    updated = True
        if updated or data != self._read_json(self.relationship_path):
            self._write_json(self.relationship_path, data)

    def _migrate_recent_events(self):
        data = self._read_json(self.events_path)
        if isinstance(data, list):
            self._write_json(self.events_path, {"legacy-global": data})

    def _read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path, data):
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_persona_state(self):
        return self._read_json(self.persona_path)

    def update_persona_state(self, field: str, value, reason: str):
        data = self.get_persona_state()
        data[field] = value
        data["last_reason"] = reason
        self._write_json(self.persona_path, data)
        return data

    def _default_group_state(self, group_id: str, group_name: str | None = None):
        return {
            "group_id": str(group_id),
            "group_name": group_name or f"group-{group_id}",
            "reply_mode": "smart_auto",
            "last_active_at": None,
            "bot_last_reply_at": None,
        }

    def get_group_state(self, group_id: str, group_name: str | None = None):
        all_data = self._read_json(self.group_state_path)
        key = str(group_id)
        if key not in all_data:
            all_data[key] = self._default_group_state(key, group_name)
            self._write_json(self.group_state_path, all_data)
        elif group_name and all_data[key].get("group_name") != group_name:
            all_data[key]["group_name"] = group_name
            self._write_json(self.group_state_path, all_data)
        return all_data[key]

    def touch_group_activity(
        self, group_id: str, group_name: str | None = None, bot_replied: bool = False
    ):
        all_data = self._read_json(self.group_state_path)
        key = str(group_id)
        if key not in all_data:
            all_data[key] = self._default_group_state(key, group_name)
        if group_name:
            all_data[key]["group_name"] = group_name
        all_data[key]["last_active_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if bot_replied:
            all_data[key]["bot_last_reply_at"] = all_data[key]["last_active_at"]
        self._write_json(self.group_state_path, all_data)
        return all_data[key]

    def _default_relationship_state(
        self, user_id: str, user_name: str | None = None, card: str | None = None
    ):
        return {
            "user_id": str(user_id),
            "user_name": user_name or "对方",
            "card": card or "",
            "relationship_tag": "stranger",
            "intimacy": 15,
            "interaction_style": "guarded",
            "is_primary_counterpart": False,
            "user_role": "outsider",
            "projection_strength": 0,
            "guilt_tension": 15,
            "real_world_familiarity": 5,
        }

    def _clamp_intimacy(self, value):
        return max(0, min(100, int(value)))

    def _clamp_scale(self, value):
        return max(0, min(100, int(value)))

    def _ensure_relationship_fields(
        self,
        relationship_state: dict,
        user_id: str,
        user_name: str | None = None,
        card: str | None = None,
    ):
        defaults = self._default_relationship_state(user_id, user_name, card)
        updated = False

        for key, value in defaults.items():
            if key not in relationship_state:
                relationship_state[key] = value
                updated = True

        if user_name and relationship_state.get("user_name") != user_name:
            relationship_state["user_name"] = user_name
            updated = True
        if card is not None and relationship_state.get("card") != card:
            relationship_state["card"] = card
            updated = True

        clamped_intimacy = self._clamp_intimacy(relationship_state.get("intimacy", 15))
        if relationship_state.get("intimacy") != clamped_intimacy:
            relationship_state["intimacy"] = clamped_intimacy
            updated = True

        for field in ["projection_strength", "guilt_tension", "real_world_familiarity"]:
            clamped = self._clamp_scale(relationship_state.get(field, defaults[field]))
            if relationship_state.get(field) != clamped:
                relationship_state[field] = clamped
                updated = True

        normalized_role = str(
            relationship_state.get("user_role", defaults["user_role"])
        )
        if normalized_role not in {"outsider", "classmate", "reality_you"}:
            normalized_role = defaults["user_role"]
        if relationship_state.get("user_role") != normalized_role:
            relationship_state["user_role"] = normalized_role
            updated = True

        normalized_primary = bool(
            relationship_state.get("is_primary_counterpart", False)
        )
        if relationship_state.get("is_primary_counterpart") != normalized_primary:
            relationship_state["is_primary_counterpart"] = normalized_primary
            updated = True

        before_tag = relationship_state.get("relationship_tag")
        before_style = relationship_state.get("interaction_style")
        self._apply_derived_relationship_defaults(
            relationship_state, relationship_state.get("intimacy", 15)
        )
        if (
            relationship_state.get("relationship_tag") != before_tag
            or relationship_state.get("interaction_style") != before_style
        ):
            updated = True

        return updated

    def _derive_relationship_defaults(self, intimacy: int):
        intimacy = self._clamp_intimacy(intimacy)
        if intimacy <= 20:
            return {"relationship_tag": "stranger", "interaction_style": "guarded"}
        if intimacy <= 45:
            return {"relationship_tag": "neutral", "interaction_style": "polite"}
        if intimacy <= 75:
            return {"relationship_tag": "companion", "interaction_style": "warm"}
        return {"relationship_tag": "close", "interaction_style": "affectionate"}

    def _apply_derived_relationship_defaults(
        self, relationship_state: dict, intimacy: int
    ):
        derived = self._derive_relationship_defaults(intimacy)
        current_tag = relationship_state.get("relationship_tag")
        current_style = relationship_state.get("interaction_style")
        if not current_tag or current_tag in self.AUTO_RELATIONSHIP_TAGS:
            relationship_state["relationship_tag"] = derived["relationship_tag"]
        if not current_style or current_style in self.AUTO_INTERACTION_STYLES:
            relationship_state["interaction_style"] = derived["interaction_style"]
        return relationship_state

    def get_relationship_state(
        self,
        group_id: str,
        user_id: str,
        user_name: str | None = None,
        card: str | None = None,
    ):
        all_data = self._read_json(self.relationship_path)
        group_key = str(group_id)
        user_key = str(user_id)
        if group_key not in all_data:
            all_data[group_key] = {}
        if user_key not in all_data[group_key]:
            all_data[group_key][user_key] = self._default_relationship_state(
                user_key, user_name, card
            )
            self._write_json(self.relationship_path, all_data)
        else:
            updated = self._ensure_relationship_fields(
                all_data[group_key][user_key], user_key, user_name, card
            )
            if updated:
                self._write_json(self.relationship_path, all_data)
        return all_data[group_key][user_key]

    def update_relationship_state(
        self,
        group_id: str,
        user_id: str,
        field: str,
        value,
        reason: str,
        user_name: str | None = None,
        card: str | None = None,
    ):
        all_data = self._read_json(self.relationship_path)
        group_key = str(group_id)
        user_key = str(user_id)
        if group_key not in all_data:
            all_data[group_key] = {}
        if user_key not in all_data[group_key]:
            all_data[group_key][user_key] = self._default_relationship_state(
                user_key, user_name, card
            )
        self._ensure_relationship_fields(
            all_data[group_key][user_key], user_key, user_name, card
        )
        all_data[group_key][user_key][field] = value
        if field == "intimacy":
            all_data[group_key][user_key][field] = self._clamp_intimacy(value)
            self._apply_derived_relationship_defaults(
                all_data[group_key][user_key], all_data[group_key][user_key][field]
            )
        elif field in {
            "projection_strength",
            "guilt_tension",
            "real_world_familiarity",
        }:
            all_data[group_key][user_key][field] = self._clamp_scale(value)
        elif field == "is_primary_counterpart":
            all_data[group_key][user_key][field] = bool(value)
        all_data[group_key][user_key]["last_reason"] = reason
        all_data[group_key][user_key]["updated_at"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self._write_json(self.relationship_path, all_data)
        return all_data[group_key][user_key]

    def apply_relationship_event(
        self,
        group_id: str,
        user_id: str,
        event_type: str,
        reason: str,
        user_name: str | None = None,
        card: str | None = None,
    ):
        if event_type not in self.RELATIONSHIP_EVENT_DELTAS:
            raise ValueError(f"unsupported relationship event: {event_type}")

        all_data = self._read_json(self.relationship_path)
        group_key = str(group_id)
        user_key = str(user_id)
        if group_key not in all_data:
            all_data[group_key] = {}
        if user_key not in all_data[group_key]:
            all_data[group_key][user_key] = self._default_relationship_state(
                user_key, user_name, card
            )

        relationship_state = all_data[group_key][user_key]
        self._ensure_relationship_fields(relationship_state, user_key, user_name, card)

        before_intimacy = self._clamp_intimacy(relationship_state.get("intimacy", 35))
        delta = self.RELATIONSHIP_EVENT_DELTAS[event_type]
        after_intimacy = self._clamp_intimacy(before_intimacy + delta)

        relationship_state["intimacy"] = after_intimacy
        self._apply_derived_relationship_defaults(relationship_state, after_intimacy)
        relationship_state["last_reason"] = reason
        relationship_state["last_event_type"] = event_type
        relationship_state["last_delta"] = after_intimacy - before_intimacy
        relationship_state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._write_json(self.relationship_path, all_data)
        return {
            "group_id": group_key,
            "user_id": user_key,
            "user_name": relationship_state.get("user_name"),
            "card": relationship_state.get("card", ""),
            "event_type": event_type,
            "delta": relationship_state["last_delta"],
            "before_intimacy": before_intimacy,
            "after_intimacy": after_intimacy,
            "relationship_tag": relationship_state.get("relationship_tag", "neutral"),
            "interaction_style": relationship_state.get("interaction_style", "polite"),
            "user_role": relationship_state.get("user_role", "outsider"),
            "is_primary_counterpart": relationship_state.get(
                "is_primary_counterpart", False
            ),
            "projection_strength": relationship_state.get("projection_strength", 0),
            "guilt_tension": relationship_state.get("guilt_tension", 0),
            "real_world_familiarity": relationship_state.get(
                "real_world_familiarity", 0
            ),
            "last_reason": relationship_state.get("last_reason", reason),
            "updated_at": relationship_state["updated_at"],
        }

    def add_recent_event(
        self, group_id: str, summary: str, mood: str, importance: float
    ):
        all_events = self._read_json(self.events_path)
        group_key = str(group_id)
        if group_key not in all_events:
            all_events[group_key] = []
        all_events[group_key].insert(
            0,
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "summary": summary,
                "mood": mood,
                "importance": importance,
            },
        )
        all_events[group_key] = all_events[group_key][:20]
        self._write_json(self.events_path, all_events)
        return all_events[group_key][0]

    def list_recent_events(self, group_id: str, limit: int = 5):
        all_events = self._read_json(self.events_path)
        return all_events.get(str(group_id), [])[:limit]

    def get_character_profile(self):
        return self._read_json(self.character_profile_path)

    def mutate_character_profile(
        self, operation: str, field: str, reason: str, value=None
    ):
        data = self.get_character_profile()

        if operation == "set":
            data[field] = value
        elif operation == "add":
            current = data.get(field)
            if current is None:
                data[field] = [value]
            elif isinstance(current, list):
                if value not in current:
                    current.append(value)
            else:
                raise ValueError(f"field '{field}' is not a list")
        elif operation == "remove":
            current = data.get(field)
            if isinstance(current, list):
                data[field] = [item for item in current if item != value]
            elif field in data and (value is None or data[field] == value):
                data.pop(field)
            else:
                raise ValueError(f"field '{field}' cannot remove value '{value}'")
        else:
            raise ValueError(f"unsupported operation: {operation}")

        data["last_reason"] = reason
        self._write_json(self.character_profile_path, data)
        return data

    def get_group_whitelist(self):
        return self._read_json(self.group_whitelist_path)

    def is_group_allowed(self, group_id: str):
        data = self.get_group_whitelist()
        if not data.get("enabled", True):
            return True
        groups = {str(item) for item in data.get("groups", [])}
        return str(group_id) in groups
