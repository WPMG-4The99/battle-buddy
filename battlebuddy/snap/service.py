"""Hotkey or button → monitor grab → Read This OCR → spoken answer."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from battlebuddy.databank.search import ask_pages
from battlebuddy.memory.catalog import KnowledgeCatalog
from battlebuddy.memory.store import default_home
from battlebuddy.readthis.capture import ReadError, capture_region
from battlebuddy.readthis.clean import clean_ocr_text
from battlebuddy.readthis.listen import HotkeyListener, arm_escape, disarm_escape
from battlebuddy.readthis.ocr import recognize
from battlebuddy.readthis.overlay import RegionOverlay
from battlebuddy.readthis.region import Rect
from battlebuddy.readthis.screen import monitor_at_cursor
from battlebuddy.session.tier import load_brain
from battlebuddy.snap.answer import DEFAULT_QUESTION
from battlebuddy.snap.config import load_snap_hotkey, snap_hotkey_label
from battlebuddy.snap.pipeline import SnapResult, finish_snap
from battlebuddy.snap.shots import fitted_size
from battlebuddy.voice.stt import listen_once, stt_available
from battlebuddy.voice.tts import speak, stop_speaking
from battlebuddy.xai.loop import api_key, chat


def grab_monitor(
    root: object | None = None,
    *,
    capture: Callable[[Rect], object] = capture_region,
    monitor: Callable[[object | None], Rect] = monitor_at_cursor,
) -> tuple[Rect, object]:
    """Full frame of the monitor under the pointer. Any of the three."""
    rect = monitor(root)
    return rect, capture(rect)


def shrink_for_ocr(image: object, max_width: int = 1280) -> object:
    size = getattr(image, "size", None)
    resize = getattr(image, "resize", None)
    if not size or resize is None:
        return image
    width, height = fitted_size(int(size[0]), int(size[1]), max_width)
    if (width, height) == (int(size[0]), int(size[1])):
        return image
    try:
        from PIL import Image

        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
    except Exception:
        resample = None
    if resample is None:
        return resize((width, height))
    return resize((width, height), resample)


class SnapAsk:
    """UI-facing Snap & Ask. Capture stays off the Tk thread after the drag."""

    def __init__(
        self,
        status: Callable[[str], None],
        game_name: Callable[[], str | None],
        databank: Callable[[], object] | None = None,
    ) -> None:
        self._status_cb = status
        self._game_name = game_name
        self._databank = databank
        self._token = 0
        self._busy = False
        self._closed = False
        self._overlay: RegionOverlay | None = None
        self._listener: HotkeyListener | None = None
        self._follow: object | None = None
        self._ask_entry: object | None = None
        self._tk: object | None = None
        self._root: object | None = None
        self._last_ocr = ""
        self._last_game: str | None = None

    @property
    def hotkey_label(self) -> str:
        return snap_hotkey_label()

    def bind_ui(self, tk: object, root: object) -> None:
        self._tk = tk
        self._root = root

    def start_hotkey(self) -> None:
        if self._listener is not None or self._closed:
            return
        listener = HotkeyListener(
            load_snap_hotkey(),
            self._on_hotkey,
            name="battlebuddy-snap-hotkey",
        )
        self._listener = listener
        error = listener.start()
        if error:
            self._status(error)

    def shutdown(self) -> None:
        self._closed = True
        self._cancel()
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            overlay.close()
        self._close_follow()
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.stop()

    def snap_monitor(self) -> None:
        """Grab the monitor under the pointer and answer."""
        if self._closed:
            return
        self._cancel()
        self._status("Snapping.")
        root = self._root
        token = self._token
        threading.Thread(
            target=self._monitor_worker,
            args=(root, token),
            daemon=True,
        ).start()

    def snap_box(self) -> None:
        """Dim every monitor, then drag a region. Same OCR and answer as SNAP."""
        if self._closed or self._tk is None or self._root is None:
            return
        self._cancel()
        if self._overlay is not None:
            self._overlay.cancel()
            return
        self._status("Drag a box. Esc cancels.")
        try:
            self._overlay = RegionOverlay(
                self._tk,
                self._root,
                self._on_box,
                self._on_box_cancel,
            )
        except Exception:
            self._overlay = None
            self._status("Could not open the snap box.")

    def stop_talking(self) -> None:
        """Cut current speech. Idle calls are safe. Does not cancel a drag."""
        if self._closed:
            return
        self._cancel()
        self._status("Stopped.")

    def ask_followup(self, question: str | None = None) -> None:
        """Typed question, or the mic when the box is empty."""
        if self._closed:
            return
        if not self._last_ocr:
            self._status("Snap first.")
            return
        self._cancel()
        asked = (question if question is not None else self._entry_text()).strip()
        token = self._token
        if asked:
            threading.Thread(
                target=self._answer_worker,
                args=(self._last_ocr, self._last_game, asked, token),
                daemon=True,
            ).start()
            return
        if not stt_available():
            self._status("Type a question about the snap.")
            return
        self._status("Listening.")
        threading.Thread(target=self._listen_worker, args=(token,), daemon=True).start()

    def _on_hotkey(self) -> None:
        root = self._root
        if root is None or self._closed:
            return
        try:
            root.after(0, self.snap_monitor)  # type: ignore[attr-defined]
        except Exception:
            return

    def _on_escape(self) -> None:
        self._token += 1
        self._busy = False
        stop_speaking()
        self._status("Stopped.")

    def _on_box(self, rect: Rect) -> None:
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
            overlay.close()
        token = self._token
        self._status("Snapping.")
        threading.Thread(
            target=self._rect_worker,
            args=(rect, token),
            daemon=True,
        ).start()

    def _on_box_cancel(self) -> None:
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            overlay.close()
        self._status(f"Snap · {self.hotkey_label}")

    def _monitor_worker(self, root: object | None, token: int) -> None:
        if token != self._token or self._closed:
            return
        try:
            _rect, image = grab_monitor(root)
        except ReadError as exc:
            self._status(str(exc))
            return
        except Exception:
            self._status("Snap could not grab that monitor.")
            return
        self._read_image(image, token)

    def _rect_worker(self, rect: Rect, token: int) -> None:
        if token != self._token or self._closed:
            return
        try:
            image = capture_region(rect)
        except ReadError as exc:
            self._status(str(exc))
            return
        except Exception:
            self._status("Snap could not grab that box.")
            return
        self._read_image(image, token)

    def _read_image(self, image: object, token: int) -> None:
        try:
            raw = recognize(shrink_for_ocr(image))
        except ReadError as exc:
            self._status(str(exc))
            return
        except Exception:
            self._status("Snap OCR failed. pip install -r requirements-readthis.txt")
            return
        text = clean_ocr_text(raw)
        if token != self._token or self._closed:
            return
        if not text:
            self._status("No text in that snap.")
            return
        game = self._current_game()
        self._last_ocr = text
        self._last_game = game
        self._answer_worker(text, game, DEFAULT_QUESTION, token, image=image)

    def _listen_worker(self, token: int) -> None:
        heard = listen_once()
        if token != self._token or self._closed:
            return
        if not heard:
            self._status("Heard nothing. Type it.")
            return
        self._answer_worker(self._last_ocr, self._last_game, heard, token)

    def _answer_worker(
        self,
        ocr_text: str,
        game: str | None,
        question: str,
        token: int,
        image: object | None = None,
    ) -> None:
        if token != self._token or self._closed or not ocr_text:
            return
        self._busy = True
        home = default_home()
        try:
            notes = [item.text for item in KnowledgeCatalog(home).list_notes(game)[:5]]
        except Exception:
            notes = []
        try:
            pages = _page_lines(self._databank() if self._databank else None, game, question)
        except Exception:
            pages = []
        try:
            if image is None:
                result = _answer_saved(ocr_text, game, question, notes, pages, home)
            else:
                result = finish_snap(
                    image,
                    ocr_text,
                    game,
                    question,
                    notes=notes,
                    pages=pages,
                    home=home,
                    brain=load_brain(home),
                    chat_fn=chat,
                    local_fn=_local,
                    key=api_key(),
                )
        except Exception:
            self._busy = False
            self._status("Snap could not answer.")
            return
        if token != self._token or self._closed:
            self._busy = False
            return
        self._speak(result, token)

    def _speak(self, result: SnapResult, token: int) -> None:
        self._status(result.answer)
        self._show_followup()
        arm_escape(self._on_escape)

        def _allow() -> bool:
            return token == self._token and not self._closed

        try:
            speak(result.answer, timeout=90, allow=_allow)
        finally:
            disarm_escape()
        if token == self._token:
            self._busy = False

    def _show_followup(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.after(0, self._open_followup)  # type: ignore[attr-defined]
        except Exception:
            return

    def _open_followup(self) -> None:
        if self._closed or self._tk is None or self._root is None:
            return
        if self._follow is not None:
            return
        tk = self._tk
        win = tk.Toplevel(self._root)  # type: ignore[attr-defined]
        win.title("Snap")
        win.configure(bg="#0B0B0B")
        try:
            win.attributes("-topmost", True)
        except Exception:
            pass
        tk.Label(  # type: ignore[attr-defined]
            win,
            text="Ask about this snap",
            font=("Arial", 14, "bold"),
            fg="#E6C35C",
            bg="#0B0B0B",
        ).pack(fill="x", padx=12, pady=(10, 4))
        entry = tk.Entry(  # type: ignore[attr-defined]
            win,
            font=("Arial", 16),
            bg="#161616",
            fg="#F4F1E8",
            insertbackground="#E6C35C",
            relief="flat",
        )
        entry.pack(fill="x", padx=12, ipady=6)
        entry.bind("<Return>", lambda _event: self.ask_followup())
        win.bind("<Escape>", lambda _event: self._escape_follow())
        tk.Button(  # type: ignore[attr-defined]
            win,
            text="ASK",
            font=("Arial", 14, "bold"),
            bg="#C41E3A",
            fg="#F4F1E8",
            relief="flat",
            command=lambda: self.ask_followup(),
        ).pack(fill="x", padx=12, pady=10, ipady=6)
        self._follow = win
        self._ask_entry = entry
        try:
            entry.focus_set()
        except Exception:
            pass

    def _escape_follow(self) -> None:
        self._on_escape()
        self._close_follow()

    def _close_follow(self) -> None:
        win = self._follow
        self._follow = None
        self._ask_entry = None
        if win is None:
            return
        try:
            win.destroy()  # type: ignore[attr-defined]
        except Exception:
            return

    def _entry_text(self) -> str:
        entry = self._ask_entry
        if entry is None:
            return ""
        try:
            return str(entry.get())  # type: ignore[attr-defined]
        except Exception:
            return ""

    def _current_game(self) -> str | None:
        try:
            name = (self._game_name() or "").strip()
        except Exception:
            return None
        return name or None

    def _cancel(self) -> None:
        self._token += 1
        self._busy = False
        stop_speaking()
        disarm_escape()

    def _status(self, text: str) -> None:
        if self._closed:
            return
        try:
            self._status_cb(text)
        except Exception:
            return


def _local(question: str, pack: str) -> str | None:
    from battlebuddy.databank.reason import local_answer

    return local_answer(question, pack)


def _page_lines(store: object | None, game: str | None, question: str) -> list[str]:
    if store is None:
        return []
    result = ask_pages(store, game, question)
    return [f"{hit.title}. {hit.snippet}" for hit in getattr(result, "hits", ())[:3]]


def _answer_saved(
    ocr_text: str,
    game: str | None,
    question: str,
    notes: list[str],
    pages: list[str],
    home: Path,
) -> SnapResult:
    """Re-ask the last snap. Do not grab or store a second fact."""
    from battlebuddy.snap.answer import answer_snap
    from battlebuddy.snap.context import pack_context
    from battlebuddy.snap.facts import SnapFact
    from battlebuddy.snap.pipeline import append_log

    pack = pack_context(ocr_text, notes, pages)
    asked = (question or "").strip() or DEFAULT_QUESTION
    answer = answer_snap(
        asked,
        pack,
        brain=load_brain(home),
        chat_fn=chat,
        local_fn=_local,
        send_image=False,
        key=api_key(),
    )
    fact = SnapFact(id="", game=game or "", text=ocr_text, source="snap", created_at="")
    result = SnapResult(
        text=ocr_text,
        answer=answer,
        fact=fact,
        image_path=home / "snaps",
        game=game,
        question=asked,
    )
    append_log(result, home)
    return result
