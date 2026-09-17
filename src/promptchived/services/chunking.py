import re

TOKEN_PATTERN = re.compile(r"\S+")


def chunk_text(text: str, max_tokens: int = 400, overlap: int = 50) -> list[tuple[str, int]]:
    """Split text deterministically; the embedding worker may use the model tokenizer later."""
    if max_tokens <= 0 or overlap < 0 or overlap >= max_tokens:
        raise ValueError("Invalid chunk configuration")
    matches = list(TOKEN_PATTERN.finditer(text))
    if not matches:
        return []
    output: list[tuple[str, int]] = []
    start = 0
    while start < len(matches):
        end = min(start + max_tokens, len(matches))
        char_start = matches[start].start()
        char_end = matches[end - 1].end()
        output.append((text[char_start:char_end], end - start))
        if end == len(matches):
            break
        start = end - overlap
    return output
