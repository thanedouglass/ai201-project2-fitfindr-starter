"""
tools.py

The core FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
    compare_price(item, all_listings)               → dict (Stretch Tool)
"""

import os
import re
from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Configurable Groq model with fallback
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client() -> Groq:
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Size matching helper ──────────────────────────────────────────────────────

def _normalize_size_tokens(size_str: str) -> set[str]:
    """Extract normalized size tokens from a size string."""
    s = size_str.strip().upper()
    # Split on slashes, spaces, hyphens, parentheses
    tokens = set(re.findall(r"[A-Z0-9]+", s))
    return tokens


def _matches_size(query_size: str, listing_size: str) -> bool:
    """
    Case-insensitive, flexible size matching.
    Supports exact matches, composite sizes (e.g., 'M' matches 'S/M' or 'M/L'),
    parenthetical qualifiers ('XL (oversized)'), and waist sizes ('30' or 'W30').
    """
    q = query_size.strip().upper()
    l = listing_size.strip().upper()

    if q == l:
        return True

    # Check composite slash sizes (e.g. 'S/M', 'XS/S')
    l_parts = [p.strip() for p in l.split("/") if p.strip()]
    if q in l_parts:
        return True

    # Token-based check
    q_tokens = _normalize_size_tokens(q)
    l_tokens = _normalize_size_tokens(l)
    if q_tokens and q_tokens.issubset(l_tokens):
        return True

    # Number-only match for waist/shoe sizes (e.g., '30' matches 'W30')
    q_num = re.sub(r"[^\d.]", "", q)
    if q_num:
        # Check if number matches any numeric token in listing size
        l_nums = re.findall(r"\d+(?:\.\d+)?", l)
        if q_num in l_nums:
            return True

    # Check substring with word boundary
    if re.search(r"\b" + re.escape(q) + r"\b", l):
        return True

    return False


# ── Stopwords for scoring ─────────────────────────────────────────────────────

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "for", "with", "of",
    "to", "from", "by", "is", "it", "looking", "look", "want", "wanted",
    "need", "needed", "some", "like", "under", "below", "size", "something",
}


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    Failure Mode:
        Returns an empty list `[]` without raising an exception when no
        candidate listing meets the combined description, size, or price constraints.
    """
    if not description or not description.strip():
        return []

    try:
        all_listings = load_listings()
    except Exception:
        return []

    # 1. Extract and clean search tokens
    raw_tokens = re.findall(r"[a-zA-Z0-9]+", description.lower())
    meaningful_tokens = [t for t in raw_tokens if t not in STOPWORDS and len(t) > 1]
    query_tokens = meaningful_tokens if meaningful_tokens else raw_tokens

    candidates = []

    # 2. Filter and score listings
    for item in all_listings:
        # Price filter
        if max_price is not None:
            try:
                if float(item.get("price", 0.0)) > float(max_price):
                    continue
            except (ValueError, TypeError):
                continue

        # Size filter
        if size is not None and str(size).strip():
            item_size = str(item.get("size", ""))
            if not _matches_size(str(size), item_size):
                continue

        # Relevance scoring
        score = 0
        title_lower = str(item.get("title", "")).lower()
        desc_lower = str(item.get("description", "")).lower()
        cat_lower = str(item.get("category", "")).lower()
        brand_lower = str(item.get("brand", "") or "").lower()
        tags_lower = [str(t).lower() for t in item.get("style_tags", [])]
        colors_lower = [str(c).lower() for c in item.get("colors", [])]

        # Exact phrase bonus
        clean_desc_str = " ".join(query_tokens)
        if clean_desc_str and clean_desc_str in title_lower:
            score += 15
        elif clean_desc_str and clean_desc_str in desc_lower:
            score += 8

        # Keyword token scoring with field weighting
        for token in query_tokens:
            token_matched = False
            # Title match (high weight)
            if re.search(r"\b" + re.escape(token), title_lower):
                score += 5
                token_matched = True
            # Category match (high weight)
            if token == cat_lower or token in cat_lower:
                score += 4
                token_matched = True
            # Style tags match (high weight)
            for tag in tags_lower:
                if token in tag:
                    score += 4
                    token_matched = True
                    break
            # Brand match
            if brand_lower and token in brand_lower:
                score += 3
                token_matched = True
            # Colors match
            for color in colors_lower:
                if token in color:
                    score += 2
                    token_matched = True
                    break
            # Item description match
            if re.search(r"\b" + re.escape(token), desc_lower):
                score += 2
                token_matched = True

        # Drop listings with zero relevance
        if score > 0:
            candidates.append((score, item))

    # Sort primarily by relevance score (descending), tie-break by price (ascending)
    candidates.sort(key=lambda x: (-x[0], x[1].get("price", 0.0)))

    return [item for _, item in candidates]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    Failure Mode:
        If `wardrobe['items']` is empty, the tool handles this gracefully by
        providing versatile, general styling principles rather than failing.
        If inputs are malformed, returns a clear error string without crashing.
    """
    if not new_item or not isinstance(new_item, dict):
        return "Could not suggest outfit: invalid or missing item details provided."

    wardrobe_items = []
    if isinstance(wardrobe, dict):
        wardrobe_items = wardrobe.get("items", []) or []

    item_title = new_item.get("title", "Vintage Find")
    item_cat = new_item.get("category", "garment")
    item_desc = new_item.get("description", "")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))
    item_condition = new_item.get("condition", "good")

    # Empty wardrobe path: General styling advice
    if not wardrobe_items:
        system_prompt = (
            "You are an expert sustainable fashion stylist for FitFindr. "
            "The user does not currently have any items in their digital wardrobe. "
            "Provide 1-2 versatile, complete styling concepts for this thrifted item. "
            "Suggest complementary silhouettes, fabric textures, color combinations, and footwear. "
            "Be encouraging, practical, and fashionable. Keep your response under 150 words."
        )
        user_prompt = (
            f"Item: {item_title}\n"
            f"Category: {item_cat}\n"
            f"Colors: {item_colors}\n"
            f"Aesthetic/Tags: {item_tags}\n"
            f"Condition: {item_condition}\n"
            f"Description: {item_desc}\n\n"
            "Please provide general outfit styling advice for this secondhand piece."
        )
    else:
        # Populated wardrobe path: Coordinate with specific closet items
        formatted_wardrobe = []
        for w in wardrobe_items:
            w_name = w.get("name", "Unknown item")
            w_cat = w.get("category", "")
            w_colors = ", ".join(w.get("colors", []))
            w_tags = ", ".join(w.get("style_tags", []))
            w_notes = f" (Notes: {w.get('notes')})" if w.get("notes") else ""
            formatted_wardrobe.append(
                f"- [{w.get('id', 'item')}] {w_name} ({w_cat}, colors: {w_colors}, tags: {w_tags}){w_notes}"
            )
        wardrobe_text = "\n".join(formatted_wardrobe)

        system_prompt = (
            "You are an expert personal fashion stylist for FitFindr. "
            "Suggest 1-2 complete, creative outfit combinations pairing the new thrifted piece "
            "with specific, named items from the user's existing wardrobe. "
            "Explicitly name the wardrobe pieces used. Explain silhouette balance, color harmony, "
            "and include actionable styling advice (e.g. cuffing, tucking, layering). "
            "Keep the response concise, engaging, and under 175 words."
        )
        user_prompt = (
            f"Thrifted Item to style:\n"
            f"Title: {item_title}\n"
            f"Category: {item_cat}\n"
            f"Colors: {item_colors}\n"
            f"Tags: {item_tags}\n"
            f"Description: {item_desc}\n\n"
            f"User's Wardrobe Items:\n{wardrobe_text}\n\n"
            "Suggest 1-2 complete outfit combinations pairing this thrift find with specific wardrobe pieces."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=250,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()
    except Exception as e:
        # Fallback if LLM fails (e.g. offline, rate-limited)
        if not wardrobe_items:
            return (
                f"Styling ideas for the {item_title}: Pair this versatile {item_cat} with neutral "
                f"high-waisted denim or structured trousers. Complement the {item_colors} palette "
                f"with minimal leather accessories and classic retro sneakers for an effortless {item_tags} look."
            )
        first_wardrobe = wardrobe_items[0].get("name", "wardrobe staples")
        return (
            f"Outfit suggestion: Pair the {item_title} directly with your {first_wardrobe}. "
            f"The contrast creates a balanced {item_tags} silhouette. Finish the look with clean accessories."
        )

    return f"Styling tip: The {item_title} pairs effortlessly with classic denim and minimal accessories."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    Failure Mode:
        If `outfit` is empty or whitespace-only, returns a descriptive error
        string: "Could not generate fit card: outfit description is missing or empty. Please ensure an outfit recommendation is generated first."
    """
    # Guard against empty, whitespace-only, or None outfit string
    if not outfit or not outfit.strip():
        return (
            "Could not generate fit card: outfit description is missing or empty. "
            "Please ensure an outfit recommendation is generated first."
        )

    if not new_item or not isinstance(new_item, dict):
        return "Could not generate fit card: invalid or missing item details."

    item_title = new_item.get("title", "thrifted find")
    price = new_item.get("price", 0.0)
    platform = str(new_item.get("platform", "secondhand")).capitalize()
    style_tags = ", ".join(new_item.get("style_tags", []))

    system_prompt = (
        "You write punchy, authentic social media captions (Instagram/TikTok OOTD style) for secondhand fashion finds. "
        "Write a 2 to 4 sentence caption celebrating this thrifted outfit. "
        "Guidelines:\n"
        "1. Write in a relaxed, personal, everyday social media voice (lowercase aesthetics welcome, tasteful emojis).\n"
        "2. Naturally mention the item title, price, and platform once each.\n"
        "3. Capture the overall vibe and aesthetic described in the outfit pairing.\n"
        "4. Do NOT sound like an ad or commercial endorsement.\n"
        "5. Output ONLY the caption text."
    )

    user_prompt = (
        f"Item: {item_title}\n"
        f"Price: ${price:.2f}\n"
        f"Platform: {platform}\n"
        f"Aesthetic: {style_tags}\n"
        f"Outfit Styling:\n{outfit.strip()}\n\n"
        "Write a 2-4 sentence caption for this fit."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=150,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            # Strip outer quotation marks if generated
            cleaned = content.strip().strip('"').strip("'")
            return cleaned
    except Exception:
        # Fallback template if LLM call fails
        return (
            f"thrifted this {item_title} on {platform} for only ${price:.2f} and I'm obsessed ✨ "
            f"styled it up with my favorite closet staples for that effortless {style_tags} vibe."
        )

    return (
        f"thrifted this {item_title} on {platform} for ${price:.2f} ✨ "
        f"obsessed with how this outfit came together."
    )


# ── Stretch Tool: compare_price ───────────────────────────────────────────────

def compare_price(item: dict, all_listings: list[dict] | None = None) -> dict:
    """
    Stretch Tool: Market price fairness comparison.
    Compares the item's price against comparable items in the same category
    or brand to assess whether it represents a deal, fair market value, or splurge.

    Args:
        item: The candidate listing dict.
        all_listings: Optional list of all listings. Defaults to load_listings().

    Returns:
        dict with:
            - item_price: float
            - category: str
            - category_avg: float
            - difference_pct: float (negative means cheaper than average)
            - deal_rating: str ("Steal", "Great Deal", "Fair Market Value", "Splurge")
            - summary: str
    """
    if not item or not isinstance(item, dict):
        return {"error": "Invalid item provided for price comparison."}

    if all_listings is None:
        try:
            all_listings = load_listings()
        except Exception:
            all_listings = []

    cat = item.get("category", "")
    item_price = float(item.get("price", 0.0))

    # Filter category peers
    category_prices = [
        float(x.get("price", 0.0))
        for x in all_listings
        if x.get("category") == cat and x.get("price") is not None
    ]

    if not category_prices:
        return {
            "item_price": item_price,
            "category": cat,
            "category_avg": item_price,
            "difference_pct": 0.0,
            "deal_rating": "Fair Market Value",
            "summary": f"${item_price:.2f} — No category comparisons available.",
        }

    cat_avg = sum(category_prices) / len(category_prices)
    diff_pct = ((item_price - cat_avg) / cat_avg) * 100.0

    if diff_pct <= -25.0:
        rating = "Steal"
        badge = "🔥 Steal"
    elif diff_pct <= -10.0:
        rating = "Great Deal"
        badge = "🏷️ Great Deal"
    elif diff_pct <= 15.0:
        rating = "Fair Market Value"
        badge = "⚖️ Fair Market Value"
    else:
        rating = "Splurge"
        badge = "💎 Premium / Splurge"

    diff_str = (
        f"{abs(diff_pct):.0f}% below category average"
        if diff_pct < 0
        else f"{abs(diff_pct):.0f}% above category average"
    )

    summary = f"{badge} (${item_price:.2f} vs {cat} average of ${cat_avg:.2f}, {diff_str})"

    return {
        "item_price": item_price,
        "category": cat,
        "category_avg": round(cat_avg, 2),
        "difference_pct": round(diff_pct, 1),
        "deal_rating": rating,
        "summary": summary,
    }
