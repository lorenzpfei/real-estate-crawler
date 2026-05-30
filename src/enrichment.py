"""AI-powered extraction of structured data from listing descriptions."""

import json
import logging
import os

import httpx

from src.models import Listing

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

_SYSTEM_PROMPT = """You extract structured data from German real estate listing texts.
Given the listing data, extract the following fields from title + description + equipment + other_info.
Return ONLY valid JSON, no explanation.

{
  "has_balcony": bool or null,
  "has_garden": bool or null,
  "has_parking": bool or null,
  "has_elevator": bool or null,
  "has_cellar": bool or null,
  "has_fitted_kitchen": bool or null,
  "num_units_in_building": int or null,
  "available_from": "string or empty",
  "pets_allowed": bool or null,
  "is_temporary": bool or null
}

Rules:
- IMPORTANT: Only set true/false if EXPLICITLY mentioned in the text. If a feature is simply not mentioned at all, you MUST return null. "Not mentioned" ≠ false. false means explicitly stated as not available (e.g. "kein Balkon", "ohne Aufzug").
- "Balkon", "Terrasse", "Loggia" → has_balcony: true
- "Garten", "Gartenanteil", "Gartenmitbenutzung" → has_garden: true
- "Stellplatz", "Garage", "TG", "Tiefgarage", "Parkplatz" → has_parking: true
- "Aufzug", "Fahrstuhl", "Lift" → has_elevator: true
- "Keller", "Kellerraum", "Kellerabteil" → has_cellar: true
- "EBK", "Einbauküche" → has_fitted_kitchen: true
- "X Parteien", "X Wohneinheiten", "X-Familienhaus" → num_units_in_building: X
- "ab sofort", "ab 01.05." etc → available_from
- "befristet", "Zwischenmiete", "zeitlich begrenzt" → is_temporary: true
- "Haustiere nach Absprache" → pets_allowed: true
- "keine Haustiere" → pets_allowed: false"""


async def enrich_listing(client: httpx.AsyncClient, listing: Listing) -> Listing:
    """Use GPT to extract structured fields from listing texts."""
    if not OPENAI_API_KEY:
        return listing

    # Skip listings with no useful text
    if not listing.description and not listing.equipment and not listing.other_info:
        return listing

    text_parts = [f"Title: {listing.title}"]
    if listing.description:
        text_parts.append(f"Description: {listing.description[:1500]}")
    if listing.equipment:
        text_parts.append(f"Equipment: {listing.equipment[:500]}")
    if listing.other_info:
        text_parts.append(f"Other: {listing.other_info[:500]}")
    if listing.property_type:
        text_parts.append(f"Type: {listing.property_type}")

    user_text = "\n".join(text_parts)

    try:
        async with httpx.AsyncClient(timeout=10.0) as ai_client:
            response = await ai_client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_text},
                    ],
                    "temperature": 0,
                    "max_completion_tokens": 200,
                },
            )

        if response.status_code != 200:
            logger.warning("OpenAI API error: %d", response.status_code)
            return listing

        data = response.json()
        raw = data["choices"][0]["message"]["content"]
        clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
        extracted = json.loads(clean)

        # Apply extracted fields — only fill fields the portal didn't already set
        def _apply(field: str, value) -> None:
            if value is not None and getattr(listing, field) is None:
                setattr(listing, field, value)

        _apply("has_balcony", extracted.get("has_balcony"))
        _apply("has_garden", extracted.get("has_garden"))
        _apply("has_parking", extracted.get("has_parking"))
        _apply("has_elevator", extracted.get("has_elevator"))
        _apply("has_cellar", extracted.get("has_cellar"))
        _apply("has_fitted_kitchen", extracted.get("has_fitted_kitchen"))
        _apply("num_units_in_building", extracted.get("num_units_in_building"))
        _apply("pets_allowed", extracted.get("pets_allowed"))
        _apply("is_temporary", extracted.get("is_temporary"))
        # available_from: check empty string too
        if extracted.get("available_from") and not listing.available_from:
            listing.available_from = extracted["available_from"]

        logger.debug("Enriched %s: %s", listing.id, extracted)

    except Exception:
        logger.warning("AI enrichment failed for %s", listing.id, exc_info=True)

    return listing
