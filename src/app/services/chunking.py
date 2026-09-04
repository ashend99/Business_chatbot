"""Pure-function text chunker for the documents publish pipeline (Phase 2).

No tokenizer dependency -- token counts are approximated as
`len(text) // 4` (roughly right for English text with the OpenAI
tokenizers). This is a deliberate trade-off to avoid adding `tiktoken` as a
dependency; it means chunk boundaries are approximate, not exact token
counts. Revisit if per-language accuracy ever matters (see plan's
out-of-scope list).
"""

import re

CHARS_PER_TOKEN = 4


def approx_token_count(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _split_paragraphs(text: str) -> list[str]:
    # blank-line-separated paragraphs first; fall back to single newlines
    # for text that has no blank lines at all.
    raw = text.replace("\r\n", "\n")
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in raw.split("\n") if p.strip()]
    return paragraphs


def _split_sentences(paragraph: str) -> list[str]:
    # crude sentence splitter -- good enough for chunk-boundary purposes,
    # not meant to be linguistically precise.
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    return [s.strip() for s in sentences if s.strip()]


def _hard_wrap(text: str, max_chars: int) -> list[str]:
    return [text[i : i + max_chars].strip() for i in range(0, len(text), max_chars)]


def chunk_text(text: str, target_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    """Recursive splitter: paragraph boundaries first, sentence boundaries
    for any paragraph that alone exceeds the target size, hard character
    wrap only as a last resort. Chunks are joined greedily up to
    `target_tokens`, with the tail of each chunk repeated as overlap at the
    start of the next (~`overlap_tokens`).
    """
    text = text.strip()
    if not text:
        return []

    max_chars = target_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN

    # flatten the source text into a list of units no larger than max_chars
    units: list[str] = []
    for paragraph in _split_paragraphs(text):
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        for sentence in _split_sentences(paragraph):
            if len(sentence) <= max_chars:
                units.append(sentence)
            else:
                units.extend(_hard_wrap(sentence, max_chars))

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            chunks.append(current)
            # seed the next chunk with the trailing ~overlap_chars of the one
            # just closed, so context carries across the boundary
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail}\n\n{unit}" if tail else unit
    if current:
        chunks.append(current)

    return chunks
