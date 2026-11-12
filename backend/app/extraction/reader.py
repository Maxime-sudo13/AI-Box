"""Lecture locale des documents : texte des PDF, tableaux, et OCR pour les scans et photos.

Rien ne sort du boîtier : pdfplumber lit le texte, Tesseract (installé localement) reconnaît
les caractères des documents numérisés.
"""

import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

# En dessous de ce nombre de caractères par page, le PDF est considéré comme une image.
_MIN_TEXT_PER_PAGE = 40
_MAX_PAGES = 20


@dataclass
class ReadResult:
    method: str  # "text", "ocr" ou "none"
    pages: int
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)
    duration_ms: int = 0
    warning: str | None = None


def ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_images(images, lang: str) -> str:
    import pytesseract

    texts = []
    for image in images:
        # psm 6 : bloc de texte uniforme, adapté aux factures en colonnes alignées.
        texts.append(pytesseract.image_to_string(image, lang=lang, config="--psm 6"))
    return "\n".join(texts)


def _ocr_pdf(data: bytes, lang: str) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    images = [pdf[i].render(scale=300 / 72).to_pil() for i in range(min(len(pdf), _MAX_PAGES))]
    return _ocr_images(images, lang)


def _page_text(page) -> str:
    """Texte d'une page, ligne par ligne, en séparant les blocs côte à côte.

    Deux mots d'une même ligne sont séparés par un espace simple s'ils sont proches, et par
    trois espaces s'ils appartiennent à deux blocs distincts (l'écart dépasse la taille de la
    police) : « Marée Atlantique   Réf. facture : MA-2026-0112 ».
    """
    words = page.extract_words(x_tolerance=1.5, y_tolerance=3, extra_attrs=["size"])
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(word["top"] - rows[-1][0]["top"]) <= 3:
            rows[-1].append(word)
        else:
            rows.append([word])
    lines = []
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        parts = [row[0]["text"]]
        for prev, word in zip(row, row[1:], strict=False):
            gap = word["x0"] - prev["x1"]
            parts.append(("   " if gap > max(prev["size"], word["size"]) * 0.9 else " ") + word["text"])
        lines.append("".join(parts))
    return "\n".join(lines)


def read_document(path: Path, content_type: str, *, ocr_lang: str = "fra") -> ReadResult:
    started = time.monotonic()
    data = path.read_bytes()

    if content_type.startswith("image/"):
        if not ocr_available():
            return ReadResult("none", 1, "", warning="La reconnaissance de caractères (OCR) n'est pas installée.")
        from PIL import Image, ImageOps

        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        text = _ocr_images([image], ocr_lang)
        return ReadResult("ocr", 1, text, duration_ms=int((time.monotonic() - started) * 1000))

    tables: list[list[list[str | None]]] = []
    page_texts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages[:_MAX_PAGES]:
            page_texts.append(_page_text(page))
            tables.extend(page.extract_tables())
    text = "\n".join(page_texts)

    if len(text.strip()) >= _MIN_TEXT_PER_PAGE * max(1, min(pages, _MAX_PAGES)) / 2:
        return ReadResult("text", pages, text, tables, int((time.monotonic() - started) * 1000))

    if not ocr_available():
        return ReadResult(
            "none",
            pages,
            text,
            warning="Ce document est une image et l'OCR n'est pas installé sur le boîtier.",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    text = _ocr_pdf(data, ocr_lang)
    return ReadResult("ocr", pages, text, duration_ms=int((time.monotonic() - started) * 1000))
