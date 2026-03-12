from agent.client import ArkClient
from agent.core import CatgirlAgent
from agent.logger import setup_logger
from agent.qq_router import QQRouter
from agent.skills import SkillStore
from agent.state import StateStore
from config import API_KEY, API_URL, DATA_DIR, DEBUG, LOG_DIR, MODEL, QQ_LLM_COOLDOWN_SECONDS, QQ_MULTI_MSG_DELAY_SECONDS, QQ_REPLY_COOLDOWN_SECONDS, QQ_WS_TOKEN, QQ_WS_URL, SKILLS_DIR, validate_runtime
from tools.registry import ToolRegistry
from adapters.qq_ws import NapCatWebSocketAdapter


def main():
    validate_runtime(require_qq=True)
    logger = setup_logger(LOG_DIR, debug=DEBUG)
    skill_store = SkillStore(SKILLS_DIR)
    state_store = StateStore(DATA_DIR)
    tool_registry = ToolRegistry(skill_store, state_store, logger)
    client = ArkClient(API_URL, API_KEY, MODEL, logger)
    agent = CatgirlAgent(client, skill_store, tool_registry, logger)
    router = QQRouter(
        state_store,
        logger,
        cooldown_seconds=QQ_REPLY_COOLDOWN_SECONDS,
        llm_cooldown_seconds=QQ_LLM_COOLDOWN_SECONDS,
    )
    adapter = NapCatWebSocketAdapter(QQ_WS_URL, QQ_WS_TOKEN, logger, state_store, router, agent, multi_msg_delay=QQ_MULTI_MSG_DELAY_SECONDS)

    print("未郁 QQ adapter is running...")
    adapter.serve_forever()


if __name__ == "__main__":
    main()
