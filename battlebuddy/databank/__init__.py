"""Local wiki databank. Paste a URL. The app fetches. No account."""

from battlebuddy.databank.fetch import FetchResult, fetch_page
from battlebuddy.databank.slug import databank_label, game_slug
from battlebuddy.databank.store import DatabankStore, Source

__all__ = [
    "DatabankStore",
    "FetchResult",
    "Source",
    "databank_label",
    "fetch_page",
    "game_slug",
]
