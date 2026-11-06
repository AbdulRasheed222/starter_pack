"""Split parsed sections into overlapping passages sized for the embedding model."""

import re
from dataclasses import dataclass

from app.ai.parsing import Section

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


@dataclass
class Passage:
    text: str
    page: int | None
    heading: str | None

    def embedding_text(self) -> str:
        """Text sent to the embedder: the heading adds context the passage often lacks."""
        return f"{self.heading}\n{self.text}" if self.heading else self.text


def chunk_sections(sections: list[Section], size: int, overlap: int) -> list[Passage]:
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    passages: list[Passage] = []
    for section in sections:
        for text in _pack(section.text, size, overlap):
            passages.append(Passage(text, section.page, section.heading))
    return passages


def _pack(text: str, size: int, overlap: int) -> list[str]:
    """Group whole paragraphs into passages of up to `size` words. A paragraph longer than
    `size` is split into word windows that overlap by `overlap` words."""
    paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]
    passages: list[str] = []
    current: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) > size:
            if current:
                passages.append("\n\n".join(current))
                current, current_words = [], 0
            step = size - overlap
            for start in range(0, len(words), step):
                passages.append(" ".join(words[start : start + size]))
                if start + size >= len(words):
                    break
            continue
        if current_words + len(words) > size and current:
            passages.append("\n\n".join(current))
            current, current_words = [], 0
        current.append(paragraph)
        current_words += len(words)
    if current:
        passages.append("\n\n".join(current))
    return passages
