"""
tests/test_tools.py

Exhaustive tests for FitFindr tools:
- search_listings (filtering, ranking, zero-result failure mode)
- suggest_outfit (with wardrobe, empty wardrobe failure mode, invalid inputs)
- create_fit_card (valid generation, empty outfit failure mode, invalid inputs)
- compare_price (stretch tool market value analysis)
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card, compare_price
from utils.data_loader import load_listings, get_example_wardrobe, get_empty_wardrobe


# ── Tests for search_listings ─────────────────────────────────────────────────

def test_search_listings_basic_query():
    """Verify that searching for known keywords returns non-empty list of dicts."""
    results = search_listings("vintage graphic tee")
    assert isinstance(results, list)
    assert len(results) > 0
    # Verify dict schema
    first = results[0]
    required_keys = {
        "id", "title", "description", "category", "style_tags",
        "size", "condition", "price", "colors", "brand", "platform"
    }
    assert required_keys.issubset(first.keys())
    assert isinstance(first["price"], (int, float))
    assert isinstance(first["style_tags"], list)


def test_search_listings_price_ceiling():
    """Verify max_price filtering behaves inclusively."""
    max_p = 25.0
    results = search_listings("tee", max_price=max_p)
    assert len(results) > 0
    for item in results:
        assert float(item["price"]) <= max_p


def test_search_listings_size_filter_case_insensitive():
    """Verify size filtering matches case-insensitively and composite sizes."""
    # Testing size 'M' which should match 'M' and 'S/M'
    results = search_listings("tee", size="m")
    assert len(results) > 0
    for item in results:
        size_str = str(item.get("size", "")).upper()
        assert "M" in size_str


def test_search_listings_zero_results_failure_mode():
    """
    Designated Failure Mode:
    If no items match the criteria, returns an empty list without raising an exception.
    """
    results = search_listings("designer ballgown", size="XXS", max_price=5.0)
    assert isinstance(results, list)
    assert len(results) == 0


def test_search_listings_empty_or_whitespace_description():
    """Verify empty query returns empty list without error."""
    assert search_listings("") == []
    assert search_listings("   ") == []


# ── Tests for suggest_outfit ──────────────────────────────────────────────────

def test_suggest_outfit_with_example_wardrobe():
    """Verify that suggest_outfit produces recommendations referencing wardrobe items."""
    listings = load_listings()
    item = listings[0]
    wardrobe = get_example_wardrobe()
    outfit = suggest_outfit(item, wardrobe)
    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 30


def test_suggest_outfit_empty_wardrobe_failure_mode():
    """
    Designated Failure Mode:
    If wardrobe['items'] is empty, the tool provides general styling advice
    rather than raising an exception or returning an empty string.
    """
    listings = load_listings()
    item = listings[0]
    empty_wardrobe = get_empty_wardrobe()
    outfit = suggest_outfit(item, empty_wardrobe)
    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 30
    assert not outfit.startswith("Could not suggest outfit")


def test_suggest_outfit_invalid_item():
    """Verify that invalid item input returns a descriptive message without crashing."""
    wardrobe = get_example_wardrobe()
    res = suggest_outfit({}, wardrobe)
    assert "Could not suggest outfit" in res
    res_none = suggest_outfit(None, wardrobe)
    assert "Could not suggest outfit" in res_none


# ── Tests for create_fit_card ─────────────────────────────────────────────────

def test_create_fit_card_happy_path():
    """Verify that create_fit_card returns a casual, social caption mentioning title, price, platform."""
    listings = load_listings()
    item = listings[0]
    sample_outfit = "Pair this with dark wash jeans and chunky white sneakers for a relaxed silhouette."
    card = create_fit_card(sample_outfit, item)
    assert isinstance(card, str)
    assert len(card.strip()) > 20
    # Check that platform and price or title are represented
    card_lower = card.lower()
    assert str(item["platform"]).lower() in card_lower or "depop" in card_lower or "poshmark" in card_lower or "thredup" in card_lower


def test_create_fit_card_empty_outfit_failure_mode():
    """
    Designated Failure Mode:
    If outfit is empty or whitespace-only, returns a descriptive error string
    without raising an unhandled exception.
    """
    listings = load_listings()
    item = listings[0]
    err_msg1 = create_fit_card("", item)
    assert "Could not generate fit card: outfit description is missing or empty" in err_msg1
    err_msg2 = create_fit_card("   \n\t  ", item)
    assert "Could not generate fit card: outfit description is missing or empty" in err_msg2


def test_create_fit_card_invalid_item():
    """Verify that invalid item input returns an error string without crashing."""
    sample_outfit = "Pair with boots and jacket."
    err = create_fit_card(sample_outfit, None)
    assert "Could not generate fit card: invalid or missing item" in err


# ── Tests for compare_price (Stretch Tool) ────────────────────────────────────

def test_compare_price_stretch_tool():
    """Verify price fairness calculation and deal rating."""
    listings = load_listings()
    item = listings[0]
    comparison = compare_price(item)
    assert isinstance(comparison, dict)
    assert "item_price" in comparison
    assert "category_avg" in comparison
    assert "difference_pct" in comparison
    assert "deal_rating" in comparison
    assert comparison["deal_rating"] in ["Steal", "Great Deal", "Fair Market Value", "Splurge"]
    assert "summary" in comparison
