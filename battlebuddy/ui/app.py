"""High-contrast UI. One primary action: set a reminder. No account."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone

from battlebuddy.databank.reason import start_bundled_server, stop_bundled_server
from battlebuddy.databank.search import ask_pages
from battlebuddy.databank.seed import (
    needs_wiki_seed,
    seed_hold_line,
    seed_new_game,
)
from battlebuddy.databank.slug import databank_label, game_slug
from battlebuddy.databank.store import DatabankStore
from battlebuddy.databank.wiki import ask_or_hunt, rank_ask_result, should_hunt
from battlebuddy.game_detect import detect_game, status_line
from battlebuddy.memory.catalog import KnowledgeCatalog, seen_on_disk_line
from battlebuddy.memory.war_room import ROSTER_NAMES, parse_war_room_line
from battlebuddy.reminders.commands import run_line
from battlebuddy.vision.miss import is_miss_command, miss_check
from battlebuddy.session.tier import (
    TIER_GENTLE,
    TIER_HANDHOLD,
    TIER_LABELS,
    TIER_SOCRATIC,
    load_brain,
    load_tier,
    load_window,
    parse_tk_geometry,
    save_tier,
    save_window,
    window_geometry,
)
from battlebuddy.ui.layout import (
    STACK_COLUMNS_BELOW,
    columns_stacked,
    wheel_units,
    wrap_positions,
)
from battlebuddy.harvest.locate import load_harvest
from battlebuddy.xai.loop import answer_ask, api_key, reason_utterance
from battlebuddy.reminders.engine import STATUS_PENDING, Reminder, ReminderEngine
from battlebuddy.reminders.hygiene import is_active as hygiene_is_active
from battlebuddy.reminders.notify import fire_banner
from battlebuddy.reminders.parse import is_clear_all
from battlebuddy.reminders.warn import pending_minute_warns
from battlebuddy.ui.hud import HudOverlay
from battlebuddy.ui.overlay_win import enable_dpi_awareness
from battlebuddy.readthis.config import load_stop_hotkey, stop_hotkey_label
from battlebuddy.readthis.listen import STOP_HOTKEY_ID, HotkeyListener
from battlebuddy.readthis.service import ReadAloud
from battlebuddy.snap.service import SnapAsk
from battlebuddy.voice.stt import listen_once, stt_available
from battlebuddy.voice.tick import play_ticks_async
from battlebuddy.voice.tts import speak_async, spoken_line, stop_speaking, tts_available

_BG = "#0B0B0B"
_GOLD = "#E6C35C"
_FG = "#F4F1E8"
_SCARLET = "#C41E3A"
_PURPLE = "#7B3FA8"
_FIRE_BG = "#0B0B0B"
_FIRE_FG = "#E6C35C"
_INPUT_BG = "#161616"
_CARD = "#141414"
_EDGE = "#2A2A2A"
_MUTED = "#C4C0B4"
_BTN_DARK = "#1F1F1F"
_BTN_DARK_HI = "#2A2A2A"
_EXAMPLE = "remind me in 1 minute to check food stores"
_QUERY_HINT = "Paste a wiki link or ask a game question"
_POLL_MS = 250
_DETECT_EVERY = 20
_CLOCK_FONT = ("Arial", 40, "bold")
_TITLE_FONT = ("Arial", 30, "bold")
_BODY_FONT = ("Arial", 16)
_HINT_FONT = ("Arial", 14)
_MIN_WIDTH = 720
_MIN_HEIGHT = 560
_DEFAULT_GEOMETRY = "1200x800"
_WAR_KINDS: tuple[tuple[str, str], ...] = (
    ("Place", "place"),
    ("Trap", "trap"),
    ("Decision", "decision"),
    ("Patch", "patch"),
)
_TIER_CHIPS: tuple[tuple[str, str], ...] = (
    ("Hand-hold", TIER_HANDHOLD),
    ("Gentle", TIER_GENTLE),
    ("Socratic", TIER_SOCRATIC),
)
_SAY_WRONG = "Say if this is wrong."


def war_room_oneliner(name: str, place: str | None, patch: str | None) -> str:
    """One line of current standing state. Not the full log."""
    if place is None and patch is None:
        return f"{name} · War Room empty."
    shown_place = place if place else "—"
    shown_patch = patch if patch else "—"
    return f"{name} · {shown_place} · patch {shown_patch}"


def remaining_seconds(due_at: str, now: datetime | None = None) -> int:
    """Whole seconds left until due. Floor at 0. Local display helper."""
    moment = now if now is not None else datetime.now(timezone.utc)
    due = datetime.fromisoformat(due_at)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    else:
        due = due.astimezone(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    left = int((due - moment).total_seconds())
    return left if left > 0 else 0


def format_countdown(seconds: int) -> str:
    """ADHD clock: 0:47 or 12:05. Minutes can pass 60."""
    remaining = max(0, int(seconds))
    minutes, secs = divmod(remaining, 60)
    return f"{minutes}:{secs:02d}"


def row_clock_text(status: str, due_at: str, now: datetime | None = None) -> str:
    """Pending rows countdown. Fired/cancelled keep FIRED / CANCELLED."""
    if status != STATUS_PENDING:
        return status.upper()
    return format_countdown(remaining_seconds(due_at, now))


def is_named_game(name: str | None) -> bool:
    """True when detect has a real game name, not a blank flicker."""
    return bool((name or "").strip())


def looks_like_public_url(text: str) -> bool:
    """True for a public http(s) URL. Game questions go to ASK."""
    raw = (text or "").strip()
    if not raw or any(ch.isspace() for ch in raw):
        return False
    lower = raw.lower()
    if lower in {"http://", "https://"}:
        return False
    return lower.startswith("http://") or lower.startswith("https://")


def ask_visible_message(result: object) -> str:
    """Text ASK must put on the right output pane. Local search only."""
    output = getattr(result, "output", None)
    if callable(output):
        text = str(output())
    else:
        text = str(getattr(result, "message", "") or "")
    return text.strip()


_EMPTY_FOLDER = "No pages on disk for this game. ADD / FETCH a link first."


def shown_after_hunt_failure(local: object | None) -> str:
    """Keep the local pane. A crash is not a wiki miss."""
    if local is None:
        return _EMPTY_FOLDER
    return ask_visible_message(local)


def hunt_or_keep_local(
    store: object,
    game: str | None,
    question: str,
    local: object | None,
) -> tuple[object | None, str]:
    """Hunt and present. On any raise, keep the local AskResult."""
    result: object | None = local
    try:
        result = ask_or_hunt(store, game, question)
    except Exception:
        result = local
    try:
        if result is None:
            return result, shown_after_hunt_failure(None)
        return result, answer_ask(result, question, store, game)
    except Exception:
        return result, shown_after_hunt_failure(result)


def switched_databank_line(game: str | None) -> str:
    return f"Switched databank to {game_slug(game)}."


def sources_count_line(game: str | None, count: int) -> str:
    """One running total for the current game. No title dump."""
    name = (game or "").strip() or "General"
    pages = max(0, int(count))
    noun = "page" if pages == 1 else "pages"
    return f"{name} · {pages} {noun} on disk"


def _local_stamp(iso: str) -> str:
    parsed = datetime.fromisoformat(iso)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%H:%M:%S")


def _voice_footer() -> str:
    tts = "on" if tts_available() else "off (visual still fires)"
    stt = "on" if stt_available() else "off (type it)"
    return f"No account. TTS {tts}. STT {stt}."


def run_ui() -> int:
    from battlebuddy.readthis.screen import enable_dpi_awareness
    from battlebuddy.session.log import report, setup_logging

    try:
        setup_logging()
    except Exception:
        pass
    enable_dpi_awareness()
    try:
        import tkinter as tk
    except ImportError:
        print("No tkinter on this box. Typed path still works:")
        print("  python -m battlebuddy remind me in 1 minute to check food stores")
        return 1
    enable_dpi_awareness()
    app = BattleBuddyApp(tk)
    app.run()
    try:
        app = BattleBuddyApp(tk)
        app.run()
    except Exception as exc:
        report("UI crashed", exc)
        raise
    return 0


class BattleBuddyApp:
    def __init__(self, tk: object) -> None:
        self.tk = tk
        self.engine = ReminderEngine()
        self._listening = False
        self._fire_up = False
        self._firing: set[str] = set()
        self._selected_id: str | None = None
        self._wipe_armed = False
        self._clocks: dict[str, tuple[object, str]] = {}
        self._minute_warned: set[str] = set()
        self._game_busy = False
        self._miss_busy = False
        self._detect_ticks = 0

        self.root = tk.Tk()
        self.root.title("Battle Buddy")
        self.root.configure(bg=_BG)
        self.databank = DatabankStore()
        self.catalog = KnowledgeCatalog()
        self._game_name: str | None = self.catalog.last_game() or self.databank.sole_saved_game()
        self._fetching = False
        self._asking = False
        self._seed_started: set[str] = set()
        self.reader = ReadAloud(self._read_status, lambda: self._game_name, self._read_saved)
        self.snap = SnapAsk(
            self._read_status,
            lambda: self._game_name,
            lambda: self.databank,
        )

        self._wrap_busy: set[int] = set()
        self._columns_stacked: bool | None = None
        self._stop_listener: HotkeyListener | None = None
        self.root.minsize(720, 560)
        self.root.geometry("1200x800")
        self._hud: HudOverlay | None = None
        self._restore_window()

        self._build()
        self.reader.bind_ui(self.tk, self.root)
        self.snap.bind_ui(self.tk, self.root)
        try:
            self.read_line.config(text=self.reader.hint)
        except Exception:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._warm_bundled_llm, daemon=True).start()
        self.root.after(_POLL_MS, self._tick)

    def run(self) -> None:
        if self._hud is not None:
            try:
                self._hud.start()
            except Exception:
                pass
        try:
            self.reader.start_hotkey()
            self.snap.start_hotkey()
            self._start_stop_hotkey()
        except Exception:
            pass
        self.root.mainloop()

    def _build(self) -> None:
        tk = self.tk
        self._build_top_bar()

        footer = tk.Frame(self.root, bg=_BG)
        footer.pack(side="bottom", fill="x")
        self.voice_footer = tk.Label(
            footer,
            text=_voice_footer(),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
            anchor="w",
            justify="left",
            wraplength=680,
        )
        self.voice_footer.pack(fill="x", padx=20, pady=(4, 6))

        body = tk.Frame(self.root, bg=_BG)
        body.pack(fill="both", expand=True)
        self.page_scroll = tk.Scrollbar(body, orient="vertical")
        self.page_canvas = tk.Canvas(
            body,
            bg=_BG,
            highlightthickness=0,
            bd=0,
        )
        self.page_scroll.config(command=self.page_canvas.yview)
        self.page_canvas.config(yscrollcommand=self.page_scroll.set)
        self.page_scroll.pack(side="right", fill="y")
        self.page_canvas.pack(side="left", fill="both", expand=True)

        self.page = tk.Frame(self.page_canvas, bg=_BG)
        self._page_window = self.page_canvas.create_window(
            (0, 0),
            window=self.page,
            anchor="nw",
        )

        columns = tk.Frame(self.page, bg=_BG)
        columns.pack(fill="both", expand=True, padx=20, pady=(8, 4))
        columns.columnconfigure(0, weight=1, uniform="col")
        columns.columnconfigure(2, weight=1, uniform="col")
        columns.rowconfigure(0, weight=1)
        columns.rowconfigure(1, weight=1)

        left = tk.Frame(columns, bg=_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16), pady=8)
        rule = tk.Frame(columns, bg=_PURPLE, width=2)
        rule.grid(row=0, column=1, sticky="ns", pady=16)
        right = tk.Frame(columns, bg=_BG)
        right.grid(row=0, column=2, sticky="nsew", padx=(16, 0), pady=8)
        self._columns = columns
        self._left_col = left
        self._rule = rule
        self._right_col = right

        self._build_left(left)
        self._build_databank(right)
        self._build_ask(right)

        self.page.bind("<Configure>", self._sync_page_scroll)
        self.page_canvas.bind("<Configure>", self._on_page_canvas)
        left.bind("<Configure>", self._fit_left_wrap)
        right.bind("<Configure>", self._fit_right_wrap)
        try:
            self.root.bind("<Configure>", self._on_root_configure, add="+")
        except Exception:
            pass
        self._bind_app_wheel()
        self._stack_columns(int(self.root.winfo_width() or 1200))
        self._fit_footer(int(self.root.winfo_width() or 1200))

        self._refresh_list()
        pending = [item for item in self.engine.list_all() if item.status == "pending"]
        if pending:
            self.status.config(text="Holding the line. Pending reminder on disk.")
        self._hud = HudOverlay(self.tk, self.root, self.engine, self)

    def _build_top_bar(self) -> None:
        """STOP TALKING stays on screen. It is not inside the scroll body."""
        tk = self.tk
        bar = tk.Frame(self.root, bg=_BG)
        bar.pack(side="top", fill="x", padx=20, pady=(6, 0))
        self.stop_talk_btn = tk.Button(
            bar,
            text="STOP TALKING",
            font=("Arial", 14, "bold"),
            bg=_SCARLET,
            fg=_FG,
            activebackground="#E03A54",
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=self._stop_talking,
        )
        self.stop_talk_btn.pack(side="left", ipadx=12, ipady=6)
        self.stop_hotkey_line = tk.Label(
            bar,
            text=stop_hotkey_label(),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
            anchor="w",
        )
        self.stop_hotkey_line.pack(side="left", padx=(12, 0))

    def _build_left(self, parent: object) -> None:
        """Reminders stay on the left. ASK output never lands here."""
        tk = self.tk

        self.clear_all_btn = tk.Button(
            parent,
            text="CLEAR ALL",
            font=("Arial", 16, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._clear_all,
        )
        self.clear_all_btn.pack(side="bottom", fill="x", ipady=10, pady=(8, 4))

        tk.Label(
            parent,
            text="BATTLE BUDDY",
            font=_TITLE_FONT,
            fg=_GOLD,
            bg=_BG,
        ).pack(pady=(8, 0))

        tk.Label(
            parent,
            text="Speak it once. It holds the line.",
            font=_HINT_FONT,
            fg=_FG,
            bg=_BG,
        ).pack(pady=(4, 8))

        self.game_line = tk.Label(
            parent,
            text=status_line(None),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
            anchor="w",
        )
        self.game_line.pack(fill="x", pady=(0, 6))
        scan_row = tk.Frame(parent, bg=_BG)
        scan_row.pack(fill="x", pady=(0, 8))
        self.scan_btn = tk.Button(
            scan_row,
            text="SCAN",
            font=("Arial", 16, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._scan_now,
        )
        self.snap_btn = tk.Button(
            scan_row,
            text="SNAP",
            font=("Arial", 14, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._snap_monitor,
        )
        self.snap_box_btn = tk.Button(
            scan_row,
            text="SNAP BOX",
            font=("Arial", 14, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._snap_box,
        )
        for btn in (self.scan_btn, self.snap_btn, self.snap_box_btn):
            btn.config(padx=10, pady=8)
        self._bind_wrap_row(scan_row)
        self.seen_line = tk.Label(
            parent,
            text=seen_on_disk_line(self.catalog.list_games(), self.catalog.list_notes()),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
            anchor="w",
            wraplength=480,
            justify="left",
        )
        self.seen_line.pack(fill="x", pady=(4, 8))
        self.read_line = tk.Label(
            parent,
            text="Read This · Ctrl+1",
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
            anchor="w",
            wraplength=480,
            justify="left",
        )
        self.read_line.pack(fill="x", pady=(0, 6))

        self._field_caption(parent, "Reminder", "Lock a time reminder here")

        self.entry = self._make_entry(parent, size=20)
        self.entry.pack(fill="x", ipady=8, pady=(2, 8))
        self.entry.bind("<Return>", lambda _event: self._lock())
        self.entry.focus_set()

        actions = tk.Frame(parent, bg=_BG)
        actions.pack(fill="x", pady=(4, 8))
        speak_on = stt_available()
        self.lock_btn = tk.Button(
            actions,
            text="SUBMIT",
            font=("Arial", 22, "bold"),
            bg=_SCARLET,
            fg=_FG,
            activebackground="#E03A54",
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=self._lock,
        )
        if speak_on:
            self.speak_btn = tk.Button(
                actions,
                text="SPEAK",
                font=("Arial", 16, "bold"),
                bg=_BTN_DARK,
                fg=_GOLD,
                activebackground=_BTN_DARK_HI,
                activeforeground=_GOLD,
                relief="flat",
                cursor="hand2",
                command=self._speak,
            )
        else:
            self.speak_btn = None
        self.hygiene_btn = tk.Button(
            actions,
            text="HYGIENE",
            font=("Arial", 16, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._toggle_hygiene,
        )
        for btn in (self.lock_btn, self.speak_btn, self.hygiene_btn):
            if btn is None:
                continue
            btn.config(padx=10, pady=8)
        self._bind_wrap_row(actions)

        self.status = tk.Label(
            parent,
            text="One action. Lock a reminder. No account.",
            font=_BODY_FONT,
            fg=_FG,
            bg=_BG,
            anchor="w",
        )
        self.status.pack(fill="x", pady=(4, 8))

        list_frame = tk.Frame(parent, bg=_BG)
        list_frame.pack(fill="both", expand=True, pady=(8, 4))
        tk.Label(
            list_frame,
            text="Reminders",
            font=("Arial", 15, "bold"),
            fg=_GOLD,
            bg=_BG,
        ).pack(anchor="w", pady=(0, 6))
        self.list_canvas = tk.Canvas(
            list_frame,
            bg=_BG,
            highlightthickness=0,
            bd=0,
            height=120,
        )
        self.list_box = tk.Frame(self.list_canvas, bg=_BG)
        self._list_window = self.list_canvas.create_window(
            (0, 0),
            window=self.list_box,
            anchor="nw",
        )
        self.list_canvas.pack(fill="both", expand=True)
        self.list_box.bind(
            "<Configure>",
            lambda _event: self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")
            ),
        )
        self.list_canvas.bind("<Configure>", self._size_list_window)
        self.list_canvas.bind("<Button-4>", self._wheel)
        self.list_canvas.bind("<Button-5>", self._wheel)
        self.list_canvas.bind("<MouseWheel>", self._wheel)
        self._build_war_room(parent)

    def _build_war_room(self, parent: object) -> None:
        """Home-roster strip under the reminder list. Chips only. No walk-in."""
        tk = self.tk
        last = KnowledgeCatalog().last_roster()
        self._war_game = last[0] if last is not None else "Bellwright"
        self._war_kind = "place"
        self._session_tier = load_tier()
        self._roster_btns: dict[str, object] = {}
        self._kind_btns: dict[str, object] = {}
        self._tier_btns: dict[str, object] = {}

        strip = tk.Frame(parent, bg=_BG)
        strip.pack(side="bottom", fill="x", pady=(4, 0))

        roster = tk.Frame(strip, bg=_BG)
        roster.pack(fill="x", pady=(0, 4))
        # Home roster only: Star Citizen, Bellwright, Corsair Cove, ASKA, Clanfolk.
        for name in ROSTER_NAMES:
            btn = tk.Button(
                roster,
                text=name,
                font=("Arial", 12, "bold"),
                relief="flat",
                cursor="hand2",
                command=lambda n=name: self._select_war_game(n),
            )
            btn.config(padx=6, pady=4)
            self._roster_btns[name] = btn
        self._bind_wrap_row(roster, gap=4)

        tiers = tk.Frame(strip, bg=_BG)
        tiers.pack(fill="x", pady=(0, 4))
        for label, key in _TIER_CHIPS:
            btn = tk.Button(
                tiers,
                text=label,
                font=("Arial", 14, "bold"),
                relief="flat",
                cursor="hand2",
                command=lambda k=key: self._select_session_tier(k),
            )
            btn.config(padx=8, pady=4)
            self._tier_btns[key] = btn
        self._bind_wrap_row(tiers, gap=4)

        self.war_line = tk.Label(
            strip,
            text="",
            font=("Arial", 14, "bold"),
            fg=_FG,
            bg=_BG,
            anchor="w",
        )
        self.war_line.pack(fill="x", pady=(2, 4))

        kinds = tk.Frame(strip, bg=_BG)
        kinds.pack(fill="x", pady=(0, 4))
        for label, kind in _WAR_KINDS:
            btn = tk.Button(
                kinds,
                text=label,
                font=("Arial", 14, "bold"),
                relief="flat",
                cursor="hand2",
                command=lambda k=kind: self._select_war_kind(k),
            )
            btn.config(padx=8, pady=4)
            self._kind_btns[kind] = btn
        self._bind_wrap_row(kinds, gap=4)

        self._field_caption(strip, "Hold this")
        self.hold_entry = self._make_entry(strip, size=16)
        self.hold_entry.pack(fill="x", ipady=4, pady=(0, 4))
        self.hold_entry.bind("<Return>", lambda _event: self._war_room_hold())

        actions = tk.Frame(strip, bg=_BG)
        actions.pack(fill="x", pady=(0, 4))
        self.hold_btn = tk.Button(
            actions,
            text="HOLD",
            font=("Arial", 18, "bold"),
            bg=_SCARLET,
            fg=_FG,
            activebackground="#E03A54",
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=self._war_room_hold,
        )
        self.where_btn = tk.Button(
            actions,
            text="WHERE",
            font=("Arial", 18, "bold"),
            bg=_GOLD,
            fg=_BG,
            activebackground="#F0D78A",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._war_room_where,
        )
        self.next_btn = tk.Button(
            actions,
            text="NEXT",
            font=("Arial", 18, "bold"),
            bg=_GOLD,
            fg=_BG,
            activebackground="#F0D78A",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._war_room_next,
        )
        self.miss_btn = tk.Button(
            actions,
            text="MISS CHECK",
            font=("Arial", 18, "bold"),
            bg=_GOLD,
            fg=_BG,
            activebackground="#F0D78A",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._war_room_miss,
        )
        for btn in (self.hold_btn, self.where_btn, self.next_btn, self.miss_btn):
            btn.config(padx=10, pady=6)
        self._bind_wrap_row(actions)

        self.war_room_out = tk.Text(
            strip,
            height=5,
            font=("Arial", 13),
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_GOLD,
            relief="flat",
            wrap="word",
            highlightthickness=1,
            highlightbackground=_EDGE,
            state="disabled",
        )
        self.war_room_out.pack(fill="x", pady=(4, 6))
        self._paint_war_chips()
        self._refresh_war_line()

    def _paint_war_chips(self) -> None:
        for name, btn in self._roster_btns.items():
            selected = name == self._war_game
            btn.config(
                bg=_GOLD if selected else _BTN_DARK,
                fg=_BG if selected else _FG,
                activebackground=_GOLD if selected else _BTN_DARK_HI,
                activeforeground=_BG if selected else _FG,
            )
        for kind, btn in self._kind_btns.items():
            selected = kind == self._war_kind
            btn.config(
                bg=_GOLD if selected else _BTN_DARK,
                fg=_BG if selected else _FG,
                activebackground=_GOLD if selected else _BTN_DARK_HI,
                activeforeground=_BG if selected else _FG,
            )
        for key, btn in self._tier_btns.items():
            selected = key == self._session_tier
            btn.config(
                bg=_GOLD if selected else _BTN_DARK,
                fg=_BG if selected else _FG,
                activebackground=_GOLD if selected else _BTN_DARK_HI,
                activeforeground=_BG if selected else _FG,
            )

    def _select_session_tier(self, key: str) -> None:
        self._session_tier = save_tier(key)
        self._paint_war_chips()
        self._refresh_war_line()

    def _select_war_game(self, name: str) -> None:
        self._war_game = name
        self._paint_war_chips()
        self._refresh_war_line()

    def _select_war_kind(self, kind: str) -> None:
        self._war_kind = kind
        self._paint_war_chips()

    def _refresh_war_line(self) -> None:
        self._session_tier = load_tier()
        self._paint_war_chips()
        name = self._war_game
        row = KnowledgeCatalog().war_room_row(game_slug(name))
        help_label = TIER_LABELS.get(self._session_tier, TIER_LABELS[TIER_GENTLE])
        if row is None:
            text = f"{name} · War Room empty. · {help_label}"
        else:
            text = (
                f"{war_room_oneliner(name, row.get('place'), row.get('patch'))}"
                f" · {help_label}"
            )
        snap = load_harvest()
        if name == "Corsair Cove" and snap is not None:
            state = "live" if snap.live else "dark"
            text = f"{text} · {state} · harvest"
        text = f"{text} · brain {load_brain()}"
        self.war_line.config(text=text)

    def _set_war_room_out(self, text: str) -> None:
        pane = getattr(self, "war_room_out", None)
        if pane is None:
            return
        shown = (text or "").rstrip()
        skip_say = (
            shown == "Hold a place first."
            or shown.startswith("Newest shot:")
            or shown in {"No screenshot.", "Wait. Vision is cooling."}
            or ("?" in shown and "One move:" not in shown and "Action:" not in shown)
        )
        if shown and _SAY_WRONG not in shown and not skip_say:
            shown = f"{shown}\n{_SAY_WRONG}"
        try:
            pane.config(state="normal")
            pane.delete("1.0", "end")
            if shown:
                pane.insert("1.0", shown)
            pane.config(state="disabled")
        except Exception:
            return

    def _war_room_hold(self) -> None:
        text = self.hold_entry.get().strip()
        if not text:
            self._set_war_room_out("Hold this is empty.")
            return
        line = f"remember {self._war_kind} for {self._war_game}: {text}"
        result = run_line(self.engine, line)
        self._set_war_room_out(result.message)
        if result.ok:
            try:
                self.hold_entry.delete(0, "end")
            except Exception:
                pass
        self._refresh_war_line()

    def _war_room_where(self) -> None:
        result = run_line(self.engine, f"where was I in {self._war_game}")
        self._set_war_room_out(result.message)
        self._refresh_war_line()

    def _speak_war(self, result: object) -> None:
        phrase = spoken_line(getattr(result, "speak", "") or getattr(result, "message", "") or "")
        if phrase:
            speak_async(phrase)

    def _heard_coach_or_miss(self, heard: str) -> bool:
        if is_miss_command(heard):
            return True
        parsed = parse_war_room_line(heard)
        return parsed is not None and parsed.action == "coach"

    def _war_room_next(self) -> None:
        result = run_line(self.engine, f"next {self._war_game}")
        self._set_war_room_out(result.message)
        self._speak_war(result)
        self._refresh_war_line()

    def _war_room_miss(self) -> None:
        result = run_line(self.engine, "miss check")
        self._set_war_room_out(result.message)
        self._speak_war(result)
        self._refresh_war_line()

    def _field_caption(
        self, parent: object, title: str, hint: str = "", *, padx: int = 0
    ) -> None:
        """Large high-contrast name above a box. Hint stays outside the entry."""
        tk = self.tk
        row = tk.Frame(parent, bg=_BG)
        pack = {"fill": "x", "pady": (6, 4)}
        if padx:
            pack["padx"] = padx
        row.pack(**pack)
        tk.Label(
            row,
            text=title,
            font=("Arial", 16, "bold"),
            fg=_GOLD,
            bg=_BG,
            anchor="w",
        ).pack(side="left")
        if not hint:
            return
        tk.Label(
            row,
            text=hint,
            font=_HINT_FONT,
            fg=_MUTED,
            bg=_BG,
            anchor="w",
        ).pack(side="left", padx=(12, 0))

    def _make_entry(self, parent: object, size: int = 18) -> object:
        """Gold caret, purple focus ring only. No orange chrome."""
        return self.tk.Entry(
            parent,
            font=("Arial", size),
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_GOLD,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_EDGE,
            highlightcolor=_PURPLE,
        )

    def _build_databank(self, parent: object) -> None:
        """One box: wiki URL or game question. Fetch or ASK. No chat."""
        tk = self.tk
        box = tk.Frame(parent, bg=_BG)
        box.pack(fill="x", pady=(8, 8))

        self.databank_header = tk.Label(
            box,
            text=databank_label(self._game_name),
            font=("Arial", 15, "bold"),
            fg=_GOLD,
            bg=_BG,
            anchor="w",
        )
        self.databank_header.pack(fill="x", pady=(2, 4))

        self._field_caption(box, "Wiki or question", _QUERY_HINT)

        read_row = tk.Frame(box, bg=_BG)
        read_row.pack(fill="x", pady=(0, 6))
        self.read_btn = tk.Button(
            read_row,
            text="READ THIS",
            font=("Arial", 14, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._read_this,
        )
        self.read_again_btn = tk.Button(
            read_row,
            text="READ AGAIN",
            font=("Arial", 14, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._read_again,
        )
        self.repeat_btn = tk.Button(
            read_row,
            text="REPEAT LAST",
            font=("Arial", 14, "bold"),
            bg=_BTN_DARK,
            fg=_GOLD,
            activebackground=_BTN_DARK_HI,
            activeforeground=_GOLD,
            relief="flat",
            cursor="hand2",
            command=self._repeat_last,
        )
        for btn in (self.read_btn, self.read_again_btn, self.repeat_btn):
            btn.config(padx=10, pady=8)
        self._bind_wrap_row(read_row)

        query_row = tk.Frame(box, bg=_BG)
        query_row.pack(fill="x", pady=(0, 6))
        self.ask_entry = self._make_entry(query_row, size=18)
        self.url_entry = self.ask_entry
        self.ask_entry.pack(fill="x", ipady=10, pady=(0, 6))
        self.ask_entry.bind("<Return>", lambda _event: self._submit_query())
        ask_row = tk.Frame(box, bg=_BG)
        ask_row.pack(fill="x", pady=(0, 6))
        self.query_btn = tk.Button(
            ask_row,
            text="Submit",
            font=("Arial", 16, "bold"),
            bg=_SCARLET,
            fg=_FG,
            activebackground="#E03A54",
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=self._submit_query,
        )
        self.query_btn.config(padx=12, pady=8)
        self._bind_wrap_row(ask_row)
        self.fetch_btn = self.query_btn
        self.ask_btn = self.query_btn

        self.databank_status = tk.Label(
            box,
            text="Public http(s) URL fetches a page. Anything else is ASK. No account.",
            font=_HINT_FONT,
            fg=_MUTED,
            bg=_BG,
            anchor="w",
            wraplength=520,
            justify="left",
        )
        self.databank_status.pack(fill="x", pady=(0, 8))

        self.source_box = tk.Frame(box, bg=_BG)
        self.source_box.pack(fill="x", expand=False)
        self.source_count = tk.Label(
            self.source_box,
            text=sources_count_line(self._game_name, 0),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
            anchor="w",
        )
        self.source_count.pack(fill="x", pady=4)
        self._refresh_sources()

    def _build_ask(self, parent: object) -> None:
        """ASK answer pane takes remaining right-column height. No wiki dump."""
        tk = self.tk
        box = tk.Frame(parent, bg=_BG)
        box.pack(fill="both", expand=True, pady=(8, 4))

        pane = tk.Frame(box, bg=_INPUT_BG, height=220)
        pane.pack(fill="both", expand=True, pady=(0, 4))
        pane.pack_propagate(False)
        self.ask_pane = pane
        self.ask_out = tk.Text(
            pane,
            font=_HINT_FONT,
            bg=_INPUT_BG,
            fg=_FG,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_EDGE,
            highlightcolor=_PURPLE,
            wrap="word",
            height=8,
            state="disabled",
            cursor="arrow",
        )
        scroll = tk.Scrollbar(pane, command=self.ask_out.yview)
        self.ask_out.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.ask_out.pack(side="left", fill="both", expand=True)

    def _submit_query(self) -> None:
        """URL → fetch. Anything else → ASK. One field, one Submit."""
        text = str(self.ask_entry.get()).strip()
        if looks_like_public_url(text):
            self._add_fetch()
            return
        self._ask()

    def _add_fetch(self) -> None:
        if self._fetching:
            return
        url = str(self.url_entry.get()).strip()
        if not url or url in {"http://", "https://"}:
            self.databank_status.config(text="Paste a public http or https URL.")
            return
        self._fetching = True
        self.fetch_btn.config(state="disabled", text="Fetching")
        self.databank_status.config(text="Fetching. Public GET only.")
        game = self._game_name
        threading.Thread(target=self._fetch_worker, args=(url, game), daemon=True).start()

    def _fetch_worker(self, url: str, game: str | None) -> None:
        try:
            result = self.databank.add_url(game, url)
        except Exception:
            result = None
        try:
            self.root.after(0, lambda r=result, g=game: self._fetch_done(r, g))
        except Exception:
            self._fetching = False

    def _fetch_done(self, result: object, game: str | None) -> None:
        self._fetching = False
        try:
            self.fetch_btn.config(state="normal", text="Submit")
        except Exception:
            pass
        if result is None:
            self.databank_status.config(text="Fetch failed.")
            return
        ok = bool(getattr(result, "ok", False))
        message = str(getattr(result, "message", "Fetch failed."))
        title = str(getattr(result, "title", "")).strip()
        if ok:
            label = title or "page"
            slug = game_slug(game)
            self.databank_status.config(text=f"Saved. {label} → {slug}.")
            try:
                self.url_entry.delete(0, "end")
            except Exception:
                pass
        else:
            self.databank_status.config(text=message)
        self._refresh_sources()

    def _refresh_seen(self) -> None:
        label = getattr(self, "seen_line", None)
        if label is None:
            return
        try:
            label.config(
                text=seen_on_disk_line(self.catalog.list_games(), self.catalog.list_notes())
            )
        except Exception:
            return

    def _refresh_sources(self) -> None:
        self._refresh_seen()
        try:
            self.databank_header.config(text=databank_label(self._game_name))
        except Exception:
            pass
        sources = self.databank.list_sources(self._game_name)
        line = sources_count_line(self._game_name, len(sources))
        label = getattr(self, "source_count", None)
        if label is None:
            return
        try:
            label.config(text=line)
        except Exception:
            return

    def _ask(self) -> None:
        """Local retrieve first. Hunt the game wiki in the background on a miss."""
        if self._asking:
            return
        question = str(self.ask_entry.get()).strip()
        result = ask_pages(self.databank, self._game_name, question)
        if not should_hunt(self.databank, self._game_name, question, result):
            ranked = rank_ask_result(result, question)
            self._show_ask(answer_ask(ranked, question, self.databank, self._game_name))
            if result.ok:
                self._clear_ask_box()
            return
        self._asking = True
        try:
            self.ask_btn.config(state="disabled")
        except Exception:
            pass
        self._show_ask("Looking on the wiki.")
        if result.ok:
            self._clear_ask_box()
        game = self._game_name
        threading.Thread(
            target=self._ask_hunt_worker,
            args=(question, game, result),
            daemon=True,
        ).start()

    def _ask_hunt_worker(
        self,
        question: str,
        game: str | None,
        local: object,
    ) -> None:
        result, shown = hunt_or_keep_local(self.databank, game, question, local)
        try:
            self.root.after(0, lambda r=result, s=shown: self._ask_hunt_done(r, s))
        except Exception:
            self._asking = False

    def _ask_hunt_done(self, result: object, shown: str | None = None) -> None:
        self._asking = False
        try:
            self.ask_btn.config(state="normal")
        except Exception:
            pass
        if shown:
            self._show_ask(shown)
        elif result is not None:
            self._show_ask(ask_visible_message(result))
        else:
            self._show_ask(shown_after_hunt_failure(None))
        self._refresh_sources()

    def _clear_ask_box(self) -> None:
        try:
            self.ask_entry.delete(0, "end")
            self.ask_entry.focus_set()
        except Exception:
            pass

    def _show_ask(self, text: str) -> None:
        """Write the ASK result on the right pane only."""
        shown = (text or "").strip()
        self._set_ask_out(shown)

    def _set_ask_out(self, text: str) -> None:
        pane = getattr(self, "ask_out", None)
        if pane is None:
            return
        try:
            pane.config(state="normal")
            pane.delete("1.0", "end")
            if text:
                pane.insert("1.0", text)
            pane.config(state="disabled")
        except Exception:
            return

    def _size_list_window(self, event: object) -> None:
        width = int(getattr(event, "width", 0) or 0)
        if width:
            self.list_canvas.itemconfigure(self._list_window, width=width)

    def _on_page_canvas(self, event: object) -> None:
        self._size_page_window(event)
        try:
            width = int(self.root.winfo_width() or 0)
        except Exception:
            width = int(getattr(event, "width", 0) or 0)
        self._stack_columns(width)
        self._fit_footer(width)

    def _on_root_configure(self, event: object) -> None:
        widget = getattr(event, "widget", None)
        if widget is not None and widget is not self.root:
            return
        width = int(getattr(event, "width", 0) or 0)
        self._stack_columns(width)
        self._fit_footer(width)

    def _fit_footer(self, width: int) -> None:
        label = getattr(self, "voice_footer", None)
        if label is None or width < 80:
            return
        try:
            label.config(wraplength=max(width - 48, 80))
        except Exception:
            return

    def _stack_columns(self, width: int) -> None:
        if width <= 1:
            return
        stacked = columns_stacked(width, limit=STACK_COLUMNS_BELOW)
        if stacked == self._columns_stacked:
            return
        self._columns_stacked = stacked
        columns = getattr(self, "_columns", None)
        left = getattr(self, "_left_col", None)
        right = getattr(self, "_right_col", None)
        rule = getattr(self, "_rule", None)
        if columns is None or left is None or right is None or rule is None:
            return
        try:
            if stacked:
                columns.columnconfigure(0, weight=1, uniform="")
                columns.columnconfigure(1, weight=0, uniform="")
                columns.columnconfigure(2, weight=0, uniform="")
                columns.rowconfigure(0, weight=1)
                columns.rowconfigure(1, weight=1)
                rule.grid_remove()
                left.grid(
                    row=0,
                    column=0,
                    columnspan=3,
                    sticky="nsew",
                    padx=0,
                    pady=(8, 4),
                )
                right.grid(
                    row=1,
                    column=0,
                    columnspan=3,
                    sticky="nsew",
                    padx=0,
                    pady=(4, 8),
                )
            else:
                columns.columnconfigure(0, weight=1, uniform="col")
                columns.columnconfigure(1, weight=0, uniform="")
                columns.columnconfigure(2, weight=1, uniform="col")
                columns.rowconfigure(0, weight=1)
                columns.rowconfigure(1, weight=0)
                left.grid(
                    row=0,
                    column=0,
                    columnspan=1,
                    sticky="nsew",
                    padx=(0, 16),
                    pady=8,
                )
                rule.grid(row=0, column=1, sticky="ns", pady=16)
                right.grid(
                    row=0,
                    column=2,
                    columnspan=1,
                    sticky="nsew",
                    padx=(16, 0),
                    pady=8,
                )
        except Exception:
            self._columns_stacked = None
            return
        self._sync_page_scroll()

    def _size_page_window(self, event: object) -> None:
        width = int(getattr(event, "width", 0) or 0)
        height = int(getattr(event, "height", 0) or 0)
        if width:
            self.page_canvas.itemconfigure(self._page_window, width=width)
        try:
            self.page.update_idletasks()
            need = int(self.page.winfo_reqheight() or 0)
        except Exception:
            need = 0
        if height <= 0:
            self._sync_page_scroll()
            return
        # The page is never shorter than its content, so the scrollbar reaches every
        # control (side-by-side too, e.g. the default 1200x800 window). When the
        # content is shorter than the viewport the two columns still fill it.
        inner = max(need, height)
        self.page_canvas.itemconfigure(self._page_window, height=inner)
        self._sync_page_scroll()

    def _sync_page_scroll(self, _event: object | None = None) -> None:
        canvas = getattr(self, "page_canvas", None)
        if canvas is None:
            return
        try:
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
        except Exception:
            return
        if bbox:
            canvas.configure(scrollregion=bbox)

    def _bind_wrap_row(self, row: object, gap: int = 8) -> None:
        try:
            row.pack_propagate(False)
        except Exception:
            pass

        def relayout(_event: object | None = None) -> None:
            self._layout_wrap_row(row, gap)

        try:
            row.bind("<Configure>", relayout)
        except Exception:
            pass
        try:
            row.after_idle(relayout)
        except Exception:
            relayout()

    def _layout_wrap_row(self, row: object, gap: int = 8) -> None:
        marker = id(row)
        if marker in self._wrap_busy:
            return
        try:
            kids = list(row.winfo_children())
        except Exception:
            return
        if not kids:
            return
        self._wrap_busy.add(marker)
        try:
            widths = [max(int(child.winfo_reqwidth()), 1) for child in kids]
            heights = [max(int(child.winfo_reqheight()), 1) for child in kids]
            row_h = max(heights) + 4
            max_w = max(int(row.winfo_width()), 1)
            positions, total = wrap_positions(
                widths, max_w, gap=gap, row_height=row_h
            )
            for child, (x, y) in zip(kids, positions):
                child.place(x=x, y=y)
            total = max(total, row_h)
            try:
                current = int(row.cget("height") or 0)
            except Exception:
                current = 0
            if current != total:
                row.configure(height=total)
        except Exception:
            return
        finally:
            self._wrap_busy.discard(marker)

    def _fit_left_wrap(self, event: object) -> None:
        self._fit_wrap_labels(
            event,
            getattr(self, "seen_line", None),
            getattr(self, "read_line", None),
        )

    def _fit_right_wrap(self, event: object) -> None:
        self._fit_wrap_labels(event, getattr(self, "databank_status", None))

    def _fit_wrap_labels(self, event: object, *labels: object) -> None:
        width = int(getattr(event, "width", 0) or 0)
        if width < 80:
            return
        wrap = max(width - 8, 80)
        for label in labels:
            if label is None:
                continue
            try:
                label.config(wraplength=wrap)
            except Exception:
                continue

    def _bind_app_wheel(self) -> None:
        """Windows sends wheel to the focused window. bind_all, not overlay grabs."""
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.root.bind_all(seq, self._wheel, add="+")
            except Exception:
                continue
            try:
                self.page_canvas.bind(seq, self._wheel)
            except Exception:
                continue

    def _widget_under_wheel(self, event: object) -> object | None:
        try:
            x = int(getattr(event, "x_root", 0) or 0)
            y = int(getattr(event, "y_root", 0) or 0)
            found = self.root.winfo_containing(x, y)
            if found is not None:
                return found
        except Exception:
            pass
        return getattr(event, "widget", None)

    def _scroll_target(self, event: object) -> object | None:
        ask = getattr(self, "ask_out", None)
        list_c = getattr(self, "list_canvas", None)
        list_box = getattr(self, "list_box", None)
        page_c = getattr(self, "page_canvas", None)
        node: object | None = self._widget_under_wheel(event)
        while node is not None:
            if ask is not None and node is ask:
                return None
            if list_c is not None and (node is list_c or node is list_box):
                return list_c
            if page_c is not None and node is page_c:
                return page_c
            node = getattr(node, "master", None)
        return page_c

    def _wheel(self, event: object) -> str | None:
        target = self._scroll_target(event)
        if target is None:
            return None
        step = wheel_units(
            getattr(event, "delta", 0),
            getattr(event, "num", None),
        )
        if step == 0:
            return None
        try:
            target.yview_scroll(step, "units")
        except Exception:
            return None
        return "break"

    def _lock(self) -> None:
        line = self.entry.get().strip()
        if is_clear_all(line):
            self._clear_all()
            return
        decided = reason_utterance(
            line, store=self.databank, game=self._game_name
        )
        if decided.kind == "command":
            if is_clear_all(decided.line):
                self._clear_all()
                return
            result = run_line(self.engine, decided.line)
        elif decided.kind == "ask" and decided.result is not None:
            result = decided.result
        else:
            result = decided.result or run_line(self.engine, line)
        if result.kind in {"note", "notes", "games"}:
            self._wipe_armed = False
            self.clear_all_btn.config(text="CLEAR ALL")
            self.status.config(text=result.message.split("\n", 1)[0])
            if result.ok:
                self.entry.delete(0, "end")
                self.entry.focus_set()
            if result.speak:
                speak_async(result.speak)
            self._refresh_seen()
            self._refresh_list()
            return
        if result.kind == "ask":
            self._wipe_armed = False
            self.clear_all_btn.config(text="CLEAR ALL")
            self._show_ask(result.message)
            self.status.config(text="Ask. Saved pages only.")
            if result.ok:
                self.entry.delete(0, "end")
                self.entry.focus_set()
            if result.speak:
                speak_async(result.speak)
            self._refresh_list()
            return
        if not result.ok:
            if result.kind == "unknown":
                self.status.config(text=f"Could not parse that. Try: {_EXAMPLE}")
                return
            self.status.config(text=result.message)
            if result.speak:
                speak_async(result.speak)
            self._refresh_list()
            return
        self._wipe_armed = False
        self.clear_all_btn.config(text="CLEAR ALL")
        if result.kind in {"remind", "hygiene_start"} and result.reminder is not None:
            due = _local_stamp(result.reminder.due_at)
            self.status.config(text=f"{result.message}  Due {due}.")
            self.entry.delete(0, "end")
            self.entry.focus_set()
        else:
            self.status.config(text=result.message)
            if result.kind in {"hygiene_stop"}:
                self.entry.delete(0, "end")
                self.entry.focus_set()
        if result.speak:
            speak_async(result.speak)
        self._refresh_list()

    def _toggle_hygiene(self) -> None:
        """One gold control. Start the 15/5 loop, or stop it."""
        line = "stop hygiene" if hygiene_is_active(self.engine) else "start hygiene"
        result = run_line(self.engine, line)
        self._wipe_armed = False
        self.clear_all_btn.config(text="CLEAR ALL")
        if result.kind == "hygiene_start" and result.reminder is not None:
            due = _local_stamp(result.reminder.due_at)
            self.status.config(text=f"{result.message}  Due {due}.")
        else:
            self.status.config(text=result.message)
        if result.speak:
            speak_async(result.speak)
        self._refresh_list()

    def _speak(self) -> None:
        if self._listening or self.speak_btn is None:
            return
        self._listening = True
        self.speak_btn.config(state="disabled", text="LISTENING")
        self.status.config(text="Listening. Local only. No cloud.")
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self) -> None:
        heard = listen_once()
        self.root.after(0, lambda h=heard: self._listen_done(h))

    def _listen_done(self, heard: str | None) -> None:
        self._listening = False
        if self.speak_btn is not None:
            self.speak_btn.config(state="normal", text="SPEAK")
        if not heard:
            self.status.config(text="Heard nothing. Type it. Typed fallback is live.")
            return
        if self._heard_coach_or_miss(heard):
            result = run_line(self.engine, heard)
            self._set_war_room_out(result.message)
            self._speak_war(result)
            self._refresh_war_line()
            self.status.config(text=result.message.split("\n")[0][:80])
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, heard)
        self._lock()

    def _refresh_list(self) -> None:
        self._clocks = {}
        for child in self.list_box.winfo_children():
            child.destroy()
        tk = self.tk
        reminders = [
            item
            for item in self.engine.list_all()
            if item.status != "cancelled"
        ]
        reminders.sort(
            key=lambda item: (
                0 if item.id in self._firing else
                1 if item.status == STATUS_PENDING else
                2
            )
        )
        if not reminders:
            tk.Label(
                self.list_box,
                text="No reminders on disk.",
                font=_BODY_FONT,
                fg=_MUTED,
                bg=_BG,
                anchor="w",
            ).pack(fill="x", pady=12)
            self._sync_hygiene_btn()
            return
        for item in reminders:
            self._add_row(item)
        self._bind_wheel(self.list_box)
        self._emit_minute_warns()
        self._sync_hygiene_btn()

    def _sync_hygiene_btn(self) -> None:
        btn = getattr(self, "hygiene_btn", None)
        if btn is None:
            return
        live = False
        try:
            live = hygiene_is_active(self.engine)
        except Exception:
            live = False
        label = "STOP HYGIENE" if live else "HYGIENE"
        try:
            if str(btn.cget("text")) != label:
                btn.config(text=label)
        except Exception:
            return

    def _bind_wheel(self, widget: object) -> None:
        if widget is getattr(self, "ask_out", None):
            return
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            widget.bind(seq, self._wheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _add_row(self, item: Reminder) -> None:
        tk = self.tk
        firing = item.id in self._firing
        selected = item.id == self._selected_id and not firing
        if firing:
            card_bg = _SCARLET
            card_fg = _GOLD
            clock_fg = _GOLD
            edge = _GOLD
        else:
            card_bg = _CARD
            card_fg = _FG
            clock_fg = _GOLD if item.status == STATUS_PENDING else _MUTED
            edge = _PURPLE if selected else _EDGE
        row = tk.Frame(
            self.list_box,
            bg=card_bg,
            highlightthickness=2,
            highlightbackground=edge,
        )
        row.pack(fill="x", pady=10)
        row.bind("<Button-1>", lambda _event, i=item: self._select_row(i.id))
        if firing:
            tk.Label(
                row,
                text="FIRE",
                font=("Arial", 18, "bold"),
                fg=_GOLD,
                bg=card_bg,
                anchor="w",
            ).pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(
            row,
            text=item.text,
            font=_BODY_FONT,
            fg=card_fg,
            bg=card_bg,
            wraplength=480,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12 if not firing else 4, 2))
        pending = item.status == STATUS_PENDING
        clock = tk.Label(
            row,
            text=row_clock_text(item.status, item.due_at),
            font=_CLOCK_FONT,
            fg=clock_fg,
            bg=card_bg,
            anchor="w",
        )
        clock.pack(fill="x", padx=14, pady=(0, 6))
        clock.bind("<Button-1>", lambda _event, i=item: self._select_row(i.id))
        if pending:
            self._clocks[item.id] = (clock, item.due_at)
        btns = tk.Frame(row, bg=card_bg)
        btns.pack(fill="x", padx=14, pady=(0, 12))
        if firing:
            tk.Button(
                btns,
                text="SEEN",
                font=("Arial", 16, "bold"),
                bg=_GOLD,
                fg=_BG,
                activebackground="#F0D67A",
                activeforeground=_BG,
                relief="flat",
                cursor="hand2",
                command=lambda i=item: self._seen_item(i),
            ).pack(side="left", expand=True, fill="x", ipady=12, padx=(0, 8))
        tk.Button(
            btns,
            text="SNOOZE 5 MIN",
            font=("Arial", 16, "bold"),
            bg=_GOLD if not firing else _BTN_DARK,
            fg=_BG if not firing else _GOLD,
            activebackground="#F0D67A" if not firing else _BTN_DARK_HI,
            activeforeground=_BG if not firing else _GOLD,
            relief="flat",
            cursor="hand2",
            command=lambda i=item: self._snooze_item(i),
        ).pack(side="left", expand=True, fill="x", ipady=12, padx=(0, 8))
        tk.Button(
            btns,
            text="CLEAR",
            font=("Arial", 16, "bold"),
            bg=_BTN_DARK,
            fg=_FG,
            activebackground=_BTN_DARK_HI,
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=lambda i=item: self._clear_item(i),
        ).pack(side="left", expand=True, fill="x", ipady=12)

    def _select_row(self, reminder_id: str) -> None:
        self._selected_id = reminder_id
        self._refresh_list()

    def _snooze_item(self, item: Reminder) -> None:
        self._firing.discard(item.id)
        result = run_line(self.engine, f"snooze {item.id} 5 minutes")
        self.status.config(text=result.message)
        if result.speak:
            speak_async(result.speak)
        self._wipe_armed = False
        self.clear_all_btn.config(text="CLEAR ALL")
        self._refresh_list()

    def _clear_item(self, item: Reminder) -> None:
        self._firing.discard(item.id)
        result = run_line(self.engine, f"clear {item.id}")
        self.status.config(text=result.message)
        if result.speak:
            speak_async(result.speak)
        self._wipe_armed = False
        self.clear_all_btn.config(text="CLEAR ALL")
        self._refresh_list()

    def _seen_item(self, item: Reminder) -> None:
        """Dismiss FIRE on this card only. Reminder stays on disk."""
        self._firing.discard(item.id)
        if not self._firing:
            self._fire_up = False
            try:
                self.root.attributes("-topmost", False)
            except Exception:
                pass
        self.status.config(text="Fire seen. Lock another when you need it.")
        self._refresh_list()

    def _clear_all(self) -> None:
        if not self._wipe_armed:
            self._wipe_armed = True
            self.clear_all_btn.config(text="CONFIRM WIPE")
            self.status.config(text="Confirm once. Hit CONFIRM WIPE to clear all.")
            return
        result = run_line(self.engine, "clear all")
        self._wipe_armed = False
        self._firing.clear()
        self._fire_up = False
        self.clear_all_btn.config(text="CLEAR ALL")
        self.status.config(text=result.message)
        if result.speak:
            speak_async(result.speak)
        self._refresh_list()

    def _tick(self) -> None:
        self._emit_minute_warns()
        try:
            fired = self.engine.fire_due()
        except Exception:
            fired = []
        for item in fired:
            self._on_fire(item)
        if fired:
            self._refresh_list()
        else:
            self._tick_clocks()
        self._maybe_scan_game()
        self._maybe_unsolicited_miss()
        try:
            self.root.after(_POLL_MS, self._tick)
        except Exception:
            return

    def _read_status(self, text: str) -> None:
        """Read This feedback. Reminder FIRE status stays on its own label."""

        def _apply() -> None:
            try:
                self.read_line.config(text=text)
            except Exception:
                return

        try:
            self.root.after(0, _apply)
        except Exception:
            return

    def _read_saved(self) -> None:
        try:
            self.root.after(0, self._refresh_seen)
        except Exception:
            return

    def _snap_monitor(self) -> None:
        self.snap.snap_monitor()

    def _snap_box(self) -> None:
        self.snap.snap_box()

    def _read_this(self) -> None:
        self.reader.start_select()

    def _read_again(self) -> None:
        self.reader.read_again()

    def _repeat_last(self) -> None:
        self.reader.repeat_last()

    def _start_stop_hotkey(self) -> None:
        if self._stop_listener is not None:
            return
        listener = HotkeyListener(
            load_stop_hotkey(),
            self._on_stop_hotkey,
            name="battlebuddy-stop-hotkey",
            taken_hint="BATTLEBUDDY_STOP_HOTKEY or stop_hotkey in session.json",
            need_windows="Global hotkey needs Windows. Use the STOP TALKING button.",
            hotkey_id=STOP_HOTKEY_ID,
        )
        self._stop_listener = listener
        error = listener.start()
        if error:
            try:
                self._read_status(error)
            except Exception:
                pass

    def _on_stop_hotkey(self) -> None:
        try:
            self.root.after(0, self._stop_talking)
        except Exception:
            self._stop_talking()

    def _stop_talking(self) -> None:
        """Kill any local TTS and undim an active box. Safe when idle."""
        try:
            self.reader.stop_talking()
        except Exception:
            pass
        try:
            self.snap.stop_talking()
        except Exception:
            pass
        stop_speaking()

    def _scan_now(self) -> None:
        """Immediate rescan. Ignores the 5s poll throttle. Fire stays live."""
        try:
            self.game_line.config(text="Scanning.")
        except Exception:
            pass
        self._start_game_scan(prefer_switch=True)

    def _maybe_unsolicited_miss(self) -> None:
        """Cove live only. Five-minute cap. Never blocks FIRE."""
        if self._miss_busy:
            return
        if getattr(self, "_war_game", None) != "Corsair Cove":
            return
        snap = load_harvest()
        if snap is None or not snap.live:
            return
        self._miss_busy = True
        threading.Thread(target=self._unsolicited_miss_worker, daemon=True).start()

    def _unsolicited_miss_worker(self) -> None:
        try:
            found = miss_check(
                unsolicited=True,
                key=api_key(),
            )
        except Exception:
            found = None
        try:
            self.root.after(0, lambda: self._apply_unsolicited_miss(found))
        except Exception:
            self._miss_busy = False

    def _apply_unsolicited_miss(self, found: object) -> None:
        self._miss_busy = False
        message = getattr(found, "message", "") if found is not None else ""
        skipped = bool(getattr(found, "skipped", True)) if found is not None else True
        if skipped or not message:
            return
        self._set_war_room_out(str(message))

    def _maybe_scan_game(self) -> None:
        """Refresh the quiet game line. Never blocks fire or countdown."""
        self._detect_ticks += 1
        if self._detect_ticks != 1 and self._detect_ticks % _DETECT_EVERY != 0:
            return
        self._start_game_scan(prefer_switch=False)

    def _start_game_scan(self, prefer_switch: bool) -> None:
        if self._game_busy and not prefer_switch:
            return
        self._game_busy = True
        current = self._game_name
        threading.Thread(
            target=self._scan_game_worker,
            args=(prefer_switch, current),
            daemon=True,
        ).start()

    def _scan_game_worker(self, prefer_switch: bool = False, current: str | None = None) -> None:
        try:
            skip = current if prefer_switch else None
            name = detect_game(prefer_other=skip)
        except Exception:
            name = None
        try:
            self.root.after(0, lambda n=name: self._apply_game(n))
        except Exception:
            self._game_busy = False

    def _apply_game(self, name: str | None) -> None:
        self._game_busy = False
        text = status_line(name)
        try:
            if str(self.game_line.cget("text")) != text:
                self.game_line.config(text=text)
        except Exception:
            return
        if not is_named_game(name):
            return
        self.catalog.remember_game(name, source="scan")
        self._refresh_seen()
        old = self._game_name
        if not is_named_game(old):
            self._game_name = name
            self._refresh_sources()
            self._maybe_seed_wiki(name)
            return
        if game_slug(old) == game_slug(name):
            self._game_name = name
            self._maybe_seed_wiki(name)
            return
        self._game_name = name
        self._refresh_sources()
        if self._maybe_seed_wiki(name):
            return
        notice = switched_databank_line(name)
        self._show_ask(notice)
        try:
            self.databank_status.config(text=notice)
        except Exception:
            pass

    def _maybe_seed_wiki(self, game: str | None) -> bool:
        """Empty new-game folder: hold the line and fetch wikis. Reminders stay live."""
        if not needs_wiki_seed(self.databank, game):
            return False
        slug = game_slug(game)
        if slug in self._seed_started:
            return False
        self._seed_started.add(slug)
        note = f"Hold the line. Fetching wiki pages for {game}. Give it a few minutes."
        self._show_ask(note)
        try:
            self.databank_status.config(text=note)
        except Exception:
            pass
        self._start_wiki_seed(game)
        return True

    def _start_wiki_seed(self, game: str | None) -> None:
        threading.Thread(target=self._seed_worker, args=(game,), daemon=True).start()

    def _seed_worker(self, game: str | None) -> None:
        try:
            result = seed_new_game(self.databank, game)
        except Exception:
            result = None
        try:
            self.root.after(0, lambda r=result, g=game: self._seed_done(r, g))
        except Exception:
            return

    def _seed_done(self, result: object, game: str | None) -> None:
        saved = 0
        if result is not None:
            saved = int(getattr(result, "saved", 0) or 0)
        if saved <= 0:
            self._seed_started.discard(game_slug(game))
        if game_slug(self._game_name) != game_slug(game):
            return
        if result is None:
            text = "Could not reach the wikis. Reminders still hold."
        else:
            text = str(getattr(result, "message", "") or "Could not reach the wikis. Reminders still hold.")
        self._show_ask(text)
        try:
            self.databank_status.config(text=text)
        except Exception:
            pass
        self._refresh_sources()

    def _emit_minute_warns(self) -> None:
        """One tick-tick-tick when a pending reminder first has 60 seconds left."""
        try:
            hits = pending_minute_warns(self.engine.list_all(), self._minute_warned)
        except Exception:
            return
        if hits:
            play_ticks_async(len(hits))

    def _tick_clocks(self) -> None:
        """Rewrite pending clocks about once per second. Fired rows stay FIRED."""
        if not self._clocks:
            return
        now = datetime.now(timezone.utc)
        for label, due_at in self._clocks.values():
            text = format_countdown(remaining_seconds(due_at, now))
            try:
                if str(label.cget("text")) != text:
                    label.config(text=text)
            except Exception:
                continue

    def _on_fire(self, reminder: Reminder) -> None:
        sys.stdout.write(fire_banner(reminder.text) + "\n")
        sys.stdout.write("\a")
        sys.stdout.flush()
        speak_async(f"Battle Buddy. Fire. {reminder.text}")
        self._firing.add(reminder.id)
        hidden = _window_is_hidden(self.root)
        raise_for_fire(self.root)
        self._show_fire(reminder)
        raise_for_fire(self.root)
        if hidden:
            spawn_fire_splash(reminder.text)
        else:
            self.root.after(400, lambda t=reminder.text: self._ensure_fire_visible(t))

    def _show_fire(self, reminder: Reminder) -> None:
        """Visible window: that card goes FIRE. No full-window overlay."""
        self._fire_up = True
        self._firing.add(reminder.id)
        self.status.config(text=f"FIRE. {reminder.text}")

    def _ensure_fire_visible(self, text: str) -> None:
        """If the main window is not on screen, open a topmost FIRE splash."""
        if not _window_is_hidden(self.root):
            return
        spawn_fire_splash(text)

    def _dismiss_fire(self) -> None:
        self._fire_up = False
        self._firing.clear()
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass
        self.status.config(text="Fire seen. Lock another when you need it.")
        try:
            self._refresh_list()
        except Exception:
            pass

    def _clear_drafts(self) -> None:
        """Wipe typed drafts only. Reminders and databank stay on disk."""
        for widget in (
            getattr(self, "entry", None),
            getattr(self, "url_entry", None),
            getattr(self, "ask_entry", None),
            getattr(self, "hold_entry", None),
        ):
            if widget is None:
                continue
            try:
                widget.delete(0, "end")
            except Exception:
                continue
        self._set_ask_out("")
        self._set_war_room_out("")

    def _warm_bundled_llm(self) -> None:
        """Background only. Missing GGUF is fine. Reminder clocks stay live."""
        try:
            start_bundled_server(wait=True)
        except Exception:
            return

    def _restore_window(self) -> None:
        saved = load_window()
        if saved is None:
            return
        spec = window_geometry(
            saved,
            default=_DEFAULT_GEOMETRY,
            min_w=_MIN_WIDTH,
            min_h=_MIN_HEIGHT,
        )
        try:
            self.root.geometry(spec)
        except Exception:
            self.root.geometry(_DEFAULT_GEOMETRY)

    def _remember_window(self) -> None:
        root = getattr(self, "root", None)
        if root is None:
            return
        try:
            root.update_idletasks()
            parsed = parse_tk_geometry(str(root.geometry()))
        except Exception:
            return
        if parsed is None:
            return
        try:
            save_window(
                parsed["width"],
                parsed["height"],
                parsed.get("x"),
                parsed.get("y"),
            )
        except Exception:
            return

    def _on_close(self) -> None:
        if self._hud is not None:
            try:
                self._hud.shutdown()
            except Exception:
                pass
        self._remember_window()
        self._clear_drafts()
        try:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.root.unbind_all(seq)
        except Exception:
            pass
        try:
            self.reader.shutdown()
            self.snap.shutdown()
        except Exception:
            pass
        listener = self._stop_listener
        self._stop_listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        try:
            stop_bundled_server()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            return


def _window_is_hidden(root: object) -> bool:
    try:
        state = str(root.state())
        viewable = bool(root.winfo_viewable())
        mapped = bool(root.winfo_ismapped())
    except Exception:
        return False
    return state == "iconic" or not viewable or not mapped


def raise_for_fire(root: object) -> None:
    """Bring the window forward when a reminder is due, even if it sat in back."""
    try:
        root.bell()
    except Exception:
        pass
    for action in (
        lambda: root.deiconify(),
        lambda: root.wm_state("normal"),
        lambda: root.attributes("-topmost", True),
        lambda: root.lift(),
        lambda: root.focus_force(),
        lambda: root.update_idletasks(),
    ):
        try:
            action()
        except Exception:
            continue
    threading.Thread(target=_raise_windows, args=(root,), daemon=True).start()
    threading.Thread(target=_raise_linux, daemon=True).start()


def spawn_fire_splash(text: str) -> None:
    """Separate topmost FIRE window. Used when the main UI stays minimized."""
    try:
        subprocess.Popen(
            [sys.executable, "-m", "battlebuddy.ui.app", "--fire", text],
            cwd=str(_repo_root()),
            env=os.environ.copy(),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _raise_windows(root: object) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(root.winfo_id())
        parent = ctypes.windll.user32.GetParent(hwnd)
        target = parent or hwnd
        ctypes.windll.user32.ShowWindow(target, 9)
        ctypes.windll.user32.FlashWindow(target, True)
        ctypes.windll.user32.SetForegroundWindow(target)
    except Exception:
        return


def _raise_linux() -> None:
    if sys.platform == "win32":
        return
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        return
    env = os.environ.copy()
    try:
        subprocess.run(
            [
                xdotool,
                "search",
                "--name",
                "Battle Buddy",
                "windowmap",
                "windowactivate",
                "windowraise",
            ],
            timeout=3,
            check=False,
            capture_output=True,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return


def run_fire_splash(text: str) -> int:
    """Standalone FIRE surface. No account. Closes on SEEN."""
    try:
        import tkinter as tk
    except ImportError:
        print(fire_banner(text))
        return 0
    root = tk.Tk()
    root.title("FIRE — Battle Buddy")
    root.configure(bg=_FIRE_BG)
    root.geometry("740x560+80+80")
    try:
        root.wm_class("BattleBuddyFire", "BattleBuddyFire")
    except Exception:
        pass
    try:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
    except Exception:
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
    tk.Label(
        root,
        text="FIRE",
        font=("Arial", 80, "bold"),
        fg=_SCARLET,
        bg=_FIRE_BG,
    ).pack(pady=(80, 12))
    tk.Label(
        root,
        text=text,
        font=("Arial", 28, "bold"),
        fg=_GOLD,
        bg=_FIRE_BG,
        wraplength=640,
    ).pack(pady=12, padx=24)
    tk.Button(
        root,
        text="SEEN",
        font=("Arial", 24, "bold"),
        bg=_SCARLET,
        fg=_GOLD,
        activebackground="#E03A54",
        activeforeground=_GOLD,
        relief="flat",
        cursor="hand2",
        command=root.destroy,
    ).pack(fill="x", ipady=18, padx=48, pady=32)
    try:
        root.lift()
        root.focus_force()
    except Exception:
        pass
    root.mainloop()
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--fire":
        raise SystemExit(run_fire_splash(" ".join(args[1:]) or "reminder"))
    raise SystemExit(run_ui())
