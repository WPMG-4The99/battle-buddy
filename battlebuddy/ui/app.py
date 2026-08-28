"""High-contrast UI. One primary action: set a reminder. No account."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone

from battlebuddy.reminders.engine import Reminder, ReminderEngine
from battlebuddy.reminders.notify import confirm_line, fire_banner
from battlebuddy.reminders.parse import parse_reminder
from battlebuddy.voice.stt import listen_once, stt_available
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

        self.root = tk.Tk()
        self.root.title("Battle Buddy")
        self.root.configure(bg=_BG)
        self.root.minsize(640, 520)
        self.root.geometry("740x560")

        self._build()
        self.root.after(_POLL_MS, self._tick)

    def run(self) -> None:
        self.root.mainloop()

    def _build(self) -> None:
        tk = self.tk
        pad = {"padx": 28, "pady": 8}

        tk.Label(
            self.root,
            text="BATTLE BUDDY",
            font=("Arial", 28, "bold"),
            fg=_FLAME,
            bg=_BG,
        ).pack(pady=(28, 0))

        tk.Label(
            self.root,
            text="Speak it once. It holds the line.",
            font=("Arial", 14),
            fg=_FG,
            bg=_BG,
        ).pack(pady=(4, 16))

        self.entry = tk.Entry(
            self.root,
            font=("Arial", 20),
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_FLAME,
            relief="flat",
            highlightthickness=2,
            highlightbackground=_FLAME,
            highlightcolor=_FLAME,
        )
        self.entry.pack(fill="x", ipady=18, padx=28, pady=8)
        self.entry.insert(0, _EXAMPLE)
        self.entry.bind("<Return>", lambda _event: self._lock())
        self.entry.focus_set()

        self.lock_btn = tk.Button(
            self.root,
            text="HOLD THE LINE",
            font=("Arial", 26, "bold"),
            bg=_FLAME,
            fg=_BG,
            activebackground="#FF8A30",
            activeforeground=_BG,
            relief="flat",
            cursor="hand2",
            command=self._lock,
        )
        self.lock_btn.pack(fill="x", ipady=22, padx=28, pady=(12, 8))

        if stt_available():
            self.speak_btn = tk.Button(
                self.root,
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
            self.speak_btn.pack(fill="x", ipady=12, padx=28, pady=4)
        else:
            self.speak_btn = None

        self.status = tk.Label(
            self.root,
            text="One action. Lock a reminder. No account.",
            font=("Arial", 16),
            fg=_FG,
            bg=_BG,
            wraplength=660,
            justify="left",
        )
        self.status.pack(fill="x", **pad)

        tk.Label(
            self.root,
            text=_voice_footer(),
            font=("Arial", 12),
            fg=_MUTED,
            bg=_BG,
        ).pack(side="bottom", pady=16)

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

        pending = [item for item in self.engine.list_all() if item.status == "pending"]
        if pending:
            self.status.config(text="Holding the line. Pending reminder on disk.")

    def _lock(self) -> None:
        line = self.entry.get().strip()
        parsed = parse_reminder(line)
        if parsed is None:
            self.status.config(
                text="Could not parse that. Try: remind me in 1 minute to check food stores"
            )
            return
        reminder = self.engine.schedule(parsed.text, parsed.delay_seconds)
        line = confirm_line(reminder.text, parsed.delay_label)
        due = _local_stamp(reminder.due_at)
        self.status.config(text=f"{line}  Due {due}.")
        speak_async(line)

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
        parsed = parse_reminder(heard)
        if parsed is None:
            self.status.config(text=f"Heard: {heard}. Edit, then HOLD THE LINE.")
            return
        self._lock()

    def _tick(self) -> None:
        try:
            fired = self.engine.fire_due()
        except Exception:
            fired = []
        for item in fired:
            self._on_fire(item)
        try:
            self.root.after(_POLL_MS, self._tick)
        except Exception:
            return

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
