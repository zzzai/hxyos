from __future__ import annotations

import re
from dataclasses import dataclass


_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])")


@dataclass(frozen=True)
class MaterialChunkDraft:
    chunk_index: int
    heading: str
    content: str


def _split_long_paragraph(paragraph: str, target_chars: int) -> list[str]:
    if len(paragraph) <= target_chars:
        return [paragraph]
    sentences = [part.strip() for part in _SENTENCE_END.split(paragraph) if part.strip()]
    pieces: list[str] = []
    current = ""
    for sentence in sentences or [paragraph]:
        if len(sentence) > target_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[index : index + target_chars]
                for index in range(0, len(sentence), target_chars)
            )
            continue
        candidate = sentence if not current else current + sentence
        if current and len(candidate) > target_chars:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _paragraphs(markdown: str, target_chars: int) -> list[tuple[str, str]]:
    heading = ""
    buffer: list[str] = []
    items: list[tuple[str, str]] = []

    def flush() -> None:
        if not buffer:
            return
        paragraph = " ".join(line.strip() for line in buffer if line.strip()).strip()
        buffer.clear()
        for piece in _split_long_paragraph(paragraph, target_chars):
            if piece:
                items.append((heading, piece))

    for raw_line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        match = _HEADING.match(line)
        if match:
            flush()
            heading = match.group(1).strip()[:300]
            continue
        if not line:
            flush()
            continue
        buffer.append(line)
    flush()
    return items


def chunk_markdown(
    markdown: str,
    *,
    target_chars: int = 900,
    overlap_chars: int = 120,
    max_chunks: int = 500,
    default_heading: str = "",
) -> list[MaterialChunkDraft]:
    if target_chars < 32:
        raise ValueError("target_chars must be at least 32")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than target_chars")
    if max_chunks < 1:
        raise ValueError("max_chunks must be positive")

    segments = _paragraphs(markdown, target_chars)
    chunks: list[MaterialChunkDraft] = []
    current_heading = ""
    current_parts: list[str] = []

    def flush(*, keep_overlap: bool) -> None:
        nonlocal current_parts
        content = "\n\n".join(current_parts).strip()
        if content and len(chunks) < max_chunks:
            chunks.append(
                MaterialChunkDraft(
                    chunk_index=len(chunks),
                    heading=(current_heading or default_heading).strip()[:300],
                    content=content,
                )
            )
        if keep_overlap and current_parts and overlap_chars:
            tail = current_parts[-1][-overlap_chars:].strip()
            current_parts = [tail] if tail else []
        else:
            current_parts = []

    for heading, paragraph in segments:
        if len(chunks) >= max_chunks:
            break
        if current_parts and heading != current_heading:
            flush(keep_overlap=False)
        current_heading = heading
        candidate = paragraph if not current_parts else "\n\n".join([*current_parts, paragraph])
        if current_parts and len(candidate) > target_chars:
            flush(keep_overlap=True)
        current_parts.append(paragraph)
    if len(chunks) < max_chunks:
        flush(keep_overlap=False)
    return chunks
