"""Edge CV product catalog — stock-record names must match character-for-character."""

from __future__ import annotations

from typing import Any

from models.bouncer_schemas import ExpectedLedger
from services.shopfloor_catalog import parent_sku_for_ean

CV_PRODUCT_CATALOG: dict[str, dict[str, Any]] = {
    "walkers_crisps_6pk": {
        "ean": "5000328376677",
        "name": "Walkers Ready Salted Crisps 6x25g",
        "parent_price": 2.35,
        "pack_size": 6,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
    "heinz_beans_4pk": {
        "ean": "5000157024886",
        "name": "Heinz B/Beans In TOMT SCE 4x415g",
        "parent_price": 4.00,
        "pack_size": 4,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-02",
    },
    "nestle_cheerios_500g": {
        "ean": "8445291301948",
        "name": "Nestle Cheerios, Wholegrain Cereal, Multigrain, 500g",
        "parent_price": 4.00,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-02",
    },
    "coca_cola_8pk": {
        "ean": "5449000058386",
        "name": "Coca Cola Regular 8x330ml",
        "parent_price": 6.00,
        "pack_size": 8,
        "expected_format": "CARDBOARD_MULTIPACK",
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-05",
    },
    "schweppes_lemonade_2l": {
        "ean": "5000193900861",
        "name": "Schweppes Lemonade 2L BTL",
        "parent_price": 2.00,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-05",
    },
    "diet_coke_caffeine_free_8pk": {
        "ean": "5449000154774",
        "name": "Diet Coke Caffeine Free 8x300ml",
        "parent_price": 4.70,
        "pack_size": 8,
        "expected_format": "CARDBOARD_MULTIPACK",
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-05",
    },
    "fosters_lager_4pk": {
        "ean": "5035766185239",
        "name": "Fosters Lager 4x440ml",
        "parent_price": 4.50,
        "pack_size": 4,
        "expected_format": "CARDBOARD_MULTIPACK",
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-06",
    },
    "budweiser_4pk": {
        "ean": "5021319189021",
        "name": "Budweiser 4x440ml",
        "parent_price": 5.00,
        "pack_size": 4,
        "expected_format": "CARDBOARD_MULTIPACK",
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-06",
    },
    "galaxy_cookie_180g": {
        "ean": "5060402904776",
        "name": "Galaxy Cookie 180g",
        "parent_price": 2.50,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-03",
    },
    "doritos_cool_original_sharing_bag": {
        "ean": "5000328028613",
        "name": "Doritos Tortilla Chips Cool Original Sharing Bag Crisps",
        "parent_price": 2.75,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
    "mccoys_classic_variety_6pk": {
        "ean": "5000237129999",
        "name": "McCoy's Classic Variety Crisps 6x25g",
        "parent_price": 2.65,
        "pack_size": 6,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
    "asahi_super_dry_620ml": {
        "ean": "8008440246066",
        "name": "Asahi Super Dry 5% 620ml",
        "parent_price": 3.55,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-06",
    },
    "stella_artois_4pk": {
        "ean": "5014379028089",
        "name": "Stella Artois Lager 4x568ml",
        "parent_price": 7.00,
        "pack_size": 4,
        "expected_format": "CARDBOARD_MULTIPACK",
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "BEERS-WINES-01",
    },
    "nestle_water_12pk": {
        "ean": "7613031722662",
        "name": "Nestle Pure Life Water 12x500ml",
        "parent_price": 2.90,
        "pack_size": 12,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "SOFT-DRINKS-02",
    },
    "coke_zero_8pk": {
        "ean": "5449000031341",
        "name": "Coke Zero 8x330ml",
        "parent_price": 4.90,
        "pack_size": 8,
        "expected_format": "CARDBOARD_MULTIPACK",
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "SOFT-DRINKS-02",
    },
    "walkers_cheese_onion_6pk": {
        "ean": "5000328375373",
        "name": "Walkers Cheese & Onion Crisps 6x25g",
        "parent_price": 2.50,
        "pack_size": 6,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
    "lucky_buddha_beer": {
        "ean": "851626003001",
        "name": "Lucky Budha Beer 0.33l",
        "parent_price": 3.15,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "BEERS-WINES-01",
    },
    "walkers_quavers_6pk": {
        "ean": "5000328014937",
        "name": "Walkers Quavers Cheese Snacks 6X16G",
        "parent_price": 2.70,
        "pack_size": 6,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
    "british_mineral_water_2l": {
        "ean": "5059697384226",
        "name": "British Natural Mineral Water Still 2L",
        "parent_price": 0.85,
        "pack_size": 1,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
    "british_mineral_water_6x2l": {
        "ean": "5063446480503",
        "name": "British Natural Mineral Water Still 6X2L",
        "parent_price": 2.50,
        "pack_size": 6,
        "child_sku_suffix": "SINGLE-WASTE",
        "planogram_location": "CAM-AISLE-04",
    },
}


def resolve_cv_catalog_item(identifier: str) -> tuple[str, dict[str, Any]] | None:
    """
    Resolve a catalog entry by slug key, exact stock `name`, or EAN.
    Returns (catalog_key, item dict).
    """
    if identifier in CV_PRODUCT_CATALOG:
        return identifier, CV_PRODUCT_CATALOG[identifier]

    for key, item in CV_PRODUCT_CATALOG.items():
        if item.get("name") == identifier:
            return key, item
        if item.get("ean") == identifier:
            return key, item

    return None


def expected_ledger_from_cv_item(item: dict[str, Any]) -> ExpectedLedger:
    ean = str(item["ean"])
    parent = parent_sku_for_ean(ean)
    name = str(item.get("name", ""))
    fixture = str(item.get("planogram_location", "CAM-AISLE-04"))

    pack_size = int(item.get("pack_size", 1))

    if pack_size > 1:
        expected_format = "SHRINK_WRAPPED_MULTIPACK"
    else:
        expected_format = "SINGLE_ITEM"
    # Optional per-item packaging override (e.g. cardboard sleeves instead of shrink wrap).
    expected_format = str(item.get("expected_format") or expected_format)

    name_lower = name.lower()
    is_alcohol = any(
        brand in name_lower
        for brand in ["lager", "fosters", "budweiser", "asahi", "beer", "cider"]
    )

    return ExpectedLedger(
        parent_sku=parent,
        ean=ean,
        expected_quantity=pack_size * 2,
        planogram_location=fixture,
        expected_format=expected_format,
        linked_child_sku=f"{parent}-SINGLE",
        retail_price=float(item["parent_price"]),
        pack_quantity=pack_size,
        is_alcohol=is_alcohol,
        abv_strength=4.0 if is_alcohol else None,
        volume_litres=0.44 if is_alcohol else None,
        excise_duty=0.45 if is_alcohol else None,
        vat_amount=0.20 if is_alcohol else None,
    )
