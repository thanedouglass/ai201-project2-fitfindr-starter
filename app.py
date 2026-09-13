"""
app.py

Gradio interface for FitFindr. Maps the user input query and wardrobe
selection to the planning loop (run_agent), formatting results across three
dedicated output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (typically http://127.0.0.1:7860).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of three strings:
            (listing_text, outfit_suggestion, fit_card)
        Each string maps to one of the three output panels in the UI.
    """
    # 1. Guard against an empty query
    if not user_query or not user_query.strip():
        error_msg = (
            "⚠️ Please enter a query in the search box above.\n\n"
            "Examples:\n"
            "• 'vintage graphic tee under $30, size M'\n"
            "• 'black combat boots size 8'\n"
            "• 'flowy midi skirt under $40'"
        )
        return error_msg, "", ""

    # 2. Select the wardrobe based on user choice
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    # 3. Call run_agent() with the query and selected wardrobe
    session = run_agent(query=user_query.strip(), wardrobe=wardrobe)

    # 4. Check for error / early termination
    if session.get("error"):
        error_display = f"⚠️ Search Notice\n\n{session['error']}"
        return error_display, "", ""

    # 5. Format the selected listing for the first panel
    item = session.get("selected_item")
    if not item:
        return "No item details available.", "", ""

    title = item.get("title", "Unknown Piece")
    price = f"${item.get('price', 0.0):.2f}"
    platform = str(item.get("platform", "secondhand")).capitalize()
    size = item.get("size", "N/A")
    condition = str(item.get("condition", "N/A")).capitalize()
    category = str(item.get("category", "N/A")).capitalize()
    brand = item.get("brand") or "Vintage / Unbranded"
    colors = ", ".join(item.get("colors", [])) or "N/A"
    tags = ", ".join(f"#{t}" for t in item.get("style_tags", []))
    desc = item.get("description", "")

    # Price comparison analysis (stretch feature)
    price_comp = session.get("price_comparison")
    deal_info = ""
    if price_comp and "summary" in price_comp:
        deal_info = f"\nMarket Price Check: {price_comp['summary']}\n"

    listing_text = (
        f"🏷️ {title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Price: {price} | Platform: {platform} | Size: {size}\n"
        f"Condition: {condition} | Brand: {brand}\n"
        f"Category: {category} | Colors: {colors}\n"
        f"{deal_info}"
        f"Tags: {tags}\n\n"
        f"Description:\n{desc}"
    )

    outfit_text = session.get("outfit_suggestion") or ""
    fit_card_text = session.get("fit_card") or ""

    return listing_text, outfit_text, fit_card_text


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
