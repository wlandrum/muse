"""Isolated, offline environment for a single eval case.

Points every storage path in `config` at a fresh temp directory, makes sure
Google auth can't succeed (so tools use their local SQLite fallbacks), and
swaps ChromaDB's embedding model for a deterministic offline one.
"""

from __future__ import annotations

import contextlib
import hashlib
import math
import os
import shutil
import tempfile
from typing import Iterator

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from muse.config import config
from muse.rag.voice_engine import VoiceEngine


class HashingEmbeddingFunction(EmbeddingFunction[Documents]):
    """Bag-of-words hashing embedder: deterministic, no model download."""

    DIM = 256

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for doc in input:
            vec = [0.0] * self.DIM
            for token in doc.lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % self.DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    @staticmethod
    def name() -> str:
        return "muse-eval-hashing"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "HashingEmbeddingFunction":
        return HashingEmbeddingFunction()


_PATCHED_ATTRS = (
    "DB_PATH",
    "CHROMADB_PATH",
    "INVOICE_OUTPUT_DIR",
    "GOOGLE_TOKEN_PATH",
)


@contextlib.contextmanager
def sandbox() -> Iterator[str]:
    """Yield a temp dir that all Muse storage points at for the duration."""
    tmp = tempfile.mkdtemp(prefix="muse-eval-")
    saved = {attr: getattr(config, attr) for attr in _PATCHED_ATTRS}
    saved_embedder = VoiceEngine.default_embedding_function
    saved_cloud = os.environ.pop("STREAMLIT_URL", None)
    try:
        config.DB_PATH = os.path.join(tmp, "muse.db")
        config.CHROMADB_PATH = os.path.join(tmp, "chroma_db")
        config.INVOICE_OUTPUT_DIR = os.path.join(tmp, "invoices")
        # Never exists → Google tools fall back to local mode.
        config.GOOGLE_TOKEN_PATH = os.path.join(tmp, "no_token.json")
        VoiceEngine.default_embedding_function = HashingEmbeddingFunction()
        yield tmp
    finally:
        for attr, value in saved.items():
            setattr(config, attr, value)
        VoiceEngine.default_embedding_function = saved_embedder
        if saved_cloud is not None:
            os.environ["STREAMLIT_URL"] = saved_cloud
        # Chroma may hold file handles briefly on Windows.
        shutil.rmtree(tmp, ignore_errors=True)
