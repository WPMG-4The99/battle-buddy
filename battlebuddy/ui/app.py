"""High-contrast UI. One primary action: set a reminder. No account."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone

from battlebuddy.databank.reason import present_ask
from battlebuddy.databank.search import ask_pages
from battlebuddy.databank.slug import databank_label, game_slug
from battlebuddy.databank.store import DatabankStore
from battlebuddy.databank.wiki import ask_or_hunt, rank_ask_result, should_hunt
from battlebuddy.game_detect import detect_game, status_line
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import STATUS_PENDING, Reminder, ReminderEngine
from battlebuddy.reminders.notify import fire_banner
from battlebuddy.reminders.parse import is_clear_all
from battlebuddy.reminders.warn import pending_minute_warns
from battlebuddy.voice.stt import listen_once, stt_available
from battlebuddy.voice.tick import play_ticks_async
from battlebuddy.voice.tts import speak_async, tts_available

_BG = "#111111"
_FG = "#F4F1E8"
_FLAME = "#FF6A00"
_FIRE_BG = "#000000"
_FIRE_FG = "#FFE600"
_INPUT_BG = "#1C1C1C"
_MUTED = "#C4C0B4"
_EXAMPLE = "remind me in 1 minute to check food stores"
_POLL_MS = 250
_DETECT_EVERY = 20
_CLOCK_FONT = ("Arial", 40, "bold")


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
        return result, present_ask(result, question, store, game)
    except Exception:
        return result, shown_after_hunt_failure(result)


def switched_databank_line(game: str | None) -> str:
    return f"Switched databank to {game_slug(game)}."


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
    try:
        import tkinter as tk
    except ImportError:
        print("No tkinter on this box. Typed path still works:")
        print("  python -m battlebuddy remind me in 1 minute to check food stores")
        return 1
    app = BattleBuddyApp(tk)
    app.run()
    return 0


class BattleBuddyApp:
    def __init__(self, tk: object) -> None:
        self.tk = tk
        self.engine = ReminderEngine()
        self._listening = False
        self._fire_up = False
        self._wipe_armed = False
        self._clocks: dict[str, tuple[object, str]] = {}
        self._minute_warned: set[str] = set()
        self._game_busy = False
        self._detect_ticks = 0

        self.root = tk.Tk()
        self.root.title("Battle Buddy")
        self.root.configure(bg=_BG)
        self.databank = DatabankStore()
        self._game_name: str | None = self.databank.sole_saved_game()
        self._fetching = False
        self._asking = False

        self.root.minsize(1000, 640)
        self.root.geometry("1200x800")

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(_POLL_MS, self._tick)

    def run(self) -> None:
        self.root.mainloop()

    def _build(self) -> None:
        tk = self.tk

        tk.Label(
            self.root,
            text=_voice_footer(),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
        ).pack(side="bottom", pady=8)

        columns = tk.Frame(self.root, bg=_BG)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1, uniform="col")
        columns.columnconfigure(1, weight=1, uniform="col")
        columns.rowconfigure(0, weight=1)

        left = tk.Frame(columns, bg=_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=4)
        right = tk.Frame(columns, bg=_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=4)

        self._build_left(left)
        self._build_databank(right)
        self._build_ask(right)

        self._overlay = tk.Frame(self.root, bg=_FIRE_BG)
        tk.Label(
            self._overlay,
            text="FIRE",
            font=("Arial", 80, "bold"),
            fg=_FIRE_FG,
            bg=_FIRE_BG,
        ).pack(pady=(80, 12))
        self.fire_text = tk.Label(
            self._overlay,
            text="",
            font=("Arial", 28, "bold"),
            fg=_FG,
            bg=_FIRE_BG,
            wraplength=640,
        )
        self.fire_text.pack(pady=12, padx=24)
        tk.Button(
            self._overlay,
            text="SEEN",
            font=("Arial", 24, "bold"),
            bg=_FIRE_FG,
            fg=_FIRE_BG,
            activebackground="#FFF38A",
            relief="flat",
            cursor="hand2",
            command=self._dismiss_fire,
        ).pack(fill="x", ipady=18, padx=48, pady=32)

        self._refresh_list()
        pending = [item for item in self.engine.list_all() if item.status == "pending"]
        if pending:
            self.status.config(text="Holding the line. Pending reminder on disk.")

    def _build_left(self, parent: object) -> None:
        """Reminders stay on the left. ASK output never lands here."""
        tk = self.tk

        self.clear_all_btn = tk.Button(
            parent,
            text="CLEAR ALL",
            font=("Arial", 16, "bold"),
            bg="#2A2A2A",
            fg=_FG,
            activebackground="#3A3A3A",
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=self._clear_all,
        )
        self.clear_all_btn.pack(side="bottom", fill="x", ipady=8, pady=(2, 2))

        tk.Label(
            parent,
            text="BATTLE BUDDY",
            font=("Arial", 28, "bold"),
            fg=_FLAME,
            bg=_BG,
        ).pack(pady=(4, 0))

        tk.Label(
            parent,
            text="Speak it once. It holds the line.",
            font=("Arial", 14),
            fg=_FG,
            bg=_BG,
        ).pack(pady=(2, 2))

        self.game_line = tk.Label(
            parent,
            text=status_line(None),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
        )
        self.game_line.pack(pady=(0, 6))

        self._field_caption(parent, "REMINDER", "Lock a time reminder here")

        self.entry = tk.Entry(
            parent,
            font=("Arial", 20),
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_FLAME,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_FLAME,
            highlightcolor=_FLAME,
        )
        self.entry.pack(fill="x", ipady=6, pady=4)
        self.entry.bind("<Return>", lambda _event: self._lock())
        self.entry.focus_set()

        actions = tk.Frame(parent, bg=_BG)
        actions.pack(fill="x", pady=(6, 4))
        speak_on = stt_available()
        self.lock_btn = tk.Button(
            actions,
            text="SUBMIT",
            font=("Arial", 22, "bold"),
            bg=_FLAME,
            fg=_BG,
            activebackground="#FF8A30",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._lock,
        )
        self.lock_btn.pack(
            side="left",
            expand=True,
            fill="x",
            ipady=8,
            padx=(0, 8) if speak_on else 0,
        )
        if speak_on:
            self.speak_btn = tk.Button(
                actions,
                text="SPEAK",
                font=("Arial", 16, "bold"),
                bg="#2A2A2A",
                fg=_FG,
                activebackground="#3A3A3A",
                activeforeground=_FG,
                relief="flat",
                cursor="hand2",
                command=self._speak,
            )
            self.speak_btn.pack(side="left", expand=True, fill="x", ipady=8)
        else:
            self.speak_btn = None

        self.status = tk.Label(
            parent,
            text="One action. Lock a reminder. No account.",
            font=("Arial", 16),
            fg=_FG,
            bg=_BG,
            anchor="w",
        )
        self.status.pack(fill="x", pady=4)

        list_frame = tk.Frame(parent, bg=_BG)
        list_frame.pack(fill="both", expand=True, pady=(4, 4))
        tk.Label(
            list_frame,
            text="ON DISK",
            font=("Arial", 14, "bold"),
            fg=_FLAME,
            bg=_BG,
        ).pack(anchor="w")
        self.list_canvas = tk.Canvas(
            list_frame,
            bg=_BG,
            highlightthickness=0,
            bd=0,
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

    def _field_caption(
        self, parent: object, title: str, hint: str = "", *, padx: int = 0
    ) -> None:
        """Large high-contrast name above a box. Hint stays outside the entry."""
        tk = self.tk
        row = tk.Frame(parent, bg=_BG)
        pack = {"fill": "x", "pady": (4, 2)}
        if padx:
            pack["padx"] = padx
        row.pack(**pack)
        tk.Label(
            row,
            text=title,
            font=("Arial", 16, "bold"),
            fg=_FLAME,
            bg=_BG,
            anchor="w",
        ).pack(side="left")
        if not hint:
            return
        tk.Label(
            row,
            text=hint,
            font=("Arial", 14),
            fg=_FG,
            bg=_BG,
            anchor="w",
        ).pack(side="left", padx=(12, 0))

    def _build_databank(self, parent: object) -> None:
        """Paste a URL. The app fetches. ASK searches local files. No chat."""
        tk = self.tk
        box = tk.Frame(parent, bg=_BG)
        box.pack(fill="x", pady=(4, 4))

        self.databank_header = tk.Label(
            box,
            text=databank_label(self._game_name),
            font=("Arial", 14, "bold"),
            fg=_FLAME,
            bg=_BG,
            anchor="w",
        )
        self.databank_header.pack(fill="x", pady=(2, 0))

        self._field_caption(box, "URL", "Paste a wiki URL here")

        url_row = tk.Frame(box, bg=_BG)
        url_row.pack(fill="x", pady=(0, 2))
        self.url_entry = tk.Entry(
            url_row,
            font=("Arial", 18),
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_FLAME,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_FLAME,
            highlightcolor=_FLAME,
        )
        self.url_entry.pack(side="left", expand=True, fill="x", ipady=8)
        self.url_entry.bind("<Return>", lambda _event: self._add_fetch())
        self.fetch_btn = tk.Button(
            url_row,
            text="ADD / FETCH",
            font=("Arial", 16, "bold"),
            bg=_FLAME,
            fg=_BG,
            activebackground="#FF8A30",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._add_fetch,
        )
        self.fetch_btn.pack(side="left", ipady=8, padx=(8, 0))

        self.databank_status = tk.Label(
            box,
            text="Paste a public wiki URL. The app fetches it. No account.",
            font=("Arial", 14),
            fg=_FG,
            bg=_BG,
            anchor="w",
        )
        self.databank_status.pack(fill="x", pady=(0, 4))

        self.source_box = tk.Frame(box, bg=_BG)
        self.source_box.pack(fill="x")
        self._refresh_sources()

    def _build_ask(self, parent: object) -> None:
        """ASK + output fill the right column. This pane is the only ASK dump."""
        tk = self.tk
        box = tk.Frame(parent, bg=_BG)
        box.pack(fill="both", expand=True, pady=(4, 4))

        self._field_caption(box, "ASK YOUR QUESTION")

        ask_row = tk.Frame(box, bg=_BG)
        ask_row.pack(fill="x", pady=(0, 2))
        self.ask_entry = tk.Entry(
            ask_row,
            font=("Arial", 18),
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_FLAME,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_FLAME,
            highlightcolor=_FLAME,
        )
        self.ask_entry.pack(side="left", expand=True, fill="x", ipady=8)
        self.ask_entry.bind("<Return>", lambda _event: self._ask())
        self.ask_btn = tk.Button(
            ask_row,
            text="ASK",
            font=("Arial", 16, "bold"),
            bg=_FLAME,
            fg=_BG,
            activebackground="#FF8A30",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._ask,
        )
        self.ask_btn.pack(side="left", ipady=8, padx=(8, 0))

        pane = tk.Frame(box, bg=_INPUT_BG, height=220)
        pane.pack(fill="both", expand=True, pady=(0, 4))
        pane.pack_propagate(False)
        self.ask_out = tk.Text(
            pane,
            font=("Arial", 14),
            bg=_INPUT_BG,
            fg=_FG,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_FLAME,
            highlightcolor=_FLAME,
            wrap="word",
            height=8,
            state="disabled",
            cursor="arrow",
        )
        scroll = tk.Scrollbar(pane, command=self.ask_out.yview)
        self.ask_out.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.ask_out.pack(side="left", fill="both", expand=True)

    def _add_fetch(self) -> None:
        if self._fetching:
            return
        url = str(self.url_entry.get()).strip()
        if not url or url in {"http://", "https://"}:
            self.databank_status.config(text="Paste a public http or https URL.")
            return
        self._fetching = True
        self.fetch_btn.config(state="disabled", text="FETCHING")
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
            self.fetch_btn.config(state="normal", text="ADD / FETCH")
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
                self.url_entry.insert(0, "https://")
            except Exception:
                pass
        else:
            self.databank_status.config(text=message)
        self._refresh_sources()

    def _refresh_sources(self) -> None:
        try:
            self.databank_header.config(text=databank_label(self._game_name))
        except Exception:
            pass
        try:
            for child in self.source_box.winfo_children():
                child.destroy()
        except Exception:
            return
        tk = self.tk
        sources = self.databank.list_sources(self._game_name)
        if not sources:
            tk.Label(
                self.source_box,
                text="No sources on disk for this game.",
                font=("Arial", 12),
                fg=_MUTED,
                bg=_BG,
                anchor="w",
            ).pack(fill="x", pady=2)
            return
        for item in sources:
            line = item.title or item.url
            tk.Label(
                self.source_box,
                text=line,
                font=("Arial", 12),
                fg=_MUTED,
                bg=_BG,
                anchor="w",
                wraplength=520,
                justify="left",
            ).pack(fill="x", pady=1)

    def _ask(self) -> None:
        """Local retrieve first. Hunt the game wiki in the background on a miss."""
        if self._asking:
            return
        question = str(self.ask_entry.get()).strip()
        result = ask_pages(self.databank, self._game_name, question)
        if not should_hunt(self.databank, self._game_name, question, result):
            ranked = rank_ask_result(result, question)
            self._show_ask(present_ask(ranked, question, self.databank, self._game_name))
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

    def _wheel(self, event: object) -> None:
        delta = int(getattr(event, "delta", 0) or 0)
        num = int(getattr(event, "num", 0) or 0)
        if num == 4 or delta > 0:
            self.list_canvas.yview_scroll(-1, "units")
        elif num == 5 or delta < 0:
            self.list_canvas.yview_scroll(1, "units")

    def _lock(self) -> None:
        line = self.entry.get().strip()
        if is_clear_all(line):
            self._clear_all()
            return
        result = run_line(self.engine, line)
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
        if result.kind == "remind" and result.reminder is not None:
            due = _local_stamp(result.reminder.due_at)
            self.status.config(text=f"{result.message}  Due {due}.")
            self.entry.delete(0, "end")
            self.entry.focus_set()
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
        if not reminders:
            tk.Label(
                self.list_box,
                text="No reminders on disk.",
                font=("Arial", 16),
                fg=_MUTED,
                bg=_BG,
                anchor="w",
            ).pack(fill="x", pady=8)
            return
        for item in reminders:
            self._add_row(item)
        self._bind_wheel(self.list_box)
        self._emit_minute_warns()

    def _bind_wheel(self, widget: object) -> None:
        for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            widget.bind(seq, self._wheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _add_row(self, item: Reminder) -> None:
        tk = self.tk
        row = tk.Frame(self.list_box, bg=_INPUT_BG, highlightthickness=2, highlightbackground=_FLAME)
        row.pack(fill="x", pady=8)
        tk.Label(
            row,
            text=item.text,
            font=("Arial", 16),
            fg=_FG,
            bg=_INPUT_BG,
            wraplength=480,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 2))
        pending = item.status == STATUS_PENDING
        clock = tk.Label(
            row,
            text=row_clock_text(item.status, item.due_at),
            font=_CLOCK_FONT,
            fg=_FLAME if pending else _FIRE_FG,
            bg=_INPUT_BG,
            anchor="w",
        )
        clock.pack(fill="x", padx=12, pady=(0, 4))
        if pending:
            self._clocks[item.id] = (clock, item.due_at)
        btns = tk.Frame(row, bg=_INPUT_BG)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(
            btns,
            text="SNOOZE 5 MIN",
            font=("Arial", 16, "bold"),
            bg=_FLAME,
            fg=_BG,
            activebackground="#FF8A30",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=lambda i=item: self._snooze_item(i),
        ).pack(side="left", expand=True, fill="x", ipady=12, padx=(0, 8))
        tk.Button(
            btns,
            text="CLEAR",
            font=("Arial", 16, "bold"),
            bg="#2A2A2A",
            fg=_FG,
            activebackground="#3A3A3A",
            activeforeground=_FG,
            relief="flat",
            cursor="hand2",
            command=lambda i=item: self._clear_item(i),
        ).pack(side="left", expand=True, fill="x", ipady=12)

    def _snooze_item(self, item: Reminder) -> None:
        result = run_line(self.engine, f"snooze {item.id} 5 minutes")
        self.status.config(text=result.message)
        if result.speak:
            speak_async(result.speak)
        self._wipe_armed = False
        self.clear_all_btn.config(text="CLEAR ALL")
        self._refresh_list()

    def _clear_item(self, item: Reminder) -> None:
        result = run_line(self.engine, f"clear {item.id}")
        self.status.config(text=result.message)
        if result.speak:
            speak_async(result.speak)
        self._wipe_armed = False
        self.clear_all_btn.config(text="CLEAR ALL")
        self._refresh_list()

    def _clear_all(self) -> None:
        if not self._wipe_armed:
            self._wipe_armed = True
            self.clear_all_btn.config(text="CONFIRM WIPE")
            self.status.config(text="Confirm once. Hit CONFIRM WIPE to clear all.")
            return
        result = run_line(self.engine, "clear all")
        self._wipe_armed = False
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
        try:
            self.root.after(_POLL_MS, self._tick)
        except Exception:
            return

    def _maybe_scan_game(self) -> None:
        """Refresh the quiet game line. Never blocks fire or countdown."""
        self._detect_ticks += 1
        if self._detect_ticks != 1 and self._detect_ticks % _DETECT_EVERY != 0:
            return
        if self._game_busy:
            return
        self._game_busy = True
        threading.Thread(target=self._scan_game_worker, daemon=True).start()

    def _scan_game_worker(self) -> None:
        try:
            name = detect_game()
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
        old = self._game_name
        if not is_named_game(old):
            self._game_name = name
            self._refresh_sources()
            return
        if game_slug(old) == game_slug(name):
            self._game_name = name
            return
        self._game_name = name
        self._refresh_sources()
        notice = switched_databank_line(name)
        self._show_ask(notice)
        try:
            self.databank_status.config(text=notice)
        except Exception:
            pass

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
        hidden = _window_is_hidden(self.root)
        raise_for_fire(self.root)
        self._show_fire(reminder.text)
        raise_for_fire(self.root)
        if hidden:
            spawn_fire_splash(reminder.text)
        else:
            self.root.after(400, lambda t=reminder.text: self._ensure_fire_visible(t))

    def _show_fire(self, text: str) -> None:
        self._fire_up = True
        self.fire_text.config(text=text)
        self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._overlay.lift()

    def _ensure_fire_visible(self, text: str) -> None:
        """If the main window is not on screen, open a topmost FIRE splash."""
        if not _window_is_hidden(self.root):
            return
        spawn_fire_splash(text)

    def _dismiss_fire(self) -> None:
        self._fire_up = False
        self._overlay.place_forget()
        try:
            self.root.attributes("-topmost", False)
        except Exception:
            pass
        self.status.config(text="Fire seen. Lock another when you need it.")

    def _clear_drafts(self) -> None:
        """Wipe typed drafts only. Reminders and databank stay on disk."""
        for widget in (
            getattr(self, "entry", None),
            getattr(self, "url_entry", None),
            getattr(self, "ask_entry", None),
        ):
            if widget is None:
                continue
            try:
                widget.delete(0, "end")
            except Exception:
                continue
        self._set_ask_out("")

    def _on_close(self) -> None:
        self._clear_drafts()
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
        fg=_FIRE_FG,
        bg=_FIRE_BG,
    ).pack(pady=(80, 12))
    tk.Label(
        root,
        text=text,
        font=("Arial", 28, "bold"),
        fg=_FG,
        bg=_FIRE_BG,
        wraplength=640,
    ).pack(pady=12, padx=24)
    tk.Button(
        root,
        text="SEEN",
        font=("Arial", 24, "bold"),
        bg=_FIRE_FG,
        fg=_FIRE_BG,
        activebackground="#FFF38A",
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
