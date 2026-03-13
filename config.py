from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
SKILLS_DIR = BASE_DIR / "skills"
GROUP_WHITELIST_PATH = DATA_DIR / "group_whitelist.json"


def _env_flag(name: str, default: bool) -> bool:  # pyright: ignore[reportUnusedFunction]
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip()


def validate_runtime(require_qq: bool = False) -> None:
    missing = []
    if not API_KEY:
        missing.append("ARK_API_KEY")
    if require_qq and not QQ_WS_TOKEN:
        missing.append("QQ_WS_TOKEN")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

API_URL = os.getenv("ARK_API_URL", "https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions")
API_KEY = _env_str("ARK_API_KEY")
MODEL = "doubao-seed-2.0-pro"
DEBUG = _env_flag("CATGIRL_DEBUG", True)
DEFAULT_USER_ID = _env_str("CATGIRL_USER_ID", "local-user")
DEFAULT_USER_NAME = _env_str("CATGIRL_USER_NAME", "对方")
QQ_WS_URL = _env_str("QQ_WS_URL", "ws://127.0.0.1:3001")
QQ_WS_TOKEN = _env_str("QQ_WS_TOKEN")
QQ_REPLY_COOLDOWN_SECONDS = int(_env_str("QQ_REPLY_COOLDOWN_SECONDS", "45"))
QQ_LLM_COOLDOWN_SECONDS = int(_env_str("QQ_LLM_COOLDOWN_SECONDS", "30"))
QQ_MULTI_MSG_DELAY_SECONDS = float(_env_str("QQ_MULTI_MSG_DELAY_SECONDS", "0.15"))
