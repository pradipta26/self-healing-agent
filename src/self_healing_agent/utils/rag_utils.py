from __future__ import annotations

import os
from functools import lru_cache

from google import genai
from google.genai import types


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 1536


@lru_cache(maxsize=1)
def _embedding_client() -> genai.Client:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is not set")

    return genai.Client(api_key=api_key)


def embed_text(
    text: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    output_dimensionality: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> list[float]:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("text must not be empty")

    response = _embedding_client().models.embed_content(
        model=model,
        contents=cleaned_text,
        config=types.EmbedContentConfig(
            output_dimensionality=output_dimensionality,
        ),
    )

    if not response.embeddings:
        raise ValueError("Embedding response did not include any vectors")

    return list(response.embeddings[0].values)

