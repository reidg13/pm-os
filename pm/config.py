import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


def _load():
    cfg_file = DATA_DIR / "config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text())
    return {}


_cfg = _load()

VAULT_PATH = Path(
    _cfg.get("vault_path")
    or os.getenv("VAULT_PATH", "/Users/reidgilbertson/Documents/Obsidian Vault")
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ASANA_ACCESS_TOKEN = os.getenv("ASANA_ACCESS_TOKEN", "")
ASANA_WORKSPACE_GID = _cfg.get("asana_workspace_gid", "")
ASANA_USER_GID = _cfg.get("asana_user_gid", "")
ASANA_BOARDS = _cfg.get("asana_boards", [])  # [{gid, name}, ...]

CONFLUENCE_EMAIL = os.getenv("CONFLUENCE_EMAIL", "")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")
CONFLUENCE_BASE_URL = _cfg.get("confluence_base_url", "https://hotelengine.atlassian.net/wiki")

GOOGLE_CREDS_FILE = str(BASE_DIR / "google_credentials.json")
GOOGLE_TOKEN_FILE = str(BASE_DIR / "google_token.json")
