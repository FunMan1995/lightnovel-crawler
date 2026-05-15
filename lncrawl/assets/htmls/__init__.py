from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).parent


@lru_cache
def loading_html() -> str:
    return (ROOT / "loading.html").read_text()
