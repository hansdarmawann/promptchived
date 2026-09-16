import pytest

from promptchived.services.chunking import chunk_text


def test_chunk_text_keeps_overlap_and_all_content():
    text = " ".join(f"word{i}" for i in range(12))
    chunks = chunk_text(text, max_tokens=5, overlap=2)
    assert [count for _, count in chunks] == [5, 5, 5, 3]
    assert chunks[0][0].split()[-2:] == chunks[1][0].split()[:2]
    assert chunks[-1][0].endswith("word11")


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("hello", max_tokens=5, overlap=5)

