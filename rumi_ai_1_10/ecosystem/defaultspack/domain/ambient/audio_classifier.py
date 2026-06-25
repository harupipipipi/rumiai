from __future__ import annotations

import base64
import math
import struct
from typing import Any, Iterable


EMBEDDING_DIM = 16


def embedding_from_payload(payload: dict[str, Any]) -> list[float]:
    """Extract a compact audio embedding from client-side audio features.

    The ambient wake path deliberately avoids text matching. Clients may send a
    precomputed embedding, normalized samples, or PCM16 base64; this helper
    turns only audio features into a comparable vector and never returns text.
    """

    for key in ("audio_embedding", "embedding", "audio_features"):
        value = payload.get(key)
        vector = _numeric_vector(value)
        if vector:
            return normalize(vector)
    samples = _numeric_vector(payload.get("samples"))
    if samples:
        return normalize(_sample_energy_embedding(samples))
    pcm16 = _pcm16_samples(payload.get("pcm16_base64") or payload.get("audio_pcm16_base64"))
    if pcm16:
        return normalize(_sample_energy_embedding(pcm16))
    return []


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_items = [float(item) for item in left]
    right_items = [float(item) for item in right]
    if not left_items or not right_items:
        return 0.0
    count = min(len(left_items), len(right_items))
    dot = sum(left_items[index] * right_items[index] for index in range(count))
    left_norm = math.sqrt(sum(item * item for item in left_items[:count]))
    right_norm = math.sqrt(sum(item * item for item in right_items[:count]))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def normalize(vector: Iterable[float]) -> list[float]:
    items = [float(item) for item in vector]
    if not items:
        return []
    norm = math.sqrt(sum(item * item for item in items))
    if norm <= 0:
        return [0.0 for _ in items]
    return [item / norm for item in items]


def _numeric_vector(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def _sample_energy_embedding(samples: list[float]) -> list[float]:
    if not samples:
        return []
    stride = max(1, math.ceil(len(samples) / EMBEDDING_DIM))
    features: list[float] = []
    for bucket in range(EMBEDDING_DIM):
        chunk = samples[bucket * stride : (bucket + 1) * stride]
        if not chunk:
            features.append(0.0)
            continue
        mean_abs = sum(abs(item) for item in chunk) / len(chunk)
        rms = math.sqrt(sum(item * item for item in chunk) / len(chunk))
        features.append((mean_abs + rms) / 2.0)
    return features


def _pcm16_samples(value: Any) -> list[float]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        return []
    usable = len(raw) - (len(raw) % 2)
    if usable <= 0:
        return []
    result: list[float] = []
    for (sample,) in struct.iter_unpack("<h", raw[:usable]):
        result.append(sample / 32768.0)
    return result
