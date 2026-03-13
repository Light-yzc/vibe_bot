from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.qq_ws import NapCatWebSocketAdapter
from agent.qq_router import QQRouter


class DummyStateStore:
    def is_group_allowed(self, group_id: str):
        return True

    def touch_group_activity(self, group_id: str, group_name: str | None = None, bot_replied: bool = False):
        return None


class DummyLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


def make_router():
    return QQRouter(DummyStateStore(), DummyLogger())


def test_router_ignores_ordinary_group_chatter():
    router = make_router()
    allowed, reason, cleaned, metadata = router.filter_event(
        {
            "group_id": "100",
            "user_id": "200",
            "raw_message": "今晚吃什么",
        },
        bot_user_id="999",
    )

    assert allowed is True
    assert reason == "observe_all"
    assert cleaned == "今晚吃什么"
    assert metadata is not None
    assert metadata["ordinary_message_candidate"] is True


def test_router_does_not_treat_generic_help_question_as_direct_trigger():
    router = make_router()
    allowed, reason, cleaned, metadata = router.filter_event(
        {
            "group_id": "100",
            "user_id": "200",
            "raw_message": "谁能帮我看看这个图？",
        },
        bot_user_id="999",
    )

    assert allowed is True
    assert reason == "observe_all"
    assert cleaned == "谁能帮我看看这个图？"
    assert metadata is not None
    assert metadata["targeted_question"] is True


def test_router_marks_recent_context_help_as_second_person_question():
    router = make_router()
    router.mark_replied("100")
    allowed, reason, _cleaned, metadata = router.filter_event(
        {
            "group_id": "100",
            "user_id": "200",
            "raw_message": "你帮我看看这个图？",
        },
        bot_user_id="999",
    )

    assert allowed is True
    assert reason == "second_person_question"
    assert metadata is not None
    assert metadata["targeted_question"] is True
    assert metadata["contextual_engagement"] is True


def test_router_allows_direct_name_trigger():
    router = make_router()
    allowed, reason, _cleaned, metadata = router.filter_event(
        {
            "group_id": "100",
            "user_id": "200",
            "raw_message": "未郁，你在吗",
        },
        bot_user_id="999",
    )

    assert allowed is True
    assert reason == "direct_trigger"
    assert metadata is not None
    assert metadata["contains_name"] is True


def test_render_message_for_llm_keeps_current_speaker_name():
    adapter = NapCatWebSocketAdapter("ws://example.invalid", "token", DummyLogger(), DummyStateStore(), None, None)
    rendered = adapter._render_message_for_llm(
        {
            "user_id": "200",
            "raw_message": "未郁，你在吗",
        },
        "未郁，你在吗",
        user_name="小满",
    )

    assert isinstance(rendered, str)
    assert "当前发言人：小满" in rendered
    assert "用户文本：未郁，你在吗" in rendered


def test_router_image_message_does_not_become_question_from_url():
    router = make_router()
    allowed, reason, cleaned, metadata = router.filter_event(
        {
            "group_id": "100",
            "user_id": "200",
            "raw_message": "[CQ:image,file=foo.jpg,url=https://example.com/a?x=1,file_size=12]",
        },
        bot_user_id="999",
    )

    assert allowed is True
    assert reason == "observe_all"
    assert cleaned == "[图片]"
    assert metadata is not None
    assert metadata["direct_question"] is False
    assert metadata["targeted_question"] is False


def test_render_message_uses_embedded_image_url_without_fetching():
    class TrackingAdapter(NapCatWebSocketAdapter):
        def __init__(self):
            super().__init__("ws://example.invalid", "token", DummyLogger(), DummyStateStore(), None, None)
            self.fetch_calls = 0

        def fetch_image(self, file_name: str):
            self.fetch_calls += 1
            raise AssertionError("fetch_image should not be called when CQ image already has url")

    adapter = TrackingAdapter()
    rendered = adapter._render_message_for_llm(
        {
            "user_id": "200",
            "raw_message": "[CQ:image,file=foo.jpg,url=https://example.com/a?x=1,file_size=12]",
        },
        "[图片]",
        user_name="小满",
    )

    assert adapter.fetch_calls == 0
    assert isinstance(rendered, list)
    assert rendered[0]["type"] == "text"
    assert "文件名：foo.jpg" in rendered[0]["text"]
    assert rendered[1]["image_url"]["url"] == "https://example.com/a?x=1"


def test_router_skips_ordinary_message_during_backoff_only():
    router = make_router()
    backoff_seconds = router.mark_llm_failed("100")

    assert backoff_seconds > 0
    assert router.should_skip_llm("100", {"ordinary_message_candidate": True, "direct_engagement": False}) is True
    assert router.should_skip_llm("100", {"ordinary_message_candidate": True, "direct_engagement": True}) is False


def test_trim_session_messages_keeps_head_and_tail():
    from agent.core import CatgirlAgent

    agent = CatgirlAgent(None, None, None, DummyLogger())
    messages = [
        {"role": "system", "content": "base"},
        {"role": "system", "content": "Conversation continuity summary:\nold"},
    ] + [{"role": "user", "content": str(i)} for i in range(10)]

    agent._trim_session_messages(messages, max_messages=6)

    assert len(messages) == 6
    assert messages[0]["content"] == "base"
    assert messages[1]["content"].startswith("Conversation continuity summary:")
    assert [item["content"] for item in messages[2:]] == ["6", "7", "8", "9"]
