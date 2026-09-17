from collections.abc import Iterable
from pathlib import Path

from .chunking import chunk_text
from ..config import get_settings


def cached_model_path(cache_root: Path, model_name: str) -> Path | None:
    model_cache = cache_root / f"models--{model_name.replace('/', '--')}"
    main_ref = model_cache / "refs" / "main"
    if not main_ref.is_file():
        return None
    revision = main_ref.read_text(encoding="utf-8").strip()
    snapshot = (model_cache / "snapshots" / revision).resolve()
    snapshots_root = (model_cache / "snapshots").resolve()
    if not snapshot.is_relative_to(snapshots_root):
        return None
    if (snapshot / "config.json").is_file() and (snapshot / "modules.json").is_file():
        return snapshot
    return None


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self.settings.model_cache.mkdir(parents=True, exist_ok=True)
            local_model = cached_model_path(
                self.settings.model_cache, self.settings.embedding_model
            )
            self._model = SentenceTransformer(
                str(local_model) if local_model else self.settings.embedding_model,
                device=self.settings.embedding_device,
                cache_folder=str(self.settings.model_cache),
                local_files_only=local_model is not None,
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
        # Calling encode() on a long message emits a misleading max-length warning
        # before we split it. Tokenize first, then decode bounded pieces.
        tokens = tokenizer.tokenize(text, add_special_tokens=False)
        size = self.settings.chunk_tokens
        overlap = self.settings.chunk_overlap
        if not tokens:
            return []
        output: list[tuple[str, int]] = []
        start = 0
        while start < len(tokens):
            piece = tokens[start : start + size]
            output.append((tokenizer.convert_tokens_to_string(piece), len(piece)))
            if start + size >= len(tokens):
                break
            start += size - overlap
        return output


def cheap_chunks(text: str) -> list[tuple[str, int]]:
    settings = get_settings()
    return chunk_text(text, settings.chunk_tokens, settings.chunk_overlap)
