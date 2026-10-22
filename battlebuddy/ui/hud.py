"""Small always-on-top box. Timers and live text. Does not dim a monitor."""

from __future__ import annotations

import queue
from datetime import datetime, timezone

from battlebuddy.ui.overlay_hotkey import OverlayHotkey
from battlebuddy.ui.overlay_model import (
    BOX_H,
    BOX_W,
    alpha_of,
    active_timer_lines,
    clamp_opacity,
    click_through_applies,
    compose_body,
    display_hotkey,
    launch_monitor,
    load_overlay_prefs,
    monitor_at,
    offset_for,
    origin_for,
    output_chunks,
    primary_of,
    save_overlay_prefs,
)
from battlebuddy.ui.overlay_win import apply_window_chrome, list_monitors, window_hwnd
from battlebuddy.ui.tray import OverlayTray, TrayState

_BG = "#0B0B0B"
_GOLD = "#E6C35C"
_FG = "#F4F1E8"
_MUTED = "#C4C0B4"
_EDGE = "#2A2A2A"
_POLL_MS = 200


class HudOverlay:
    """Tool window plus Overlay menu, hotkey, and tray icon."""

    def __init__(self, tk: object, root: object, engine: object, app: object) -> None:
        self.tk = tk
        self.root = root
        self.engine = engine
        self.app = app
        self.prefs = load_overlay_prefs()
        self._events: queue.Queue[str] = queue.Queue()
        self._tray_state = TrayState()
        self._hotkey: OverlayHotkey | None = None
        self._tray: OverlayTray | None = None
        self._win: object | None = None
        self._out: object | None = None
        self._percent: object | None = None
        self._click_btn: object | None = None
        self._scale: object | None = None
        self._body = ""
        self._shown = False
        self._started = False
        self._dead = False
        self._placing = False
        self._disowned = False
        self._save_after: str | None = None
        self._show_var = tk.BooleanVar(master=root, value=False)  # type: ignore[attr-defined]
        self._click_var = tk.BooleanVar(master=root, value=self.prefs.click_through)  # type: ignore[attr-defined]
        self._build_menu()
        try:
            root.bind("<Destroy>", self._on_root_destroy, add="+")  # type: ignore[attr-defined]
        except Exception:
            pass

    def start(self) -> None:
        """Hotkey, tray, and the poll. Safe to skip in tests that never call run()."""
        if self._started or self._dead:
            return
        self._started = True
        self._hotkey = OverlayHotkey(self.prefs.hotkey, lambda: self._events.put("toggle"))
        error = self._hotkey.start()
        if error:
            self._hotkey_note = error
        else:
            self._hotkey_note = display_hotkey(self.prefs.hotkey)
        try:
            self._menu.entryconfig(0, label=self._hotkey_note)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._tray = OverlayTray(self._events, self._tray_state)
        self._tray.start()
        self._publish()
        if self.prefs.visible:
            self.show()
        self._poll()

    def shutdown(self) -> None:
        if self._dead:
            return
        self._dead = True
        if self._shown:
            self._capture_position()
            try:
                save_overlay_prefs(self.prefs)
            except Exception:
                pass
        if self._hotkey is not None:
            try:
                self._hotkey.stop()
            except Exception:
                pass
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
        win = self._win
        self._win = None
        self._shown = False
        if win is not None:
            try:
                win.destroy()  # type: ignore[attr-defined]
            except Exception:
                pass

    def toggle(self) -> None:
        if self._shown:
            self.hide()
        else:
            self.show()

    def show(self) -> None:
        if self._dead:
            return
        if self._win is None:
            self._create()
        win = self._win
        if win is None:
            return
        self._placing = True
        try:
            self._move_to_saved()
            win.deiconify()  # type: ignore[attr-defined]
            win.lift()  # type: ignore[attr-defined]
        except Exception:
            pass
        finally:
            self._placing = False
        self._shown = True
        self.prefs.visible = True
        self._show_var.set(True)
        self._apply_chrome()
        self._sync_click_state()
        self._publish()
        self.refresh()
        self._save_now()

    def hide(self) -> None:
        if self._shown:
            self._capture_position()
        self._shown = False
        self.prefs.visible = False
        try:
            self._show_var.set(False)
        except Exception:
            pass
        if self._win is not None:
            try:
                self._win.withdraw()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._publish()
        self._save_now()

    def refresh(self) -> None:
        if not self._shown or self._out is None:
            return
        try:
            reminders = list(self.engine.list_all())  # type: ignore[attr-defined]
        except Exception:
            reminders = []
        timers = active_timer_lines(reminders, datetime.now(timezone.utc))
        chunks = output_chunks(
            _label_text(getattr(self.app, "status", None)),
            _pane_text(getattr(self.app, "ask_out", None)),
            _pane_text(getattr(self.app, "war_room_out", None)),
            _label_text(getattr(self.app, "read_line", None)),
        )
        body = compose_body(timers, chunks)
        if body == self._body:
            return
        self._body = body
        try:
            self._out.config(state="normal")  # type: ignore[attr-defined]
            self._out.delete("1.0", "end")  # type: ignore[attr-defined]
            self._out.insert("1.0", body)  # type: ignore[attr-defined]
            self._out.config(state="disabled")  # type: ignore[attr-defined]
        except Exception:
            return

    def _build_menu(self) -> None:
        tk = self.tk
        bar = tk.Menu(self.root, tearoff=0)  # type: ignore[attr-defined]
        menu = tk.Menu(bar, tearoff=0)
        menu.add_command(label=display_hotkey(self.prefs.hotkey), state="disabled")
        menu.add_separator()
        menu.add_checkbutton(
            label="Show overlay",
            command=self._on_show_menu,
            variable=self._show_var,
        )
        menu.add_checkbutton(
            label="Click through",
            command=self._on_click,
            variable=self._click_var,
        )
        bar.add_cascade(label="Overlay", menu=menu)
        self._menu = menu
        self._bar = bar
        try:
            self.root.config(menu=bar)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._sync_click_state()

    def _create(self) -> None:
        tk = self.tk
        win = tk.Toplevel(self.root)  # type: ignore[attr-defined]
        win.title("Battle Buddy")
        win.configure(bg=_BG)
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        try:
            win.attributes("-toolwindow", True)
        except Exception:
            pass
        win.minsize(280, 180)
        win.maxsize(640, 520)
        win.protocol("WM_DELETE_WINDOW", self.hide)
        win.bind("<Configure>", self._on_configure)
        win.withdraw()

        head = tk.Frame(win, bg=_BG)
        head.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(
            head,
            text="Battle Buddy",
            font=("Arial", 14, "bold"),
            fg=_GOLD,
            bg=_BG,
            anchor="w",
        ).pack(side="left")
        self._key_label = tk.Label(
            head,
            text=getattr(self, "_hotkey_note", display_hotkey(self.prefs.hotkey)),
            font=("Arial", 11),
            fg=_MUTED,
            bg=_BG,
            anchor="e",
        )
        self._key_label.pack(side="right")

        row = tk.Frame(win, bg=_BG)
        row.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(
            row,
            text="Opacity",
            font=("Arial", 12),
            fg=_FG,
            bg=_BG,
        ).pack(side="left")
        self._percent = tk.Label(
            row,
            text=f"{self.prefs.opacity}%",
            font=("Arial", 12, "bold"),
            fg=_GOLD,
            bg=_BG,
            width=5,
            anchor="e",
        )
        self._percent.pack(side="right")
        self._scale = tk.Scale(
            row,
            from_=10,
            to=100,
            orient="horizontal",
            showvalue=False,
            resolution=1,
            bg=_BG,
            fg=_FG,
            troughcolor=_EDGE,
            activebackground=_GOLD,
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            command=self._on_opacity,
        )
        self._scale.set(self.prefs.opacity)
        self._scale.pack(side="left", fill="x", expand=True, padx=8)
        self._scale.bind("<ButtonRelease-1>", lambda _event: self._save_now())

        self._click_btn = tk.Checkbutton(
            win,
            text="Click through",
            font=("Arial", 12),
            fg=_FG,
            bg=_BG,
            selectcolor=_BG,
            activebackground=_BG,
            activeforeground=_GOLD,
            variable=self._click_var,
            command=self._on_click,
            anchor="w",
        )
        self._click_btn.pack(fill="x", padx=10, pady=(2, 4))

        pane = tk.Frame(win, bg=_BG)
        pane.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._out = tk.Text(
            pane,
            font=("Arial", 13),
            bg=_BG,
            fg=_FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=_EDGE,
            wrap="word",
            state="disabled",
            cursor="arrow",
            insertwidth=0,
        )
        scroll = tk.Scrollbar(pane, command=self._out.yview)
        self._out.config(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._out.pack(side="left", fill="both", expand=True)
        self._win = win
        self._sync_click_state()

    def _move_to_saved(self) -> None:
        win = self._win
        if win is None:
            return
        monitors = list_monitors(self.root)
        target = launch_monitor(monitors, self.prefs.last_monitor)
        try:
            width = int(win.winfo_width())  # type: ignore[attr-defined]
            height = int(win.winfo_height())  # type: ignore[attr-defined]
        except Exception:
            width, height = BOX_W, BOX_H
        if width < 50:
            width = BOX_W
        if height < 50:
            height = BOX_H
        x, y = origin_for(target, self.prefs.positions, width, height)
        try:
            win.geometry(f"{width}x{height}+{x}+{y}")  # type: ignore[attr-defined]
        except Exception:
            return

    def _on_configure(self, event: object) -> None:
        win = self._win
        if self._placing or self._dead or win is None or not self._shown:
            return
        if getattr(event, "widget", None) is not win:
            return
        self._schedule_save()

    def _capture_position(self) -> None:
        """Store this monitor's offset. Other monitors keep theirs."""
        win = self._win
        if win is None or not self._shown or self._placing:
            return
        try:
            win.update_idletasks()  # type: ignore[attr-defined]
            if not int(win.winfo_viewable()):  # type: ignore[attr-defined]
                return
            x = int(win.winfo_x())  # type: ignore[attr-defined]
            y = int(win.winfo_y())  # type: ignore[attr-defined]
            width = int(win.winfo_width())  # type: ignore[attr-defined]
            height = int(win.winfo_height())  # type: ignore[attr-defined]
        except Exception:
            return
        if width < 50 or height < 50:
            return
        monitors = list_monitors(self.root)
        monitor = monitor_at(x + max(width, 0) // 2, y + max(height, 0) // 2, monitors)
        if monitor is None:
            monitor = primary_of(monitors)
        self.prefs.positions[monitor.key] = offset_for(monitor, x, y)
        self.prefs.last_monitor = monitor.key

    def _on_opacity(self, raw: str) -> None:
        self.prefs.opacity = clamp_opacity(raw)
        if self._percent is not None:
            try:
                self._percent.config(text=f"{self.prefs.opacity}%")  # type: ignore[attr-defined]
            except Exception:
                pass
        self._apply_chrome()
        self._sync_click_state()
        self._schedule_save()

    def _on_click(self) -> None:
        if self.prefs.opacity >= 50:
            try:
                self._click_var.set(self.prefs.click_through)
            except Exception:
                pass
            self._sync_click_state()
            return
        self.prefs.click_through = bool(self._click_var.get())
        self._apply_chrome()
        self._publish()
        self._save_now()

    def _on_show_menu(self) -> None:
        if self._show_var.get():
            self.show()
        else:
            self.hide()

    def _apply_chrome(self) -> None:
        win = self._win
        if win is None:
            return
        try:
            win.attributes("-alpha", alpha_of(self.prefs.opacity))  # type: ignore[attr-defined]
            win.attributes("-topmost", True)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            win.update_idletasks()  # type: ignore[attr-defined]
        except Exception:
            pass
        hwnd = window_hwnd(win)
        disown = not self._disowned
        apply_window_chrome(
            hwnd,
            click_through=click_through_applies(self.prefs.opacity, self.prefs.click_through),
            disown=disown,
        )
        if hwnd and disown:
            self._disowned = True

    def _sync_click_state(self) -> None:
        state = "normal" if self.prefs.opacity < 50 else "disabled"
        try:
            self._menu.entryconfig("Click through", state=state)  # type: ignore[attr-defined]
        except Exception:
            pass
        if self._click_btn is not None:
            try:
                self._click_btn.config(state=state)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _publish(self) -> None:
        self._tray_state.update(
            visible=self._shown,
            click_through=bool(self.prefs.click_through),
            click_enabled=self.prefs.opacity < 50,
        )

    def _schedule_save(self) -> None:
        win = self._win
        if win is None:
            self._save_now()
            return
        try:
            if self._save_after is not None:
                win.after_cancel(self._save_after)  # type: ignore[attr-defined]
            self._save_after = win.after(400, self._save_now)  # type: ignore[attr-defined]
        except Exception:
            self._save_now()

    def _save_now(self) -> None:
        self._save_after = None
        if self._shown and not self._placing:
            self._capture_position()
        try:
            save_overlay_prefs(self.prefs)
        except Exception:
            return

    def _poll(self) -> None:
        if self._dead:
            return
        self._drain()
        if self._shown:
            try:
                self.refresh()
            except Exception:
                pass
        try:
            self.root.after(_POLL_MS, self._poll)  # type: ignore[attr-defined]
        except Exception:
            return

    def _drain(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return
            if event == "toggle":
                self.toggle()
            elif event == "click":
                self._click_var.set(not self.prefs.click_through)
                self._on_click()

    def _on_root_destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        self.shutdown()


def _label_text(widget: object | None) -> str:
    if widget is None:
        return ""
    try:
        return str(widget.cget("text") or "")  # type: ignore[attr-defined]
    except Exception:
        return ""


def _pane_text(widget: object | None) -> str:
    if widget is None:
        return ""
    try:
        return str(widget.get("1.0", "end-1c") or "")  # type: ignore[attr-defined]
    except Exception:
        return ""
