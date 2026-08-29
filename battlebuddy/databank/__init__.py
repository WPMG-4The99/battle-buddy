"""Local wiki databank. Paste a URL. The app fetches. No account."""

from battlebuddy.databank.fetch import FetchResult, fetch_page
from battlebuddy.databank.search import AskResult, Hit, ask_pages, search_folder
from battlebuddy.databank.slug import databank_label, game_slug
from battlebuddy.databank.store import DatabankStore, Source
from battlebuddy.databank.wiki import WikiHome, ask_or_hunt, wiki_home_for

__all__ = [
    "AskResult",
    "DatabankStore",
    "FetchResult",
    "Hit",
    "Source",
    "WikiHome",
    "ask_or_hunt",
    "ask_pages",
    "databank_label",
    "fetch_page",
    "game_slug",
    "search_folder",
    "wiki_home_for",
]
