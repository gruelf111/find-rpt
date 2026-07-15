from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import fitz


class EvidenceError(ValueError):
    """Base class for safe, user-facing evidence extraction failures."""


class UnreadablePdfError(EvidenceError):
    pass


class EncryptedPdfError(EvidenceError):
    pass


class NoUsableTextError(EvidenceError):
    pass


class InvalidPageRangeError(EvidenceError):
    pass


@dataclass(frozen=True)
class EvidenceWord:
    text: str
    bbox: tuple[float, float, float, float]
    line_number: int
    word_number: int


@dataclass(frozen=True)
class EvidenceBlock:
    block_id: str
    text: str
    bbox: tuple[float, float, float, float]
    block_type: str
    source_block_number: int
    words: tuple[EvidenceWord, ...]


@dataclass(frozen=True)
class EvidencePage:
    page_number: int
    width: float
    height: float
    blocks: tuple[EvidenceBlock, ...]


@dataclass(frozen=True)
class EvidenceDocument:
    document_id: str
    source_filename: str
    page_count: int
    pages: tuple[EvidencePage, ...]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _rounded_bbox(raw: tuple[float, ...]) -> tuple[float, float, float, float]:
    return tuple(round(float(value), 3) for value in raw[:4])  # type: ignore[return-value]


def _bounded_bbox(
    raw: tuple[float, ...], width: float, height: float
) -> tuple[float, float, float, float] | None:
    x0, y0, x1, y1 = _rounded_bbox(raw)
    bounded = (max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1))
    return bounded if bounded[0] < bounded[2] and bounded[1] < bounded[3] else None


def _document_id(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise UnreadablePdfError("PDF cannot be read") from error
    return f"sha256:{digest.hexdigest()}"


def _block_id(
    document_id: str,
    page_number: int,
    order: int,
    source_block_number: int,
    text: str,
    bbox: tuple[float, ...],
) -> str:
    payload = "\x1f".join(
        (
            document_id,
            str(page_number),
            str(order),
            str(source_block_number),
            repr(_rounded_bbox(bbox)),
            text,
        )
    )
    return f"p{page_number:04d}-b{order:04d}-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def parse_page_range(value: str | None, page_count: int) -> tuple[int, ...]:
    """Parse one-based comma-separated pages/ranges, preserving document order."""
    if page_count < 1:
        return ()
    if value is None:
        return tuple(range(1, page_count + 1))
    selected: set[int] = set()
    try:
        for part in value.split(","):
            part = part.strip()
            if not part:
                raise ValueError
            if "-" in part:
                first_text, last_text = part.split("-", 1)
                first, last = int(first_text), int(last_text)
            else:
                first = last = int(part)
            if first < 1 or last < first or last > page_count:
                raise ValueError
            selected.update(range(first, last + 1))
    except ValueError as error:
        raise InvalidPageRangeError(
            f"pages must be one-based and within 1-{page_count}"
        ) from error
    return tuple(sorted(selected))


def _extract_page(page: fitz.Page, document_id: str) -> EvidencePage:
    width, height = round(page.rect.width, 3), round(page.rect.height, 3)
    words_by_block: dict[int, list[EvidenceWord]] = {}
    for raw in page.get_text("words", sort=True):
        block_number, line_number, word_number = map(int, raw[5:8])
        bbox = _bounded_bbox(raw, width, height)
        if bbox is None:
            continue
        words_by_block.setdefault(block_number, []).append(
            EvidenceWord(raw[4], bbox, line_number, word_number)
        )

    blocks: list[EvidenceBlock] = []
    page_number = page.number + 1  # PyMuPDF is zero-based; the public schema is one-based.
    for raw in page.get_text("blocks", sort=True):
        text = raw[4].strip()
        source_number = int(raw[5])
        block_type = int(raw[6])
        if block_type != 0 or not text:
            continue
        bbox = _bounded_bbox(raw, width, height)
        if bbox is None:
            continue
        order = len(blocks) + 1
        blocks.append(
            EvidenceBlock(
                block_id=_block_id(
                    document_id, page_number, order, source_number, text, bbox
                ),
                text=text,
                bbox=bbox,
                block_type="text",
                source_block_number=source_number,
                words=tuple(words_by_block.get(source_number, ())),
            )
        )
    return EvidencePage(
        page_number,
        width,
        height,
        tuple(blocks),
    )


class PdfEvidenceExtractor:
    """Extract immutable, page-scoped text evidence from one local PDF."""

    def extract(
        self,
        path: Path | str,
        *,
        pages: str | None = None,
        source_root: Path | None = None,
    ) -> EvidenceDocument:
        path = Path(path)
        if path.is_symlink():
            raise UnreadablePdfError("symbolic links are not allowed")
        document_id = _document_id(path)
        try:
            with path.open("rb") as source:
                if b"%PDF-" not in source.read(1024):
                    raise UnreadablePdfError("invalid PDF signature")
            document = fitz.open(path)
        except EvidenceError:
            raise
        except Exception as error:
            raise UnreadablePdfError("PDF cannot be opened") from error

        try:
            if document.needs_pass:
                raise EncryptedPdfError("encrypted PDFs are not supported")
            selected = parse_page_range(pages, document.page_count)
            extracted = tuple(_extract_page(document[number - 1], document_id) for number in selected)
            if not any(page.blocks for page in extracted):
                raise NoUsableTextError("selected pages have no usable text layer")
            source_filename = (
                PurePosixPath(source_root.name, path.name).as_posix()
                if source_root is not None
                else path.name
            )
            return EvidenceDocument(document_id, source_filename, document.page_count, extracted)
        except EvidenceError:
            raise
        except Exception as error:
            raise UnreadablePdfError("PDF text extraction failed") from error
        finally:
            document.close()
