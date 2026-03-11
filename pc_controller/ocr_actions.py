from __future__ import annotations

from dataclasses import dataclass
import unicodedata

try:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapAlphaMode, BitmapDecoder, BitmapPixelFormat
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
except ImportError:  # pragma: no cover - dependency is optional at import time
    Language = None
    BitmapAlphaMode = None
    BitmapDecoder = None
    BitmapPixelFormat = None
    OcrEngine = None
    DataWriter = None
    InMemoryRandomAccessStream = None


@dataclass(slots=True)
class OCRResult:
    text: str
    lines: list[str]


def _ensure_ocr() -> None:
    if OcrEngine is None:
        raise RuntimeError('Windows OCR недоступен. Проверьте, что пакет winsdk установлен.')


async def extract_text_from_image_bytes(image_bytes: bytes, language_tag: str | None = None) -> OCRResult:
    _ensure_ocr()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(image_bytes)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    writer.close()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async(
        BitmapPixelFormat.BGRA8,
        BitmapAlphaMode.PREMULTIPLIED,
    )

    candidate_tags = _build_candidate_language_tags(language_tag)
    results: list[OCRResult] = []

    for tag in candidate_tags:
        try:
            engine = OcrEngine.try_create_from_language(Language(tag))
        except Exception:
            engine = None
        if engine is None:
            continue
        raw_result = await engine.recognize_async(bitmap)
        results.append(_to_ocr_result(raw_result))

    if not results:
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise RuntimeError('Не удалось инициализировать OCR-движок Windows.')
        raw_result = await engine.recognize_async(bitmap)
        return _to_ocr_result(raw_result)

    return max(results, key=_score_ocr_result)


def find_matching_lines(lines: list[str], query: str) -> list[str]:
    needle = ' '.join((query or '').lower().split())
    if not needle:
        return []
    matches = []
    for line in lines:
        compact = ' '.join(line.lower().split())
        if needle in compact:
            matches.append(line)
    return matches


def _build_candidate_language_tags(language_tag: str | None) -> list[str]:
    tags: list[str] = []

    if language_tag:
        normalized = str(language_tag).strip()
        if normalized:
            tags.append(normalized)

    try:
        available = OcrEngine.available_recognizer_languages
    except Exception:
        available = None

    if available is not None:
        for index in range(getattr(available, 'size', 0)):
            try:
                candidate = str(available.get_at(index).language_tag or '').strip()
            except Exception:
                candidate = ''
            if candidate and candidate not in tags:
                tags.append(candidate)

    return tags


def _to_ocr_result(raw_result) -> OCRResult:
    lines = [line.text.strip() for line in raw_result.lines if line.text and line.text.strip()]
    text = (raw_result.text or '').strip()
    if not text and lines:
        text = '\n'.join(lines)
    return OCRResult(text=text, lines=lines)


def _score_ocr_result(result: OCRResult) -> tuple[int, int, int, int, int, int, int, int]:
    clean_alpha_chars = 0
    clean_digit_chars = 0
    mixed_script_penalty = 0
    mixed_alnum_penalty = 0
    punctuation_penalty = 0
    total_alpha_chars = 0
    total_alnum_chars = 0

    for token in result.text.split():
        letters = [ch for ch in token if ch.isalpha()]
        digits = [ch for ch in token if ch.isdigit()]
        other_chars = [ch for ch in token if not ch.isalnum()]
        scripts = {_detect_script(ch) for ch in letters}

        total_alpha_chars += len(letters)
        total_alnum_chars += len(letters) + len(digits)
        punctuation_penalty += len(other_chars)

        if letters and digits:
            mixed_alnum_penalty += 1
        if len(scripts) > 1:
            mixed_script_penalty += 1

        if letters and not digits and not other_chars and len(scripts) == 1:
            clean_alpha_chars += len(letters)
        if digits and not letters and not other_chars:
            clean_digit_chars += len(digits)

    return (
        clean_alpha_chars,
        clean_digit_chars,
        -mixed_script_penalty,
        -mixed_alnum_penalty,
        -punctuation_penalty,
        total_alpha_chars,
        total_alnum_chars,
        len(result.lines),
    )


def _detect_script(ch: str) -> str:
    name = unicodedata.name(ch, '')
    if 'CYRILLIC' in name:
        return 'cyrillic'
    if 'LATIN' in name:
        return 'latin'
    return 'other'
