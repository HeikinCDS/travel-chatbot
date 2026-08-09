"""Local semantic retrieval for the curated JomVoyage attraction database."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Any, Callable, Mapping, Sequence

import numpy as np


DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def attraction_search_text(attraction: Mapping[str, Any]) -> str:
    """Create the grounded text represented by one attraction embedding."""

    fields = (
        attraction.get("attraction_name"),
        attraction.get("primary_category"),
        attraction.get("interests_tags"),
        attraction.get("short_description"),
        attraction.get("city_district"),
        attraction.get("state_territory"),
        attraction.get("accessibility_notes"),
    )
    return ". ".join(
        str(value).strip()
        for value in fields
        if value is not None and str(value).strip()
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default_model_loader(model_name: str, local_files_only: bool):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        model_name,
        device=os.getenv("SEMANTIC_DEVICE", "cpu"),
        local_files_only=local_files_only,
    )


class SemanticRanker:
    """Build and query cached attraction embeddings without an LLM."""

    def __init__(
        self,
        model_name: str | None = None,
        *,
        model_loader: Callable[[str, bool], Any] | None = None,
    ) -> None:
        self.model_name = (
            model_name
            or os.getenv("SEMANTIC_MODEL")
            or DEFAULT_MODEL_NAME
        )
        self._model_loader = model_loader or _default_model_loader
        self._model = None
        self._unavailable = False

    def _load_model(self, *, allow_download: bool):
        if self._model is not None:
            return self._model
        if self._unavailable and not allow_download:
            return None
        try:
            self._model = self._model_loader(
                self.model_name,
                not allow_download,
            )
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            self._unavailable = True
            return None
        return self._model

    @staticmethod
    def _create_table(connection: sqlite3.Connection) -> None:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS attraction_embeddings (
                attraction_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                PRIMARY KEY (attraction_id, model_name)
            )
        """)

    def rebuild_index(
        self,
        connection: sqlite3.Connection,
        *,
        allow_download: bool = True,
    ) -> int:
        """Encode all curated attractions and store normalized vectors."""

        model = self._load_model(allow_download=allow_download)
        if model is None:
            raise RuntimeError(
                "The sentence embedding model could not be loaded."
            )

        connection.row_factory = sqlite3.Row
        attractions = connection.execute("""
            SELECT
                attraction_id, attraction_name, primary_category,
                interests_tags, short_description, city_district,
                state_territory, accessibility_notes
            FROM attractions
            ORDER BY attraction_id
        """).fetchall()
        texts = [attraction_search_text(dict(row)) for row in attractions]
        if not texts:
            return 0

        vectors = np.asarray(
            model.encode(
                texts,
                batch_size=32,
                show_progress_bar=True,
                normalize_embeddings=True,
            ),
            dtype=np.float32,
        )
        if vectors.ndim != 2 or vectors.shape[0] != len(attractions):
            raise ValueError("The embedding model returned an invalid shape.")

        self._create_table(connection)
        connection.execute(
            "DELETE FROM attraction_embeddings WHERE model_name = ?",
            (self.model_name,),
        )
        connection.executemany("""
            INSERT INTO attraction_embeddings (
                attraction_id, model_name, content_hash,
                dimensions, embedding
            ) VALUES (?, ?, ?, ?, ?)
        """, [
            (
                str(attraction["attraction_id"]),
                self.model_name,
                _content_hash(text),
                int(vector.shape[0]),
                vector.tobytes(),
            )
            for attraction, text, vector in zip(
                attractions,
                texts,
                vectors,
                strict=True,
            )
        ])
        connection.commit()
        return len(attractions)

    def scores(
        self,
        connection: sqlite3.Connection,
        attractions: Sequence[Mapping[str, Any]],
        query_text: str | None,
    ) -> dict[str, float]:
        """Return cosine-similarity scores for valid cached embeddings."""

        if not isinstance(query_text, str) or not query_text.strip():
            return {}
        if not attractions:
            return {}
        connection.row_factory = sqlite3.Row
        table_exists = connection.execute("""
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'attraction_embeddings'
        """).fetchone()
        if not table_exists:
            return {}

        attraction_by_id = {
            str(item["attraction_id"]): item
            for item in attractions
        }
        placeholders = ",".join("?" for _ in attraction_by_id)
        rows = connection.execute(f"""
            SELECT attraction_id, content_hash, dimensions, embedding
            FROM attraction_embeddings
            WHERE model_name = ?
              AND attraction_id IN ({placeholders})
        """, (self.model_name, *attraction_by_id)).fetchall()

        valid_rows = []
        for row in rows:
            attraction_id = str(row["attraction_id"])
            current_text = attraction_search_text(
                attraction_by_id[attraction_id]
            )
            if row["content_hash"] == _content_hash(current_text):
                valid_rows.append(row)
        if not valid_rows:
            return {}

        model = self._load_model(allow_download=False)
        if model is None:
            return {}
        query_vector = np.asarray(
            model.encode(
                [query_text],
                show_progress_bar=False,
                normalize_embeddings=True,
            )[0],
            dtype=np.float32,
        )

        scores = {}
        for row in valid_rows:
            dimensions = int(row["dimensions"])
            vector = np.frombuffer(row["embedding"], dtype=np.float32)
            if vector.shape != (dimensions,) or query_vector.shape != vector.shape:
                continue
            scores[str(row["attraction_id"])] = float(
                np.dot(query_vector, vector)
            )
        return scores
