from agent.client import ArkClient
from agent.core import CatgirlAgent
from agent.logger import setup_logger
from agent.skills import SkillStore
from agent.state import StateStore
from config import (
    API_KEY,
    API_URL,
    BOT_NAME,
    DATA_DIR,
    DEBUG,
    DEFAULT_USER_ID,
    DEFAULT_USER_NAME,
    LOG_DIR,
    MODEL,
    SKILLS_DIR,
    validate_runtime,
)
import requests
from tools.registry import ToolRegistry


def main():
    validate_runtime()
    logger = setup_logger(LOG_DIR, debug=DEBUG)
    skill_store = SkillStore(SKILLS_DIR)
    state_store = StateStore(DATA_DIR)
    tool_registry = ToolRegistry(skill_store, state_store, logger)
    client = ArkClient(API_URL, API_KEY, MODEL, logger)
    agent = CatgirlAgent(client, skill_store, tool_registry, logger)
    current_user_id = DEFAULT_USER_ID
    current_user_name = DEFAULT_USER_NAME

    print(f"{BOT_NAME} 已准备好。输入 quit 退出。")
    print("Use /user <user_id> [user_name] to switch the active user context.")
    while True:
        user_text = input("you> ").strip()
        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            print(f"{BOT_NAME}> 那我先回病房了，{current_user_name}。")
            break
        if user_text.startswith("/user "):
            parts = user_text.split(maxsplit=2)
            if len(parts) < 2:
                print(f"{BOT_NAME}> 用法：/user <user_id> [user_name]")
                continue
            current_user_id = parts[1]
            if len(parts) == 3:
                current_user_name = parts[2]
            print(
                f"{BOT_NAME}> 好，我记住现在是用户 {current_user_id}（{current_user_name}）。"
            )
            continue

        try:
            answer = agent.handle_user_input(
                user_text, user_id=current_user_id, user_name=current_user_name
            )
            print(f"{BOT_NAME}> {answer}")
        except requests.RequestException:
            print(f"{BOT_NAME}> 刚才像是又断片了一下。你再说一次。")


if __name__ == "__main__":
    main()
