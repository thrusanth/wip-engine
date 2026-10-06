"""
Localized Visual Feature Cache — edge-side SKU recognition without cloud inference.

During connected operation, cloud detections "teach" compact SHA-256 layout signatures
into ``local_sku_weights.json``. During a network blackout, the edge camera hashes incoming
frames and performs O(1) dictionary lookup against that cache (no ML runtime on device).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from models.schemas import SKUVisualSignature
from services.sku_catalog import get_sku_profile

DEFAULT_WEIGHTS_PATH = os.getenv("LOCAL_SKU_WEIGHTS_PATH", "local_sku_weights.json")
DEFAULT_CONFIDENCE_THRESHOLD = 0.85
_CACHE_VERSION = 1


def _normalize_image_payload(mock_image_data: str | bytes) -> bytes:
    if isinstance(mock_image_data, str):
        return mock_image_data.encode("utf-8")
    return mock_image_data


def compute_visual_feature_hash(mock_image_data: str | bytes) -> str:
    """Derive a stable visual layout fingerprint from mock frame bytes (cloud + edge)."""
    return hashlib.sha256(_normalize_image_payload(mock_image_data)).hexdigest()


class EdgeInferenceEngine:
    """
    Manages the localized JSON weight cache for cyclical SKU recognition at the edge.

    All cache mutations and reads are serialized with ``asyncio.Lock`` so concurrent
    shelf scans cannot corrupt ``local_sku_weights.json`` during rapid inference bursts.
    """

    def __init__(self, weights_path: str | Path | None = None) -> None:
        self._weights_path = Path(weights_path or DEFAULT_WEIGHTS_PATH)
        self._lock = asyncio.Lock()

    @property
    def weights_path(self) -> Path:
        return self._weights_path

    async def _load_cache_unlocked(self) -> dict[str, Any]:
        if not self._weights_path.exists():
            return {"version": _CACHE_VERSION, "by_feature_hash": {}}
        raw = self._weights_path.read_text(encoding="utf-8")
        if not raw.strip():
            return {"version": _CACHE_VERSION, "by_feature_hash": {}}
        data = json.loads(raw)
        if "by_feature_hash" not in data:
            data["by_feature_hash"] = {}
        data.setdefault("version", _CACHE_VERSION)
        return data

    async def _persist_cache_unlocked(self, data: dict[str, Any]) -> None:
        self._weights_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=True)
        self._weights_path.write_text(payload, encoding="utf-8")

    async def teach_edge_from_cloud(
        self,
        sku_id: str,
        mock_image_data: str | bytes,
        *,
        ean: str = "",
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> SKUVisualSignature:
        """
        Simulate an online cloud model ping: hash the frame and store the signature locally.

        The resulting ``feature_hash`` becomes the dictionary key used later during
        disconnected autonomy inference. ``ean`` is persisted in the JSON cache entry;
        when omitted, it is resolved from the product catalog when available.
        """
        resolved_ean = (ean or "").strip()
        if not resolved_ean:
            resolved_ean = get_sku_profile(sku_id).get("ean", "")

        feature_hash = compute_visual_feature_hash(mock_image_data)
        signature = SKUVisualSignature(
            sku_id=sku_id,
            ean=resolved_ean,
            feature_hash=feature_hash,
            confidence_threshold=confidence_threshold,
        )

        async with self._lock:
            cache = await self._load_cache_unlocked()
            by_hash: dict[str, dict[str, Any]] = cache["by_feature_hash"]
            by_hash[feature_hash] = signature.model_dump()
            await self._persist_cache_unlocked(cache)

        return signature

    async def autonomous_offline_inference(
        self,
        mock_image_data: str | bytes,
    ) -> Optional[SKUVisualSignature]:
        """
        Simulate inference during a network blackout: hash the frame and lookup the cache.

        Returns the cached ``SKUVisualSignature`` when the feature hash matches a taught
        layout; otherwise ``None`` (unknown SKU until cloud teach resumes).
        """
        query_hash = compute_visual_feature_hash(mock_image_data)

        async with self._lock:
            cache = await self._load_cache_unlocked()
            by_hash: dict[str, dict[str, Any]] = cache.get("by_feature_hash", {})
            row = by_hash.get(query_hash)
            if row is None:
                return None
            return SKUVisualSignature.model_validate(row)
