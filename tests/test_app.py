"""
tests/test_app.py

Tests for Gradio interface handler in app.py:
- handle_query with valid input
- handle_query with empty query
- handle_query with impossible zero-result query
- handle_query with empty wardrobe option
"""

import pytest
from app import handle_query


def test_handle_query_empty_input():
    """Verify handle_query returns early error when user query is empty."""
    listing_text, outfit, fit_card = handle_query("", "Example wardrobe")
    assert "Please enter a query" in listing_text
    assert outfit == ""
    assert fit_card == ""


def test_handle_query_happy_path():
    """Verify handle_query populates all three UI panels on success."""
    listing_text, outfit, fit_card = handle_query("vintage graphic tee under $30", "Example wardrobe")
    assert "Graphic Tee" in listing_text or "Vintage" in listing_text
    assert "Price:" in listing_text
    assert len(outfit.strip()) > 30
    assert len(fit_card.strip()) > 20


def test_handle_query_zero_results():
    """Verify handle_query formats error notice in the first panel and leaves others empty."""
    listing_text, outfit, fit_card = handle_query("designer ballgown size XXS under $5", "Example wardrobe")
    assert "Search Notice" in listing_text
    assert "What to try next:" in listing_text
    assert outfit == ""
    assert fit_card == ""


def test_handle_query_empty_wardrobe():
    """Verify handle_query handles empty wardrobe selection without error."""
    listing_text, outfit, fit_card = handle_query("black combat boots size 8", "Empty wardrobe (new user)")
    assert "Price:" in listing_text
    assert len(outfit.strip()) > 30
    assert len(fit_card.strip()) > 20
