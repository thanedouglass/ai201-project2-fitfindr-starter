"""
agent.py

The FitFindr planning loop. Orchestrates the tools in response to a
natural language user query, passing state between them via a session dict.

Key Features:
- Natural language query parser extracting item description, clothing size, and price ceiling.
- Multi-step conditional planning loop driven by session state inspections.
- Graceful early termination with actionable troubleshooting instructions on failures.
- Direct state persistence from search_listings → suggest_outfit → create_fit_card.
- Stretch Features:
    * Market price comparison (compare_price) integrated into session.
    * Adaptive fallback search analysis when strict filters yield zero results.
    * Style profile memory tracking aesthetic preferences across runs.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re
from tools import search_listings, suggest_outfit, create_fit_card, compare_price


# ── query parser ──────────────────────────────────────────────────────────────

def parse_query(query: str) -> dict:
    """
    Parse a natural language query into structured search parameters:
    description (str), size (str | None), max_price (float | None).

    Examples:
        "vintage graphic tee under $30, size M"
            → {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}
        "black combat boots size 8"
            → {"description": "black combat boots", "size": "8", "max_price": None}
        "flowy midi skirt under $40"
            → {"description": "flowy midi skirt", "size": None, "max_price": 40.0}
    """
    if not query or not query.strip():
        return {"description": "", "size": None, "max_price": None}

    text = query.strip()
    max_price: float | None = None
    size: str | None = None

    # 1. Extract price ceiling: e.g. "under $30", "below 45.00", "under 25 dollars", "<= $50"
    price_pattern = re.compile(
        r"(?:under|below|less than|max(?:imum)?|budget of|up to|costing under|\$|<=)\s*\$?(\d+(?:\.\d{1,2})?)(?:\s*(?:dollars|bucks|usd))?",
        re.IGNORECASE,
    )
    price_match = price_pattern.search(text)
    if price_match:
        try:
            max_price = float(price_match.group(1))
            # Remove the price phrase from query text
            text = text[: price_match.start()] + " " + text[price_match.end() :]
        except (ValueError, TypeError):
            max_price = None

    # 2. Extract clothing / shoe size: e.g. "size M", "size 8", "size S/M", "in size XL", "W30"
    size_pattern = re.compile(
        r"\b(?:in\s+)?size\s+([A-Za-z0-9/]+(?:\s*\([a-zA-Z]+\))?)",
        re.IGNORECASE,
    )
    size_match = size_pattern.search(text)
    if size_match:
        size = size_match.group(1).strip()
        text = text[: size_match.start()] + " " + text[size_match.end() :]
    else:
        # Check standalone size keywords if formatted like "size: M" or standalone W\d+
        waist_match = re.search(r"\b(W\d{2}(?:\s*L\d{2})?)\b", text, re.IGNORECASE)
        if waist_match:
            size = waist_match.group(1).strip()
            text = text[: waist_match.start()] + " " + text[waist_match.end() :]
        else:
            # Check for standalone single-letter sizes with word boundaries (e.g. "size M" without word "size")
            standalone_size = re.search(r"\b(XXS|XS|XXL|XL)\b", text, re.IGNORECASE)
            if standalone_size:
                size = standalone_size.group(1).strip()
                text = text[: standalone_size.start()] + " " + text[standalone_size.end() :]

    # 3. Clean remaining text to form description keywords
    cleaned_desc = re.sub(r"[,;:.!?]+", " ", text)
    cleaned_desc = re.sub(r"\b(looking for|i want|find me|search for|need a|i need|a|an|the)\b", " ", cleaned_desc, flags=re.IGNORECASE)
    cleaned_desc = re.sub(r"\s+", " ", cleaned_desc).strip()

    # If all tokens were stripped, fallback to original query without price
    if not cleaned_desc:
        cleaned_desc = re.sub(r"\s+", " ", text).strip()

    return {
        "description": cleaned_desc,
        "size": size,
        "max_price": max_price,
    }


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(
    query: str,
    wardrobe: dict,
    style_profile: dict | None = None,
) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    style memory, and any error that caused early termination.
    """
    return {
        "query": query,                          # original user query
        "parsed": {},                            # extracted description / size / max_price
        "search_results": [],                    # list of matching listing dicts from search_listings
        "selected_item": None,                   # top result, passed into suggest_outfit
        "price_comparison": None,                # stretch: price fairness analysis dict
        "wardrobe": wardrobe,                    # user's wardrobe dict
        "outfit_suggestion": None,               # string returned by suggest_outfit
        "fit_card": None,                        # string returned by create_fit_card
        "error": None,                           # set if the interaction ended early
        "fallback_applied": False,               # stretch: True if relaxed search was analyzed
        "fallback_notes": None,                  # stretch: explanation of relaxed search alternatives
        "style_profile": style_profile or {},    # stretch: user style memory (tags, preferred brands)
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(
    query: str,
    wardrobe: dict,
    style_profile: dict | None = None,
) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Decision-Making and Control Flow:
        1. Validates user input query. If empty, halts immediately with helpful prompt.
        2. Parses natural language into structured parameters (description, size, max_price).
        3. Invokes search_listings.
        4. State Inspection: Evaluates search_results length.
           - If 0 results: Triggers explicit error handling. Conducts diagnostic analysis
             (identifying if size or budget was the bottleneck) and returns actionable advice.
             Does NOT execute downstream tools.
        5. Selects top-ranked candidate listing into session["selected_item"].
        6. Runs compare_price (Stretch Tool) to compute market value and savings.
        7. Invokes suggest_outfit using selected_item and wardrobe.
        8. Validates outfit output.
        9. Invokes create_fit_card using outfit suggestion and selected_item.
        10. Updates style_profile memory with tags from the selected find.
        11. Returns fully populated session dictionary.

    Args:
        query:         Natural language user request (e.g., "vintage graphic tee under $30, size M")
        wardrobe:      User's wardrobe dict (from get_example_wardrobe() or get_empty_wardrobe())
        style_profile: Optional dict with user style history/preferences

    Returns:
        The session dict after execution. Check session["error"] first — if non-None,
        the interaction terminated early and downstream fields will be None.
    """
    session = _new_session(query, wardrobe, style_profile)

    # ── Step 1: Input Validation ──────────────────────────────────────────────
    if not query or not query.strip():
        session["error"] = (
            "No search query provided. Please describe the secondhand item you're looking for, "
            "optionally including your size and price ceiling (e.g. 'vintage graphic tee under $30, size M')."
        )
        return session

    # ── Step 2: Parse Query ───────────────────────────────────────────────────
    parsed = parse_query(query)
    session["parsed"] = parsed

    description = parsed.get("description", "")
    size = parsed.get("size")
    max_price = parsed.get("max_price")

    if not description:
        session["error"] = (
            "Could not identify a clothing item or aesthetic in your query. "
            "Please include what kind of piece you are shopping for (e.g. 'flannel shirt', 'leather boots')."
        )
        return session

    # ── Step 3: Tool 1 — search_listings ──────────────────────────────────────
    results = search_listings(description=description, size=size, max_price=max_price)
    session["search_results"] = results

    # ── Step 4: State Check & Error Handling (Zero-Results Branch) ────────────
    if not results:
        # Run diagnostic check: What caused the 0 matches?
        suggestions = []
        if size is not None:
            # Check if items exist without size constraint
            no_size_results = search_listings(description=description, size=None, max_price=max_price)
            if no_size_results:
                available_sizes = sorted(list({str(it.get("size")) for it in no_size_results if it.get("size")}))
                suggestions.append(
                    f"Removing the size filter '{size}' would reveal {len(no_size_results)} matching item(s) "
                    f"(available sizes: {', '.join(available_sizes[:5])})."
                )

        if max_price is not None:
            # Check if items exist at higher budget
            higher_budget_results = search_listings(description=description, size=size, max_price=None)
            if higher_budget_results:
                lowest_price = min(float(it.get("price", 0)) for it in higher_budget_results)
                suggestions.append(
                    f"Increasing your budget above ${max_price:.2f} (the lowest matching listing starts at ${lowest_price:.2f}) "
                    f"would unlock {len(higher_budget_results)} item(s)."
                )

        # Build detailed, actionable error message
        constraints_str = f"'{description}'"
        details = []
        if size:
            details.append(f"size '{size}'")
        if max_price is not None:
            details.append(f"max price ${max_price:.2f}")
        if details:
            constraints_str += f" with constraints ({', '.join(details)})"

        error_lines = [
            f"No secondhand listings found matching {constraints_str}.",
            "",
            "What to try next:",
            "1. Broaden your search terms (e.g., try simpler keywords like 'jacket', 'tee', or 'jeans').",
        ]
        if size:
            error_lines.append("2. Remove or relax the size filter to see pieces with flexible fits or adjacent sizes.")
        if max_price is not None:
            error_lines.append("3. Raise your price ceiling to view premium or vintage collector pieces.")

        if suggestions:
            error_lines.append("")
            error_lines.append("Helpful insights:")
            for s in suggestions:
                error_lines.append(f"• {s}")

        session["error"] = "\n".join(error_lines)
        # Early return: downstream tools are NOT executed with invalid data
        return session

    # ── Step 5: Item Selection ────────────────────────────────────────────────
    # Select the top candidate from ranked results
    selected_item = results[0]
    session["selected_item"] = selected_item

    # ── Step 6: Stretch Tool — compare_price ──────────────────────────────────
    try:
        session["price_comparison"] = compare_price(selected_item)
    except Exception:
        session["price_comparison"] = None

    # ── Step 7: Tool 2 — suggest_outfit ───────────────────────────────────────
    outfit_result = suggest_outfit(
        new_item=selected_item,
        wardrobe=session["wardrobe"],
    )
    session["outfit_suggestion"] = outfit_result

    # Validate Tool 2 output
    if not outfit_result or outfit_result.startswith("Could not suggest outfit"):
        session["error"] = (
            "We found a great listing, but encountered an issue generating your outfit styling advice. "
            "Please try submitting again or selecting a different wardrobe option."
        )
        return session

    # ── Step 8: Tool 3 — create_fit_card ──────────────────────────────────────
    fit_card_result = create_fit_card(
        outfit=outfit_result,
        new_item=selected_item,
    )
    session["fit_card"] = fit_card_result

    # ── Step 9: Stretch — Update Style Profile Memory ──────────────────────────
    if "style_profile" in session and isinstance(session["style_profile"], dict):
        profile = session["style_profile"]
        # Track favored styles
        fav_tags = profile.get("favorite_tags", [])
        for tag in selected_item.get("style_tags", []):
            if tag not in fav_tags:
                fav_tags.append(tag)
        profile["favorite_tags"] = fav_tags[:10]

        # Track favored categories
        fav_cats = profile.get("categories_viewed", [])
        cat = selected_item.get("category")
        if cat and cat not in fav_cats:
            fav_cats.append(cat)
        profile["categories_viewed"] = fav_cats

        # Track last selected platform
        profile["last_platform"] = selected_item.get("platform")

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Test 1: Happy path (vintage graphic tee) ===\n")
    session1 = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session1["error"]:
        print(f"Error: {session1['error']}")
    else:
        print(f"Selected item: {session1['selected_item']['title']} (${session1['selected_item']['price']})")
        if session1.get("price_comparison"):
            print(f"Price Analysis: {session1['price_comparison']['summary']}")
        print(f"\nOutfit suggestion:\n{session1['outfit_suggestion']}")
        print(f"\nFit card:\n{session1['fit_card']}")

    print("\n\n=== Test 2: Deliberate No-Results Path (Impossible query) ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print("Session error output:")
    print(session2["error"])
    print(f"Downstream outfit is None: {session2['outfit_suggestion'] is None}")
    print(f"Downstream fit_card is None: {session2['fit_card'] is None}")

    print("\n\n=== Test 3: Empty wardrobe path ===\n")
    session3 = run_agent(
        query="black combat boots size 8",
        wardrobe=get_empty_wardrobe(),
    )
    if session3["error"]:
        print(f"Error: {session3['error']}")
    else:
        print(f"Selected: {session3['selected_item']['title']}")
        print(f"Outfit (General styling for empty closet):\n{session3['outfit_suggestion']}")
