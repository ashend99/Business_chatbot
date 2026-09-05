from app.services.chunking import approx_token_count, chunk_text


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_a_single_chunk():
    text = "Short paragraph that easily fits in one chunk."
    chunks = chunk_text(text, target_tokens=500, overlap_tokens=50)
    assert chunks == [text]


def test_long_text_splits_into_multiple_chunks_within_target_size():
    # 40 short paragraphs -- comfortably larger than one 100-token chunk
    paragraph = "This is a sentence. " * 5
    text = "\n\n".join([paragraph] * 40)

    chunks = chunk_text(text, target_tokens=100, overlap_tokens=20)

    assert len(chunks) > 1
    max_chars = 100 * 4
    # allow the overlap prefix to push a chunk slightly over the raw target
    overlap_chars = 20 * 4
    for chunk in chunks:
        assert len(chunk) <= max_chars + overlap_chars + len(paragraph)


def test_overlap_carries_tail_of_previous_chunk_into_the_next():
    paragraph = "This is a sentence. " * 5
    text = "\n\n".join([paragraph] * 40)

    chunks = chunk_text(text, target_tokens=100, overlap_tokens=20)

    overlap_chars = 20 * 4
    tail_of_first = chunks[0][-overlap_chars:]
    assert tail_of_first.strip() in chunks[1]


def test_single_oversized_paragraph_still_respects_target_size():
    # one paragraph with many sentences, no blank lines at all -- forces the
    # splitter down its fallback separator hierarchy (word/character level)
    # rather than splitting on blank lines
    paragraph = "Sentence number {}. ".format
    text = "".join(paragraph(i) for i in range(200))

    chunks = chunk_text(text, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    max_chars = 50 * 4
    overlap_chars = 10 * 4
    for chunk in chunks:
        assert len(chunk) <= max_chars + overlap_chars + 30


def test_approx_token_count_is_length_over_four():
    assert approx_token_count("abcd") == 1
    assert approx_token_count("a" * 4000) == 1000
    assert approx_token_count("") == 1  # never returns zero/negative
