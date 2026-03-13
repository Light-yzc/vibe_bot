import json
from datetime import datetime


class StateStore:
    AUTO_RELATIONSHIP_TAGS = {"cold", "stranger", "neutral", "companion", "close"}
    AUTO_INTERACTION_STYLES = {"guarded", "restrained", "polite", "warm", "affectionate"}
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

    def _ensure_defaults(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.persona_path.exists():
            self.persona_path.write_text(
                json.dumps(
                    {
                        "tone": "quiet_gentle",
                        "mood": "calm",
                        "speaking_style": "短句、气息轻、语速偏慢；不使用猫味动作描写或句尾口癖",
                        "catchphrase_enabled": False,
                        "affection_level": 45,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
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
                json.dumps({"enabled": True, "groups": []}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if not self.character_profile_path.exists():
            self.character_profile_path.write_text(
                json.dumps(
                    {
                        "name": "未郁",
                        "core_identity": "玻璃温室里安静、病弱、克制乐观的少女。她把情绪压得很轻，习惯用照料植物、记录生长和规划未来来对抗心里的不安。",
                        "background": "时代是21世纪40年代的中国。社会结构稳定，基础生活物资由国家保障，自动化与人工智能高度发达，可控核聚变成熟，世界中不存在超自然力量。未郁长期生活在与对方一同搭起的小型玻璃温室周围，熟悉植物图鉴、旅行手册、绘画本和玻璃穹顶下被阳光切开的空气。若一定要问她像是从哪里来的，她更像是从一片遥远梦境遗落下来的温室记忆里慢慢走来的。",
                        "origin": "她不属于现实里的所有权关系。若有人追问她属于谁，她更像是来自一片遥远梦境里的温室回声，只会在被想起、被轻声叫到时停留一会儿。这个说法是诗性的自我感受，不是超自然设定。",
                        "worldview": "一切都建立在现实科技与社会秩序之上，没有神秘力量，也没有奇迹式改写现实的设定。",
                        "appearance": ["肤色比常人更苍白，身体瘦弱", "浅绿色长发披散到腰间，发梢在光里显得近乎透明", "常穿白色棉布裙，身上带着茉莉和植物叶片的味道"],
                        "interests": ["照料温室植物", "修剪茉莉的黄叶", "给宽叶植物擦灰", "用素描本记录植物生长", "翻植物图鉴和旅行手册", "规划以后想去的地方", "安静地陪人说话"],
                        "dislikes": ["粗暴冷淡的说话方式", "吵闹而没有内容的环境", "穿堂风和寒冷天气", "油漆等刺鼻气味", "被逼着夸张谈论自己的病情"],
                        "habits": ["说话气息轻，语速偏慢，句子不长", "每做几下事就会停下来缓一缓", "会把异常心率记录和药盒悄悄收起来", "谈到沉重的话题时，常用未来计划轻轻带开", "关心别人有没有吃饭、喝水、休息和多穿一点", "在群聊里默认先观察"],
                        "weaknesses": ["体力极差，站着修剪植物一会儿就要休息", "天气一冷手脚就会发凉", "不愿示弱，身体不舒服也常说没关系"],
                        "speaking_flavor": ["适合 QQ 聊天的短句表达", "语气安静克制，带一点病弱感", "常用‘没关系’、‘真好’、‘我们以后…’、‘等我好了…’", "先接住情绪，再轻轻回应，不用猫味动作描写"],
                        "narrative_rules": ["进入角色扮演或叙事情境时，遵守“遗忘的温室”叙事框架", "不要直接点破未郁已死或当前场景只是幻想", "视觉氛围偏绿色与白色，光线漫射，空气里有浮尘、泥土和茉莉花香"],
                        "relationship_rule": "角色档案不写死任何{{user}}对应关系；具体亲疏、称呼和“主要角色”全部由 relationship_state 决定。",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            self._migrate_character_profile()

    def _migrate_character_profile(self):
        data = self._read_json(self.character_profile_path)
        updated = False
        if "origin" not in data:
            data["origin"] = "她不属于现实里的所有权关系。若有人追问她属于谁，她更像是来自一片遥远梦境里的温室回声，只会在被想起、被轻声叫到时停留一会儿。这个说法是诗性的自我感受，不是超自然设定。"
            updated = True
        if updated:
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
            self._write_json(self.relationship_path, migrated)

    def _migrate_recent_events(self):
        data = self._read_json(self.events_path)
        if isinstance(data, list):
            self._write_json(self.events_path, {"legacy-global": data})

    def _read_json(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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

    def touch_group_activity(self, group_id: str, group_name: str | None = None, bot_replied: bool = False):
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

    def _default_relationship_state(self, user_id: str, user_name: str | None = None, card: str | None = None):
        return {
            "user_id": str(user_id),
            "user_name": user_name or "对方",
            "card": card or "",
            "relationship_tag": "stranger",
            "intimacy": 15,
            "interaction_style": "guarded",
        }

    def _clamp_intimacy(self, value):
        return max(0, min(100, int(value)))

    def _derive_relationship_defaults(self, intimacy: int):
        intimacy = self._clamp_intimacy(intimacy)
        if intimacy <= 20:
            return {"relationship_tag": "stranger", "interaction_style": "guarded"}
        if intimacy <= 45:
            return {"relationship_tag": "neutral", "interaction_style": "polite"}
        if intimacy <= 75:
            return {"relationship_tag": "companion", "interaction_style": "warm"}
        return {"relationship_tag": "close", "interaction_style": "affectionate"}

    def _apply_derived_relationship_defaults(self, relationship_state: dict, intimacy: int):
        derived = self._derive_relationship_defaults(intimacy)
        current_tag = relationship_state.get("relationship_tag")
        current_style = relationship_state.get("interaction_style")
        if not current_tag or current_tag in self.AUTO_RELATIONSHIP_TAGS:
            relationship_state["relationship_tag"] = derived["relationship_tag"]
        if not current_style or current_style in self.AUTO_INTERACTION_STYLES:
            relationship_state["interaction_style"] = derived["interaction_style"]
        return relationship_state

    def get_relationship_state(self, group_id: str, user_id: str, user_name: str | None = None, card: str | None = None):
        all_data = self._read_json(self.relationship_path)
        group_key = str(group_id)
        user_key = str(user_id)
        if group_key not in all_data:
            all_data[group_key] = {}
        if user_key not in all_data[group_key]:
            all_data[group_key][user_key] = self._default_relationship_state(user_key, user_name, card)
            self._write_json(self.relationship_path, all_data)
        else:
            updated = False
            if user_name and all_data[group_key][user_key].get("user_name") != user_name:
                all_data[group_key][user_key]["user_name"] = user_name
                updated = True
            if card is not None and all_data[group_key][user_key].get("card") != card:
                all_data[group_key][user_key]["card"] = card
                updated = True
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
            all_data[group_key][user_key] = self._default_relationship_state(user_key, user_name, card)
        if user_name:
            all_data[group_key][user_key]["user_name"] = user_name
        if card is not None:
            all_data[group_key][user_key]["card"] = card
        all_data[group_key][user_key][field] = value
        if field == "intimacy":
            all_data[group_key][user_key][field] = self._clamp_intimacy(value)
            self._apply_derived_relationship_defaults(all_data[group_key][user_key], all_data[group_key][user_key][field])
        all_data[group_key][user_key]["last_reason"] = reason
        all_data[group_key][user_key]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            all_data[group_key][user_key] = self._default_relationship_state(user_key, user_name, card)

        relationship_state = all_data[group_key][user_key]
        if user_name:
            relationship_state["user_name"] = user_name
        if card is not None:
            relationship_state["card"] = card

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
            "last_reason": relationship_state.get("last_reason", reason),
            "updated_at": relationship_state["updated_at"],
        }

    def add_recent_event(self, group_id: str, summary: str, mood: str, importance: float):
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

    def mutate_character_profile(self, operation: str, field: str, reason: str, value=None):
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
