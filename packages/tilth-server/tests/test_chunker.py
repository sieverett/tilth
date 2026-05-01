"""Tests for text chunking."""


from tilth_server.ingest.chunker import ChunkedRecord, chunk_text

CHUNK_SIZE = 32 * 1024  # 32KB


class TestChunkText:
    def test_small_text_returns_single_chunk(self) -> None:
        text = "This is a short sentence."
        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0
        assert chunks[0].chunk_total == 1
        assert chunks[0].chunk_group_id is not None

    def test_large_text_splits_into_multiple_chunks(self) -> None:
        # Create text that's ~3x the chunk size
        sentence = "This is a test sentence. "
        repeat_count = (CHUNK_SIZE * 3) // len(sentence.encode("utf-8"))
        text = sentence * repeat_count

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        assert len(chunks) >= 3

        # All chunks share the same group ID
        group_ids = {c.chunk_group_id for c in chunks}
        assert len(group_ids) == 1

        # Indices are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.chunk_total == len(chunks)

    def test_splits_on_sentence_boundaries(self) -> None:
        # Build text where a sentence boundary falls before the chunk limit
        short_part = "First sentence. " * 100
        # Make sure it's under one chunk
        assert len(short_part.encode("utf-8")) < CHUNK_SIZE

        # Now add enough to push past the limit
        long_part = "Second part is longer. " * 2000
        text = short_part + long_part

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        assert len(chunks) >= 2

        # First chunk should end at a sentence boundary (ends with ". " or ".")
        first = chunks[0].text.rstrip()
        assert first.endswith(".") or first.endswith("?") or first.endswith("!")

    def test_no_content_lost(self) -> None:
        sentence = "Word number one. "
        repeat_count = (CHUNK_SIZE * 2) // len(sentence.encode("utf-8")) + 10
        text = sentence * repeat_count

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        reassembled = "".join(c.text for c in chunks)
        assert reassembled == text

    def test_each_chunk_under_size_limit(self) -> None:
        sentence = "A moderately long sentence for testing purposes. "
        repeat_count = (CHUNK_SIZE * 4) // len(sentence.encode("utf-8"))
        text = sentence * repeat_count

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        for chunk in chunks:
            # Allow small overflow for sentence boundary finding
            assert len(chunk.text.encode("utf-8")) <= CHUNK_SIZE * 1.1

    def test_empty_text_returns_single_empty_chunk(self) -> None:
        chunks = chunk_text("", chunk_size=CHUNK_SIZE)
        assert len(chunks) == 1
        assert chunks[0].text == ""

    def test_text_exactly_at_limit(self) -> None:
        # Create text exactly at chunk size
        text = "x" * CHUNK_SIZE
        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        assert len(chunks) == 1

    def test_unicode_text_splits_by_bytes(self) -> None:
        # Unicode chars are multi-byte — ensure we split by bytes not chars
        # Each emoji is 4 bytes
        emoji_sentence = "Hello world! " + "\U0001f600" * 100 + ". "
        repeat_count = (CHUNK_SIZE * 2) // len(emoji_sentence.encode("utf-8")) + 5
        text = emoji_sentence * repeat_count

        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        assert len(chunks) >= 2
        # No content lost
        reassembled = "".join(c.text for c in chunks)
        assert reassembled == text

    def test_custom_chunk_size(self) -> None:
        text = "Short. " * 100
        chunks = chunk_text(text, chunk_size=50)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text.encode("utf-8")) <= 50 * 1.1

    def test_newline_is_valid_split_point(self) -> None:
        # Text with newlines as natural boundaries
        lines = ["Line number " + str(i) + ".\n" for i in range(500)]
        text = "".join(lines)
        chunks = chunk_text(text, chunk_size=CHUNK_SIZE)
        if len(chunks) > 1:
            # First chunk should end at a newline or sentence boundary
            first = chunks[0].text.rstrip()
            assert first.endswith(".") or first.endswith("\n") or first.endswith("!")


class TestChunkedRecord:
    def test_dataclass_fields(self) -> None:
        record = ChunkedRecord(
            text="hello",
            chunk_group_id="g1",
            chunk_index=0,
            chunk_total=3,
        )
        assert record.text == "hello"
        assert record.chunk_group_id == "g1"
        assert record.chunk_index == 0
        assert record.chunk_total == 3
