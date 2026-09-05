"""Text chunker for the documents publish pipeline (Phase 2).

Delegates the actual splitting to `langchain_text_splitters`'
`RecursiveCharacterTextSplitter` (paragraph -> sentence/line -> word ->
character fallback, via its default separator list) instead of a hand-rolled
splitter, per the project's "use prebuilt tools where they fit" direction.

No tokenizer dependency -- token counts are approximated as
`len(text) // 4` (roughly right for English text with the OpenAI
tokenizers). This is a deliberate trade-off to avoid adding `tiktoken` as a
dependency; it means chunk boundaries are approximate, not exact token
counts. Revisit if per-language accuracy ever matters (see plan's
out-of-scope list).
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from common import PROJECT_CONFIG

_chunking_config = PROJECT_CONFIG.get("documents", {}).get("chunking", {})
CHARS_PER_TOKEN = _chunking_config.get("chars_per_token", 4)
DEFAULT_TARGET_TOKENS = _chunking_config.get("target_tokens", 500)
DEFAULT_OVERLAP_TOKENS = _chunking_config.get("overlap_tokens", 50)


def approx_token_count(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def chunk_text(
    text: str, target_tokens: int = DEFAULT_TARGET_TOKENS, overlap_tokens: int = DEFAULT_OVERLAP_TOKENS
) -> list[str]:
    """Split text into chunks of ~target_tokens with ~overlap_tokens of
    context carried across each boundary. target_tokens/overlap_tokens are
    converted to character counts via CHARS_PER_TOKEN since the underlying
    splitter operates on characters, not tokens.
    """
    text = text.strip()
    if not text:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=target_tokens * CHARS_PER_TOKEN,
        chunk_overlap=overlap_tokens * CHARS_PER_TOKEN,
    )
    return splitter.split_text(text)
