from collections.abc import Iterable

from .chunking import chunk_text
from ..config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self.settings.model_cache.mkdir(parents=True, exist_ok=True)
            self._model = SentenceTransformer(
                self.settings.embedding_model,
                device=self.settings.embedding_device,
                cache_folder=str(self.settings.model_cache),
            )
        return self._model

    def encode_passages(self, texts: Iterable[str]) -> list[list[float]]:
        values = [f"passage: {text}" for text in texts]
        if not values:
            return []
        vectors = self.model.encode(
            values,
            batch_size=self.settings.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def encode_query(self, query: str) -> list[float]:
        vector = self.model.encode(
            [f"query: {query}"], normalize_embeddings=True, show_progress_bar=False
        )[0]
        return vector.tolist()

    def tokenizer_chunks(self, text: str) -> list[tuple[str, int]]:
        tokenizer = self.model.tokenizer
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        size = self.settings.chunk_tokens
        overlap = self.settings.chunk_overlap
        if not token_ids:
            return []
        output: list[tuple[str, int]] = []
        start = 0
        while start < len(token_ids):
            piece = token_ids[start : start + size]
            output.append((tokenizer.decode(piece, skip_special_tokens=True), len(piece)))
            if start + size >= len(token_ids):
                break
            start += size - overlap
        return output


def cheap_chunks(text: str) -> list[tuple[str, int]]:
    settings = get_settings()
    return chunk_text(text, settings.chunk_tokens, settings.chunk_overlap)

