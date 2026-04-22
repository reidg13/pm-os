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


# -----------------------------------------------------------------------------
# Unified config loader — ~/.claude/config/cars.json
#
# The legacy constants above (VAULT_PATH, ASANA_*, etc.) come from data/config.json
# and .env, and stay where they are. This loader is for everything else that
# used to be hardcoded across skill files: Slack channels, spreadsheet IDs,
# Confluence spaces, priority people, Amplitude charts, Datadog dashboards,
# model IDs. Skills should use `get("dot.path")` instead of hardcoding.
# -----------------------------------------------------------------------------

_CARS_CONFIG_PATH = Path(
    os.environ.get("CARS_CONFIG_PATH", Path.home() / ".claude" / "config" / "cars.json")
)
_cars_cache: dict | None = None


def _load_cars_config(force: bool = False) -> dict:
    global _cars_cache
    if _cars_cache is None or force:
        if not _CARS_CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"Cars config not found at {_CARS_CONFIG_PATH}. Skills depend on this."
            )
        _cars_cache = json.loads(_CARS_CONFIG_PATH.read_text(encoding="utf-8"))
    return _cars_cache


def get(path: str, default=None):
    """Dot-path config access. Example: get('roadmap.spreadsheet_id')"""
    cfg = _load_cars_config()
    for part in path.split("."):
        if isinstance(cfg, dict) and part in cfg:
            cfg = cfg[part]
        else:
            return default
    return cfg


def require(path: str):
    """Like get() but raises KeyError if missing. Use for non-optional values."""
    val = get(path, default=None)
    if val is None:
        raise KeyError(f"Required config missing: {path}")
    return val


# CLI for shell use: `python -m pm.config roadmap.spreadsheet_id`
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(json.dumps(_load_cars_config(), indent=2))
    else:
        val = get(sys.argv[1])
        if val is None:
            sys.exit(f"key not found: {sys.argv[1]}")
        elif isinstance(val, (dict, list)):
            print(json.dumps(val))
        else:
            print(val)
