"""Single EAN / SKU -> human-readable product name lookup for reconciliation events.

Sources, in priority order:
1. Edge CV catalog (``services/cv_catalog.py``) - every product the camera can recognise.
2. Shopfloor master catalog (``services/shopfloor_catalog.py``).
3. Legacy ledger SKUs below (mock names; these seed ledger rows never had a display name).
"""

from __future__ import annotations

from typing import Optional

from services.cv_catalog import CV_PRODUCT_CATALOG
from services.shopfloor_catalog import catalog_by_ean

_EAN_PREFIX = "EAN-"

# Mock names for the legacy seed ledger (see _LEGACY_LEDGER in api_bouncer_engine.py).
LEGACY_PRODUCT_NAMES_BY_EAN: dict[str, str] = {
    "5051410987654": "Spring Water 6-Pack",
    "5051420123456": "Baked Beans 4-Pack",
    "5051410112233": "Lager 4-Pack",
    "5051410223344": "Cider 4-Pack",
    "5051410998877": "Beer 10-Pack",
}
LEGACY_PRODUCT_NAMES_BY_SKU: dict[str, str] = {
    "SKU-WATER-6PK": "Spring Water 6-Pack",
    "SKU-BEANS-4PK": "Baked Beans 4-Pack",
    "SKU-LAGER-4PK": "Lager 4-Pack",
    "SKU-CIDER-4PK": "Cider 4-Pack",
    "SKU-BEER-10PK": "Beer 10-Pack",
}


def _clean_ean(value: Optional[str]) -> str:
    text = str(value or "").strip()
    if text.upper().startswith(_EAN_PREFIX):
        text = text[len(_EAN_PREFIX):]
    return text


def product_name_for_ean(ean: Optional[str]) -> Optional[str]:
    """Product name for a bare or ``EAN-`` prefixed barcode, or None when unmapped."""
    code = _clean_ean(ean)
    if not code:
        return None
    for item in CV_PRODUCT_CATALOG.values():
        if str(item.get("ean")) == code:
            return str(item["name"])
    master = catalog_by_ean().get(code)
    if master:
        return str(master["product_name"])
    return LEGACY_PRODUCT_NAMES_BY_EAN.get(code)


LEGACY_CASE_SIZES_BY_EAN: dict[str, int] = {
    "5051410987654": 6,
    "5051420123456": 4,
    "5051410112233": 4,
    "5051410223344": 4,
    "5051410998877": 10,
}


def case_size_for_ean(ean: Optional[str]) -> Optional[int]:
    """Total units in the product's case/multipack (1 for single items), or None when unmapped."""
    code = _clean_ean(ean)
    if not code:
        return None
    for item in CV_PRODUCT_CATALOG.values():
        if str(item.get("ean")) == code:
            return max(1, int(item["pack_size"]))
    master = catalog_by_ean().get(code)
    if master:
        return max(1, int(master.get("inner_pack_units") or master["bom_units"]))
    return LEGACY_CASE_SIZES_BY_EAN.get(code)


def case_size_for_catalog_key(catalog_key: Optional[str]) -> Optional[int]:
    item = CV_PRODUCT_CATALOG.get(str(catalog_key or ""))
    return max(1, int(item["pack_size"])) if item else None


LEGACY_RETAIL_BY_EAN: dict[str, float] = {
    "5051410987654": 3.00,
    "5051420123456": 2.40,
    "5051410112233": 6.00,
    "5051410223344": 4.00,
    "5051410998877": 11.00,
}


def retail_price_for_ean(ean: Optional[str]) -> Optional[float]:
    """Full shelf price (GBP) of the whole case/multipack, or None when unmapped."""
    code = _clean_ean(ean)
    if not code:
        return None
    for item in CV_PRODUCT_CATALOG.values():
        if str(item.get("ean")) == code:
            return round(float(item["parent_price"]), 2)
    master = catalog_by_ean().get(code)
    if master:
        return round(int(master["unit_price_pence"]) / 100.0, 2)
    return LEGACY_RETAIL_BY_EAN.get(code)


def resolve_case_size(
    ean: Optional[str] = None, sku: Optional[str] = None
) -> Optional[int]:
    return case_size_for_ean(ean) or case_size_for_ean(sku)


def resolve_product_name(
    ean: Optional[str] = None, sku: Optional[str] = None
) -> Optional[str]:
    """Best-effort product name from an EAN and/or parent SKU (``EAN-...`` or legacy ``SKU-...``)."""
    return (
        product_name_for_ean(ean)
        or product_name_for_ean(sku)
        or LEGACY_PRODUCT_NAMES_BY_SKU.get(str(sku or "").strip())
    )
