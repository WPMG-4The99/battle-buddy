"""Small always-on-top box. Timers and live text. Does not dim a monitor."""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone

from battlebuddy.ui.context_menu import attach_context_menu
from battlebuddy.ui.layout import wheel_units
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
        self._ui_thread = threading.get_ident()
        self._ui_calls: queue.Queue = queue.Queue()
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
        self._tray = OverlayTray(
            self._events,
            self._tray_state,
            schedule=self._schedule_from_tray,
        )
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
        if win is not None and self._save_after is not None:
            try:
                win.after_cancel(self._save_after)  # type: ignore[attr-defined]
            except Exception:
                pass
        self._save_after = None
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
            first_line = self._out.index("@0,0")  # type: ignore[attr-defined]
            at_top = float(self._out.yview()[0]) <= 0.0  # type: ignore[attr-defined]
            sel = _selection(self._out)
            self._out.config(state="normal")  # type: ignore[attr-defined]
            self._out.delete("1.0", "end")  # type: ignore[attr-defined]
            self._out.insert("1.0", body)  # type: ignore[attr-defined]
            _restore_selection(self._out, sel)
            self._out.config(state="disabled")  # type: ignore[attr-defined]
            if not at_top:
                self._out.yview(first_line)  # type: ignore[attr-defined]
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
        menu.add_command(
            label="Turn off click-through / Reset overlay",
            command=self.reset_click_through,
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
        self._bind_overlay_wheel(win)
        try:
            attach_context_menu(self._out, readonly=True)
        except Exception:
            pass
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
        self.set_opacity(raw)

    def set_opacity(self, raw: object) -> None:
        """Opacity slider. Click-through cannot stay on at 50% or above."""
        self._on_ui(lambda: self._set_opacity(raw))

    def _set_opacity(self, raw: object) -> None:
        self.prefs.opacity = clamp_opacity(raw)
        if self._percent is not None:
            try:
                self._percent.config(text=f"{self.prefs.opacity}%")  # type: ignore[attr-defined]
            except Exception:
                pass
        self._apply_click_through()
        self._sync_click_state()
        self._publish()
        self._schedule_save()

    def _on_click(self) -> None:
        try:
            wanted = bool(self._click_var.get())
        except Exception:
            wanted = not self.prefs.click_through
        self.set_click_through(wanted)

    def set_click_through(self, enabled: bool) -> None:
        """Turn click-through on or off. Off always strips WS_EX_TRANSPARENT."""
        self._on_ui(lambda: self._set_click_through(bool(enabled)))

    def _set_click_through(self, enabled: bool) -> None:
        if self.prefs.opacity >= 50 and enabled:
            try:
                self._click_var.set(self.prefs.click_through)
            except Exception:
                pass
            self._apply_click_through()
            self._sync_click_state()
            self._publish()
            return
        self.prefs.click_through = bool(enabled)
        try:
            self._click_var.set(self.prefs.click_through)
        except Exception:
            pass
        self._apply_click_through()
        self._sync_click_state()
        self._publish()
        self._save_now()

    def reset_click_through(self) -> None:
        """Turn click-through off and flush the Windows hit-test. Works anytime."""
        self._on_ui(self._reset_click_through)

    def _reset_click_through(self) -> None:
        self.prefs.click_through = False
        try:
            self._click_var.set(False)
        except Exception:
            pass
        self._apply_click_through()
        self._sync_click_state()
        self._publish()
        self._save_now()

    def _on_ui(self, fn) -> None:
        """Run ``fn`` on the Tk thread. pystray callbacks are not that thread."""
        if threading.get_ident() == self._ui_thread:
            fn()
            return
        self._ui_calls.put(fn)
        try:
            self.root.after(0, self._drain_ui_calls)  # type: ignore[attr-defined]
        except Exception:
            return

    def _drain_ui_calls(self) -> None:
        while True:
            try:
                fn = self._ui_calls.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception:
                continue

    def _schedule_from_tray(self) -> None:
        """pystray menu thread: marshal the queued tray event onto Tk with after(0)."""
        self._on_ui(self._drain)

    def _on_show_menu(self) -> None:
        if self._show_var.get():
            self.show()
        else:
            self.hide()

    def _apply_chrome(self) -> None:
        self._apply_click_through()

    def _apply_click_through(self) -> None:
        """Set or strip WS_EX_TRANSPARENT, then flush the hit-test cache."""
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
        tray = self._tray
        if tray is not None:
            try:
                tray.refresh()
            except Exception:
                pass

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
        self._drain_ui_calls()
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
                self.set_click_through(not self.prefs.click_through)
            elif event == "reset":
                self.reset_click_through()

    def scroll_wheel(self, event: object) -> str:
        """Scroll only the overlay text. ``break`` stops the main window from moving."""
        return self._on_overlay_wheel(event)

    def _bind_overlay_wheel(self, win: object) -> None:
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                win.bind(seq, self._on_overlay_wheel)  # type: ignore[attr-defined]
            except Exception:
                pass
            if self._out is not None:
                try:
                    self._out.bind(seq, self._on_overlay_wheel)  # type: ignore[attr-defined]
                except Exception:
                    pass

    def _on_overlay_wheel(self, event: object) -> str:
        out = self._out
        if out is None:
            return "break"
        step = wheel_units(getattr(event, "delta", 0), getattr(event, "num", None))
        if step:
            try:
                out.yview_scroll(step, "units")  # type: ignore[attr-defined]
            except Exception:
                pass
        return "break"

    def _on_root_destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        self.shutdown()


def _selection(widget: object) -> tuple[str, str] | None:
    try:
        return (str(widget.index("sel.first")), str(widget.index("sel.last")))  # type: ignore[attr-defined]
    except Exception:
        return None


def _restore_selection(widget: object, sel: tuple[str, str] | None) -> None:
    if sel is None:
        return
    try:
        widget.tag_remove("sel", "1.0", "end")  # type: ignore[attr-defined]
        widget.tag_add("sel", sel[0], sel[1])  # type: ignore[attr-defined]
    except Exception:
        return


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
