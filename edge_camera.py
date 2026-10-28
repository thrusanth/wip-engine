"""Edge CV capture node: webcam snapshot → Luna damage classification → API Bouncer webhook."""

from __future__ import annotations

import base64
import json
import os
import sys

import requests

from services.cv_catalog import CV_PRODUCT_CATALOG, resolve_cv_catalog_item
from services.edge_feed import make_thumbnail_b64

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
LUNA_MODEL = "gpt-6-luna"
# Override to feed the live dashboard, e.g. BOUNCER_DAMAGE_URL=https://<backend>/api/cv/damage-event
BOUNCER_DAMAGE_URL = os.getenv(
    "BOUNCER_DAMAGE_URL", "http://127.0.0.1:8000/api/cv/damage-event"
)
EDGE_API_KEY = os.getenv("BOUNCER_EDGE_TOKEN", "edge-cam-prod-992-xtz")
LUNA_UNKNOWN_CATALOG_KEY = "unknown"


def _luna_catalog_key_options() -> list[str]:
    return list(CV_PRODUCT_CATALOG.keys()) + [LUNA_UNKNOWN_CATALOG_KEY]


# Visual disambiguation: logistical wrap vs retail multipack for the British water SKUs.
LUNA_WATER_CLASSIFICATION_RULES = (
    "Water classification rules (do not confuse logistical packs with retail multipacks): "
    "IF the bottles are wrapped in completely clear, transparent plastic "
    "(often with a white logistical barcode sticker), classify it as the single item: "
    "british_mineral_water_2l. "
    "IF the bottles are wrapped in branded, opaque blue plastic with the Tesco logo "
    "covering the middle, classify it as the multipack: british_mineral_water_6x2l. "
)

LUNA_COCA_COLA_DISAMBIGUATION_RULES = (
    "Coca-Cola multipack disambiguation (read the box, not the colour): "
    "Do NOT rely solely on the packaging color (red vs. black) to differentiate between "
    "Coca-Cola variants. "
    "You MUST read the text on the box. "
    'If the packaging says "ZERO SUGAR", you must classify the item as coke_zero_8pk, '
    "even if the box is predominantly red. "
    'Only classify the item as coca_cola_8pk if it says "ORIGINAL TASTE" or explicitly '
    'lacks the "ZERO SUGAR" label. '
)

# Condition rules for the logistical (clear) wrap: torn outer plastic is not retail damage.
LUNA_WATER_CONDITION_RULES = (
    "Condition rules for logistical packaging: "
    "If the item is identified as british_mineral_water_2l (clear logistical wrap), "
    "you must ignore torn or ripped outer plastic. "
    "Do NOT classify the condition as TORN_MULTIPACK. "
    "Because the clear plastic has no retail value, classify the condition as INTACT "
    "unless you can visibly see that an individual bottle is crushed or leaking. "
)

LUNA_CARDBOARD_CONDITION_RULES = (
    "Condition rules for cardboard sleeves and trays: "
    "Cardboard sleeves and trays (like beer and soft drink multipacks) are intentionally "
    "manufactured with open sides. This is their normal, undamaged state. "
    "If you see a cardboard multipack with exposed products on the sides, you must default "
    "to INTACT. "
    "Do NOT classify these as TORN_MULTIPACK, CRUSHED, or any other damaged state unless "
    "the cardboard itself is obviously and severely ripped, flattened, or structurally "
    "destroyed. "
)

LUNA_LOOSE_UNITS_COUNTING_RULES = (
    "Loose unit counting rules for loose_units_visible: "
    "Do NOT count cans or bottles that are still securely held inside their multipack as "
    "loose_units, even if they are clearly visible through the open sides of a cardboard "
    "sleeve or clear plastic wrap. "
    "ONLY count an item as a loose_unit if it has completely fallen out and is physically "
    "separated from the main packaging. "
)


def _build_luna_system_prompt() -> str:
    keys = _luna_catalog_key_options()
    catalog_lines = "\n".join(
        f'  - {key}: {item["name"]}'
        + (
            " (packaged in a CARDBOARD sleeve/tray, not shrink wrap — intact cardboard "
            "is not a torn multipack)"
            if item.get("expected_format") == "CARDBOARD_MULTIPACK"
            else ""
        )
        for key, item in CV_PRODUCT_CATALOG.items()
    )
    return (
        "You are a retail inventory inspector analyzing product packaging on a shop floor. "
        "Respond with strictly valid JSON containing exactly four keys: "
        '"condition" (must be one of: INTACT, TORN_MULTIPACK, CRUSHED), '
        '"confidence" (a float between 0.0 and 1.0 indicating classification certainty), '
        '"catalog_key" (must be one of: '
        + ", ".join(keys)
        + "), and "
        '"loose_units_visible" (a non-negative integer). '
        f"{LUNA_LOOSE_UNITS_COUNTING_RULES}"
        "If none have fallen out or the field does not apply, return 0. "
        "You must classify the damaged item by selecting the exact matching key or name "
        "from this provided catalog list:\n"
        f"{catalog_lines}\n"
        f"{LUNA_WATER_CLASSIFICATION_RULES}"
        f"{LUNA_COCA_COLA_DISAMBIGUATION_RULES}"
        f"{LUNA_WATER_CONDITION_RULES}"
        f"{LUNA_CARDBOARD_CONDITION_RULES}"
        f'Use catalog_key "{LUNA_UNKNOWN_CATALOG_KEY}" only when no catalog entry matches. '
        "Prefer returning the catalog slug key when confident. "
        "Do not include any other keys or prose."
    )

USER_PROMPT = (
    "Examine this packaging. Is the outer seal completely intact, physically torn, "
    "or structurally crushed?"
)


def capture_and_encode() -> str:
    """Headless webcam capture: warm-up reads, terminal Enter to snap, return base64 JPEG."""
    import cv2  # lazy: the deployed backend imports this module for Luna but has no webcam/OpenCV

    cam = cv2.VideoCapture(1)
    if not cam.isOpened():
        cam.release()
        cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        cam.release()
        raise RuntimeError("Could not open webcam at index 1 or 0.")

    try:
        for _ in range(10):
            cam.read()

        input("Press ENTER in this terminal to snap the photo...")

        ret, frame = cam.read()
        if not ret or frame is None:
            raise RuntimeError("Failed to read frame from webcam.")
    finally:
        cam.release()

    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG.")

    return base64.b64encode(encoded.tobytes()).decode("ascii")


def evaluate_damage_with_luna(base64_image: str) -> dict[str, float | str | int]:
    """Send the frame to OpenAI Luna and parse condition + confidence JSON."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    payload = {
        "model": LUNA_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _build_luna_system_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            },
        ],
    }

    response = requests.post(
        OPENAI_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"OpenAI API error ({response.status_code}): {response.text[:500]}"
        )

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
        decision = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {body!r}") from exc

    condition = str(decision.get("condition", "")).strip().upper()
    if condition not in {"INTACT", "TORN_MULTIPACK", "CRUSHED"}:
        raise ValueError(f"Invalid condition from model: {condition!r}")

    try:
        confidence = float(decision["confidence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid confidence from model: {decision!r}") from exc

    confidence = max(0.0, min(1.0, confidence))

    catalog_key = str(decision.get("catalog_key", "")).strip()
    valid_keys = set(_luna_catalog_key_options())
    if catalog_key not in valid_keys:
        resolved = resolve_cv_catalog_item(catalog_key)
        if resolved:
            catalog_key = resolved[0]
        elif catalog_key not in valid_keys:
            raise ValueError(f"Invalid catalog_key from model: {catalog_key!r}")

    try:
        loose_units_visible = int(decision.get("loose_units_visible", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid loose_units_visible from model: {decision!r}"
        ) from exc
    loose_units_visible = max(0, loose_units_visible)

    return {
        "condition": condition,
        "confidence": confidence,
        "catalog_key": catalog_key,
        "loose_units_visible": loose_units_visible,
    }


def trigger_bouncer_webhook(
    decision_data: dict[str, float | str | int],
    frame_thumbnail_b64: str | None = None,
) -> dict:
    """POST damage classification (and a frame thumbnail for the live feed) to the API Bouncer."""
    catalog_key = str(
        decision_data.get("catalog_key") or LUNA_UNKNOWN_CATALOG_KEY
    )
    payload = {
        "item_name": catalog_key,
        "condition": str(decision_data["condition"]),
        "confidence_score": float(decision_data["confidence"]),
        "loose_units_visible": int(decision_data.get("loose_units_visible", 0)),
        "source": "edge_camera",
    }
    if frame_thumbnail_b64:
        payload["frame_thumbnail_b64"] = frame_thumbnail_b64

    response = requests.post(
        BOUNCER_DAMAGE_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": EDGE_API_KEY,
        },
        timeout=30,
    )

    try:
        result = response.json()
    except json.JSONDecodeError:
        result = {"raw": response.text}

    if response.status_code != 200:
        raise RuntimeError(
            f"Bouncer webhook failed ({response.status_code}): {result}"
        )

    return result


if __name__ == "__main__":
    try:
        print("Opening webcam (headless)…")
        image_b64 = capture_and_encode()
        print("Frame captured. Sending to Luna for damage evaluation…")
        decision = evaluate_damage_with_luna(image_b64)
        print(f"Model decision: {decision}")
        print("Triggering API Bouncer webhook…")
        bouncer_result = trigger_bouncer_webhook(
            decision, frame_thumbnail_b64=make_thumbnail_b64(image_b64)
        )
        print(json.dumps(bouncer_result, indent=2))
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
