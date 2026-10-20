"""Edge CV capture node: webcam snapshot → Luna damage classification → API Bouncer webhook."""

from __future__ import annotations

import base64
import json
import os
import sys

import cv2
import requests

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
LUNA_MODEL = "gpt-6-luna"
BOUNCER_DAMAGE_URL = "http://127.0.0.1:8000/api/cv/damage-event"
EDGE_API_KEY = "edge-cam-prod-992-xtz"
HARDCODED_ITEM_NAME = "Multipack Crisps 6pk"

LUNA_CATALOG_KEYS = [
    "walkers_crisps_6pk",
    "heinz_beans_4pk",
    "coca_cola_8pk",
    "schweppes_lemonade_2l",
    "fosters_lager_4pk",
    "galaxy_cookie_180g",
    "doritos_cool_original_sharing_bag",
    "asahi_super_dry_620ml",
    "unknown",
]

SYSTEM_PROMPT = (
    "You are a retail inventory inspector analyzing product packaging on a shop floor. "
    "Respond with strictly valid JSON containing exactly three keys: "
    '"condition" (must be one of: INTACT, TORN_MULTIPACK, CRUSHED), '
    '"confidence" (a float between 0.0 and 1.0 indicating classification certainty), and '
    '"catalog_key" (must be one of: '
    + ", ".join(LUNA_CATALOG_KEYS)
    + "). "
    "Do not include any other keys or prose."
)

USER_PROMPT = (
    "Examine this packaging. Is the outer seal completely intact, physically torn, "
    "or structurally crushed?"
)


def capture_and_encode() -> str:
    """Headless webcam capture: warm-up reads, terminal Enter to snap, return base64 JPEG."""
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


def evaluate_damage_with_luna(base64_image: str) -> dict[str, float | str]:
    """Send the frame to OpenAI Luna and parse condition + confidence JSON."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    payload = {
        "model": LUNA_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
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
    if catalog_key not in LUNA_CATALOG_KEYS:
        raise ValueError(f"Invalid catalog_key from model: {catalog_key!r}")

    return {
        "condition": condition,
        "confidence": confidence,
        "catalog_key": catalog_key,
    }


def trigger_bouncer_webhook(decision_data: dict[str, float | str]) -> dict:
    """POST damage classification to the local API Bouncer CV ingestion route."""
    catalog_key = str(decision_data.get("catalog_key") or HARDCODED_ITEM_NAME)
    payload = {
        "item_name": catalog_key,
        "condition": str(decision_data["condition"]),
        "confidence_score": float(decision_data["confidence"]),
    }

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
        bouncer_result = trigger_bouncer_webhook(decision)
        print(json.dumps(bouncer_result, indent=2))
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
