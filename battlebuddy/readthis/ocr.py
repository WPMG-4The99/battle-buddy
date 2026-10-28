"""Local OCR only. Windows.Media.Ocr first. Tesseract if that engine is missing."""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from battlebuddy.readthis.capture import ReadError
from battlebuddy.readthis.clean import join_ocr_lines
from battlebuddy.readthis.hints import ocr_help, pillow_help, tesseract_help

INVERT_MEAN_BELOW = 140.0

# Windows PowerShell 5.1 can call WinRT. PowerShell 7 cannot.
# Two backticks so the file PowerShell runs contains one backtick in IAsyncOperation`1.
_WINDOWS_OCR_PS1 = r"""
param([Parameter(Mandatory = $true)][string]$Path)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$awaiter = [WindowsRuntimeSystemExtensions].GetMember("GetAwaiter", "Method", "Public,Static") |
    Where-Object { $_.GetParameters()[0].ParameterType.Name -eq "IAsyncOperation``1" } |
    Select-Object -First 1
function Invoke-Async([object]$AsyncTask, [Type]$As) {
    return $awaiter.MakeGenericMethod($As).Invoke($null, @($AsyncTask)).GetResult()
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {
    Write-Error "NO_ENGINE"
    exit 2
}
$full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
$file = Invoke-Async ([Windows.Storage.StorageFile]::GetFileFromPathAsync($full)) ([Windows.Storage.StorageFile])
$stream = Invoke-Async ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Invoke-Async ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Invoke-Async ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Invoke-Async ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$chunks = New-Object System.Collections.Generic.List[string]
foreach ($line in @($result.Lines)) {
    $text = [string]$line.Text
    if ($text) { $chunks.Add($text) }
}
if ($chunks.Count -eq 0 -and $result.Text) {
    $chunks.Add([string]$result.Text)
}
Write-Output ($chunks -join "`n")
"""


def should_invert(mean: float) -> bool:
    """Light glyphs on a dark game panel. Invert so OCR sees dark-on-light."""
    return float(mean) < INVERT_MEAN_BELOW


def prepare_for_ocr(image: object) -> object:
    """2x, grayscale, auto-contrast. Invert when the panel is dark."""
    try:
        from PIL import Image, ImageOps, ImageStat
    except ImportError as exc:
        raise ReadError(pillow_help()) from exc
    gray = image if getattr(image, "mode", "") == "L" else ImageOps.grayscale(image)
    width, height = gray.size
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
    gray = gray.resize((max(1, width * 2), max(1, height * 2)), resample)
    gray = ImageOps.autocontrast(gray)
    mean = float(ImageStat.Stat(gray).mean[0])
    if should_invert(mean):
        gray = ImageOps.invert(gray)
    return gray


def recognize(image: object) -> str:
    """OCR one prepared-or-raw image. Raises ReadError naming the missing extra."""
    prepared = prepare_for_ocr(image)
    errors: list[str] = []
    if sys.platform == "win32":
        try:
            return _recognize_windows(prepared)
        except ImportError:
            errors.append("winsdk is not installed")
        except Exception as exc:
            errors.append(f"winsdk OCR failed ({exc})")
        try:
            return _recognize_windows_shell(prepared)
        except Exception as exc:
            errors.append(f"Windows OCR failed ({exc})")
    try:
        return _recognize_tesseract(prepared)
    except ImportError:
        errors.append("pytesseract is not installed")
    except Exception as exc:
        errors.append(f"Tesseract failed ({exc})")
    detail = "; ".join(errors) if errors else "no engine"
    raise ReadError(f"{ocr_help()} ({detail})")


def _recognize_tesseract(image: object) -> str:
    import pytesseract

    try:
        text = pytesseract.image_to_string(image)
    except pytesseract.TesseractNotFoundError as exc:
        raise ReadError(tesseract_help()) from exc
    return str(text or "")


def _recognize_windows_shell(image: object) -> str:
    """Windows.Media.Ocr through Windows PowerShell when winsdk has no wheel."""
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise ReadError("Windows PowerShell is missing, so Windows OCR cannot run.")
    folder = Path(tempfile.mkdtemp(prefix="battlebuddy-read-"))
    image_path = folder / "grab.png"
    script_path = folder / "ocr.ps1"
    try:
        image.save(image_path, format="PNG")  # type: ignore[attr-defined]
        script_path.write_text(_WINDOWS_OCR_PS1, encoding="utf-8")
        kwargs: dict[str, object] = {
            "timeout": 20,
            "check": False,
            "capture_output": True,
        }
        if sys.platform == "win32":
            from battlebuddy.voice.tts import hidden_console_run_kwargs

            kwargs.update(hidden_console_run_kwargs())
        proc = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-Path",
                str(image_path),
            ],
            **kwargs,  # type: ignore[arg-type]
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    raw = _decode_output(getattr(proc, "stdout", b"") or b"")
    if proc.returncode != 0 and not raw.strip():
        err = _decode_output(getattr(proc, "stderr", b"") or b"").strip()
        detail = err.splitlines()[-1] if err else f"exit {proc.returncode}"
        raise ReadError(detail)
    return raw


def _decode_output(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if b"\x00" in raw[:80]:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _recognize_windows(image: object) -> str:
    import asyncio

    png = _png_bytes(image)

    async def _run() -> str:
        _init_com()
        bitmap = await _bitmap_from_png(png)
        engine = _ocr_engine()
        result = await engine.recognize_async(bitmap)
        return _result_text(result)

    return asyncio.run(_run())


def _png_bytes(image: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")  # type: ignore[attr-defined]
    return buffer.getvalue()


def _init_com() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except OSError:
        return


def _ocr_engine() -> object:
    from winsdk.windows.globalization import Language
    from winsdk.windows.media.ocr import OcrEngine

    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is not None:
        return engine
    for tag in ("en-US", "en"):
        try:
            engine = OcrEngine.try_create_from_language(Language(tag))
        except Exception:
            engine = None
        if engine is not None:
            return engine
    raise ReadError(
        "Windows OCR has no language pack. Add an OCR language in Windows Settings, "
        "or install Tesseract and pytesseract."
    )


async def _bitmap_from_png(data: bytes) -> object:
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    _write_bytes(writer, data)
    await writer.store_async()
    await writer.flush_async()
    try:
        writer.detach_stream()
    except Exception:
        pass
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    return await decoder.get_software_bitmap_async()


def _write_bytes(writer: object, data: bytes) -> None:
    try:
        writer.write_bytes(data)  # type: ignore[attr-defined]
        return
    except (TypeError, OverflowError):
        pass
    try:
        writer.write_bytes(bytearray(data))  # type: ignore[attr-defined]
        return
    except (TypeError, OverflowError):
        writer.write_bytes(list(data))  # type: ignore[attr-defined]


def _result_text(result: object) -> str:
    lines = getattr(result, "lines", None)
    if not lines:
        return str(getattr(result, "text", "") or "")
    rows: list[tuple[str, float | None, float | None]] = []
    for line in lines:
        rows.append(_line_row(line))
    joined = join_ocr_lines(rows)
    if joined.strip():
        return joined
    return str(getattr(result, "text", "") or "")


def _line_row(line: object) -> tuple[str, float | None, float | None]:
    words = list(getattr(line, "words", []) or [])
    text = " ".join(
        (getattr(word, "text", "") or "").strip()
        for word in words
        if (getattr(word, "text", "") or "").strip()
    )
    if not text:
        text = str(getattr(line, "text", "") or "").strip()
    top: float | None = None
    height: float | None = None
    if words:
        box = getattr(words[0], "bounding_rect", None)
        if box is not None:
            try:
                top = float(box.y)
                height = float(box.height) or 1.0
            except (TypeError, ValueError, AttributeError):
                top = None
                height = None
    return text, top, height
