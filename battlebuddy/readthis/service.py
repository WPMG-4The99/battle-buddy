"""Hotkey or button → drag → local OCR → local TTS. Optional note for ASK."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from battlebuddy.memory.catalog import KnowledgeCatalog
from battlebuddy.readthis.capture import ReadError, capture_region
from battlebuddy.readthis.clean import clean_ocr_text
from battlebuddy.readthis.config import (
    hotkey_label,
    load_region,
    load_text,
    save_region,
    save_text,
    saves_reads,
)
from battlebuddy.readthis.listen import (
    READ_HOTKEY_ID,
    HotkeyListener,
    arm_escape,
    disarm_escape,
)
from battlebuddy.readthis.ocr import recognize
from battlebuddy.readthis.overlay import RegionOverlay
from battlebuddy.readthis.region import Rect
from battlebuddy.voice.tts import is_speaking, speak, stop_speaking

_NOTE_CAP = 4000


class ReadAloud:
    """UI-facing Read This. Tk stays on the main thread. OCR and speech do not."""

    def __init__(
        self,
        status: Callable[[str], None],
        game_name: Callable[[], str | None],
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        self._status_cb = status
        self._game_name = game_name
        self._on_saved = on_saved
        self.last_region = load_region()
        self.last_text = load_text()
        self._token = 0
        self._busy = False
        self._closed = False
        self._overlay: RegionOverlay | None = None
        self._listener: HotkeyListener | None = None
        self._tk: object | None = None
        self._root: object | None = None

    @property
    def hotkey_label(self) -> str:
        return hotkey_label()

    @property
    def hint(self) -> str:
        return f"Read This · {self.hotkey_label}"

    def bind_ui(self, tk: object, root: object) -> None:
        self._tk = tk
        self._root = root

    def start_hotkey(self) -> None:
        if self._listener is not None or self._closed:
            return
        listener = HotkeyListener(
            self._hotkey_spec(),
            self._on_hotkey,
            name="battlebuddy-read-hotkey",
            taken_hint="BATTLEBUDDY_READ_HOTKEY or read_hotkey in session.json",
            hotkey_id=READ_HOTKEY_ID,
        )
        self._listener = listener
        error = listener.start()
        if error:
            self._status(error)

    def shutdown(self) -> None:
        self._closed = True
        self._cancel_work()
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            overlay.close()
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def start_select(self) -> None:
        """Dim every connected monitor and wait for a drag."""
        if self._closed or self._tk is None or self._root is None:
            return
        self._cancel_work()
        self._busy = False
        if self._overlay is not None:
            self._overlay.cancel()
            return
        self._status("Drag a box. Esc cancels.")
        try:
            self._overlay = RegionOverlay(
                self._tk,
                self._root,
                self._on_selected,
                self._on_overlay_cancel,
            )
        except Exception:
            self._overlay = None
            self._status("Could not open the read overlay.")

    def read_again(self) -> None:
        """Grab the last box again. Event windows that stay put."""
        if self._closed:
            return
        rect = self.last_region or load_region()
        if rect is None:
            self._status("Drag a box once. Read again uses that spot.")
            return
        self._cancel_work()
        self._begin_read(rect)

    def stop_talking(self) -> None:
        """Cut current speech and cancel an active drag. Idle calls are safe."""
        if self._closed:
            return
        self._cancel_overlay()
        self._cancel_work()
        self._busy = False
        self._status("Stopped.")

    def repeat_last(self) -> None:
        """Speak the last cleaned text again. No new grab."""
        if self._closed:
            return
        text = (self.last_text or load_text()).strip()
        if not text:
            self._status("Nothing read yet.")
            return
        self.last_text = text
        self._cancel_work()
        self._busy = True
        token = self._token
        threading.Thread(
            target=self._repeat_worker,
            args=(text, token),
            daemon=True,
        ).start()

    def _on_hotkey(self) -> None:
        root = self._root
        if root is None or self._closed:
            return
        try:
            root.after(0, self._hotkey_main)  # type: ignore[attr-defined]
        except Exception:
            return

    def _hotkey_main(self) -> None:
        if self._closed:
            return
        if self._overlay is not None:
            self._overlay.cancel()
            return
        if is_speaking() or self._busy:
            self._cancel_work()
            self._busy = False
            self._status("Stopped.")
            return
        self.start_select()

    def _on_escape(self) -> None:
        self._token += 1
        self._busy = False
        stop_speaking()
        self._status("Stopped.")

    def _on_selected(self, rect: Rect) -> None:
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            overlay.hide()
            root = self._root
            if root is not None:
                try:
                    root.update_idletasks()  # type: ignore[attr-defined]
                except Exception:
                    pass
            time.sleep(0.05)
            overlay.close()
        self._begin_read(rect)

    def _on_overlay_cancel(self) -> None:
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            overlay.close()
        self._status(self.hint)

    def _begin_read(self, rect: Rect) -> None:
        self.last_region = rect
        try:
            save_region(rect)
        except OSError:
            pass
        self._busy = True
        token = self._token
        self._status("Reading.")
        threading.Thread(
            target=self._worker,
            args=(rect, token),
            daemon=True,
        ).start()

    def _worker(self, rect: Rect, token: int) -> None:
        try:
            if token != self._token or self._closed:
                return
            try:
                image = capture_region(rect)
                raw = recognize(image)
            except ReadError as exc:
                self._status(str(exc))
                return
            except Exception:
                from battlebuddy.readthis.hints import read_failed_help

                self._status(read_failed_help())
                return
            text = clean_ocr_text(raw)
            if token != self._token or self._closed:
                return
            if not text:
                self._status("No text in that box.")
                return
            self.last_text = text
            try:
                save_text(text)
            except OSError:
                pass
            self._maybe_note(text)
            self._speak_only(text, token)
        finally:
            if token == self._token:
                self._busy = False

    def _repeat_worker(self, text: str, token: int) -> None:
        try:
            self._speak_only(text, token)
        finally:
            if token == self._token:
                self._busy = False

    def _speak_only(self, text: str, token: int) -> None:
        if token != self._token or self._closed:
            return
        label = self.hotkey_label
        self._status(f"Speaking. Esc or {label} stops.")
        arm_escape(self._on_escape)

        def _allow() -> bool:
            return token == self._token and not self._closed

        try:
            speak(text, timeout=180, allow=_allow)
        finally:
            disarm_escape()
        if token != self._token or self._closed:
            self._status("Stopped.")
            return
        self._status("Read done.")

    def _maybe_note(self, text: str) -> None:
        if not saves_reads():
            return
        game: str | None
        try:
            game = (self._game_name() or "").strip() or None
        except Exception:
            game = None
        body = text if len(text) <= _NOTE_CAP else text[:_NOTE_CAP].rstrip() + "…"
        try:
            KnowledgeCatalog().add_note(f"Read: {body}", game=game)
        except Exception:
            return
        saved = self._on_saved
        if saved is None:
            return
        try:
            saved()
        except Exception:
            return

    def _cancel_overlay(self) -> None:
        overlay = self._overlay
        if overlay is None:
            return
        try:
            overlay.cancel()
        except Exception:
            try:
                overlay.close()
            except Exception:
                pass
        if self._overlay is overlay:
            self._overlay = None

    def _cancel_work(self) -> None:
        self._token += 1
        stop_speaking()
        disarm_escape()

    def _hotkey_spec(self) -> str:
        from battlebuddy.readthis.config import load_hotkey

        return load_hotkey()

    def _status(self, text: str) -> None:
        if self._closed:
            return
        try:
            self._status_cb(text)
        except Exception:
            return
