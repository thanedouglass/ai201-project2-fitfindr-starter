"""
tests/test_agent.py

Exhaustive tests for FitFindr planning loop and state management:
- Natural language query parser (prices, sizes, keywords)
- Happy path state transitions (search_results → selected_item → outfit_suggestion → fit_card)
- Error handling & zero-results early exit (actionable troubleshooting advice)
- Empty query validation
- Empty wardrobe branch
- Style profile memory tracking across sessions
"""

import pytest
from agent import parse_query, run_agent, _new_session
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Tests for parse_query ─────────────────────────────────────────────────────

def test_parse_query_full_specs():
    """Verify parsing of description, size, and price."""
    q = "vintage graphic tee under $30, size M"
    parsed = parse_query(q)
    assert parsed["max_price"] == 30.0
    assert parsed["size"] == "M"
    assert "vintage graphic tee" in parsed["description"]


def test_parse_query_only_price():
    """Verify parsing with only price constraint."""
    q = "flowy midi skirt under $40"
    parsed = parse_query(q)
    assert parsed["max_price"] == 40.0
    assert parsed["size"] is None
    assert "flowy midi skirt" in parsed["description"]


def test_parse_query_only_size():
    """Verify parsing with size and no price."""
    q = "black combat boots size 8"
    parsed = parse_query(q)
    assert parsed["max_price"] is None
    assert parsed["size"] == "8"
    assert "black combat boots" in parsed["description"]


def test_parse_query_empty():
    """Verify parsing with empty string."""
    parsed = parse_query("")
    assert parsed["description"] == ""
    assert parsed["size"] is None
    assert parsed["max_price"] is None


# ── Tests for run_agent & State Management ────────────────────────────────────

def test_run_agent_happy_path_state_flow():
    """
    Verify complete happy path state management:
    item returned by search_listings passes into selected_item,
    which passes to suggest_outfit, and outfit passes to create_fit_card.
    """
    wardrobe = get_example_wardrobe()
    session = run_agent("vintage graphic tee under $30", wardrobe)

    # 1. Check error status
    assert session["error"] is None

    # 2. Check search results
    assert isinstance(session["search_results"], list)
    assert len(session["search_results"]) > 0

    # 3. Check selected item persistence
    assert session["selected_item"] is not None
    assert session["selected_item"] == session["search_results"][0]

    # 4. Check outfit suggestion
    assert isinstance(session["outfit_suggestion"], str)
    assert len(session["outfit_suggestion"].strip()) > 30

    # 5. Check fit card
    assert isinstance(session["fit_card"], str)
    assert len(session["fit_card"].strip()) > 20

    # 6. Check stretch price comparison
    assert session.get("price_comparison") is not None
    assert "deal_rating" in session["price_comparison"]


def test_run_agent_zero_results_error_handling():
    """
    Verify that when search returns 0 results:
    - Downstream tools (suggest_outfit, create_fit_card) are NOT executed.
    - session["error"] contains actionable troubleshooting instructions.
    - session["outfit_suggestion"] and session["fit_card"] remain None.
    """
    wardrobe = get_example_wardrobe()
    # Deliberate impossible query
    session = run_agent("designer ballgown size XXS under $5", wardrobe)

    assert session["error"] is not None
    assert "No secondhand listings found" in session["error"]
    assert "What to try next:" in session["error"]
    assert "Broaden your search terms" in session["error"]

    # Downstream tools must be skipped
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_run_agent_empty_query():
    """Verify that an empty query halts immediately with actionable message."""
    wardrobe = get_example_wardrobe()
    session = run_agent("   ", wardrobe)

    assert session["error"] is not None
    assert "No search query provided" in session["error"]
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None


def test_run_agent_empty_wardrobe_path():
    """Verify agent runs cleanly and provides styling even when user wardrobe is empty."""
    empty_wardrobe = get_empty_wardrobe()
    session = run_agent("black combat boots size 8", empty_wardrobe)

    assert session["error"] is None
    assert session["selected_item"] is not None
    assert session["outfit_suggestion"] is not None
    assert session["fit_card"] is not None


def test_run_agent_style_profile_memory_stretch():
    """Verify that style profile memory updates across session runs."""
    profile = {"favorite_tags": [], "categories_viewed": []}
    wardrobe = get_example_wardrobe()

    session = run_agent("vintage graphic tee under $30", wardrobe, style_profile=profile)
    assert session["error"] is None
    assert len(profile["favorite_tags"]) > 0
    assert len(profile["categories_viewed"]) > 0
    assert "tops" in profile["categories_viewed"]
