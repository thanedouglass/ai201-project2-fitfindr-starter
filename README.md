# FitFindr — Secondhand Wardrobe Styling Agent

> 📹 **Demo Video (3–5 min):** [Watch on YouTube](https://youtu.be/hF7dO5rGr_Y) (`https://youtu.be/hF7dO5rGr_Y`)

FitFindr is an autonomous secondhand wardrobe styling agent powered by Groq and Gradio that searches thrifted listings, styles complete outfits with the user's existing wardrobe, and creates social-ready fit cards.


## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Tool Inventory

The agent uses three core tools defined in `tools.py`. The documented interfaces below strictly match the function signatures and type annotations in `tools.py`:

### 1. `search_listings`
- **Signature:** `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`
- **Purpose:** Searches the mock dataset of 40 secondhand listings (`data/listings.json`), filtering candidate items by maximum price and user size, and ranking matching items by keyword relevance.
- **Inputs:**
  - `description` (`str`): Free-text keywords describing the desired garment, aesthetic, or category (e.g., `"vintage graphic tee"`).
  - `size` (`str | None`, default `None`): Size string to filter by (e.g., `"M"`, `"L"`, `"S/M"`). Case-insensitive. `None` skips size filtering.
  - `max_price` (`float | None`, default `None`): Maximum price ceiling in USD (inclusive). `None` skips price filtering.
- **Returns:**
  - `list[dict]`: List of matching listing dictionaries sorted by relevance score descending. Each dictionary contains: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` if no listings match (does not raise an exception).

### 2. `suggest_outfit`
- **Signature:** `suggest_outfit(new_item: dict, wardrobe: dict) -> str`
- **Purpose:** Generates 1–2 complete outfit recommendations coordinating the prospective thrift find with items from the user's existing wardrobe, or provides general styling advice if the wardrobe is empty.
- **Inputs:**
  - `new_item` (`dict`): Listing dictionary representing the thrifted piece under consideration.
  - `wardrobe` (`dict`): User wardrobe dictionary containing an `"items"` list of wardrobe items (each with `id`, `name`, `category`, `colors`, `style_tags`, `notes`).
- **Returns:**
  - `str`: Non-empty styling recommendation string with pairing suggestions, silhouette balancing tips, and advice on tucking, cuffing, or layering.

### 3. `create_fit_card`
- **Signature:** `create_fit_card(outfit: str, new_item: dict) -> str`
- **Purpose:** Generates a short, authentic social media caption (Instagram/TikTok OOTD format) celebrating the secondhand find.
- **Inputs:**
  - `outfit` (`str`): Outfit styling suggestion string produced by `suggest_outfit()`.
  - `new_item` (`dict`): Listing dictionary for the thrifted item.
- **Returns:**
  - `str`: A 2–4 sentence social-ready caption naturally incorporating the item title, price, and marketplace platform once each, capturing the aesthetic vibe without sounding like marketing copy.

### 4. `compare_price` *(Stretch Tool)*
- **Signature:** `compare_price(item: dict, all_listings: list[dict] | None = None) -> dict`
- **Purpose:** Evaluates market fairness and potential savings by comparing the selected piece's price against all available listings in the same garment category in the mock dataset.
- **Inputs:**
  - `item` (`dict`): Candidate listing dictionary selected for purchase.
  - `all_listings` (`list[dict] | None`, default `None`): Dataset listings to benchmark against (defaults to loading `data/listings.json`).
- **Returns:**
  - `dict`: Formatted price comparison object containing `item_price` (float), `category` (str), `category_avg` (float), `difference_pct` (float), `deal_rating` (str: `"Steal"`, `"Great Deal"`, `"Fair Market Value"`, or `"Splurge"`), and `summary` (str: formatted badge string).

---

## Planning Loop & Logic

The planning loop is implemented in `run_agent(query: str, wardrobe: dict, style_profile: dict | None = None) -> dict` in `agent.py`. The agent does **not** blindly execute a fixed sequence of tools; rather, its behavior is dynamically driven by conditional branching on the session state:

1. **Initialization & Input Validation:** Initializes session state with `_new_session(query, wardrobe, style_profile)`. Guards against empty or whitespace-only queries by setting `session["error"]` with helpful query examples and returning immediately without invoking any tools.
2. **Query Parsing:** Uses regex parameter extraction (`parse_query()`) to parse the user's natural language request into `max_price` (e.g., `under $30`), `size` (e.g., `size M`), and cleaned search `description` (e.g., `"vintage graphic tee"`).
3. **Tool 1 Invocation (`search_listings`):** Queries the dataset with parsed parameters and stores results in `session["search_results"]`.
4. **Conditional Decision Point 1 (Zero-Results Branch & Diagnostic Analysis):**
   - If `search_results` is empty (`len == 0`), the agent **halts execution immediately**.
   - It runs an automated diagnostic analysis:
     * If a `size` filter was used, it checks if relaxing the size constraint reveals matching items and lists available sizes.
     * If a `max_price` ceiling was used, it checks if items exist at higher budgets and reports the starting price.
   - It populates `session["error"]` with actionable, numbered troubleshooting instructions and diagnostic insights.
   - It **does not** proceed to `suggest_outfit` or `create_fit_card` with invalid data.
5. **Item Selection & Tool 4 Invocation (`compare_price` — Stretch Tool):**
   - If listings are found, selects the top match: `session["selected_item"] = search_results[0]`.
   - Runs `compare_price(selected_item)` to benchmark the price against category averages and determine deal status (`"Steal"`, `"Great Deal"`, `"Fair Market Value"`, `"Splurge"`), storing results in `session["price_comparison"]`.
6. **Tool 2 Invocation (`suggest_outfit`):**
   - Calls `suggest_outfit(selected_item, wardrobe)`.
   - Inside `suggest_outfit`, inspects `wardrobe["items"]`: if populated, prompts the LLM for outfit combinations with specific named wardrobe pieces; if empty, dynamically prompts for general styling principles.
7. **Conditional Decision Point 2 (Outfit Validation):**
   - Validates that `outfit_suggestion` was generated successfully. If not, sets `session["error"]` and halts early.
8. **Tool 3 Invocation (`create_fit_card`):**
   - Calls `create_fit_card(outfit_suggestion, selected_item)` to create the final caption.
9. **Style Profile Memory Update (Stretch Feature):**
   - Records the style tags, viewed category, and platform in `session["style_profile"]` to retain aesthetic preferences across sessions.
10. **Return:** Returns the complete session dictionary to the Gradio interface.

---

## State Management Approach

FitFindr maintains state across all tool calls using a centralized `session` dictionary initialized at the start of `run_agent()`. The session acts as the single source of truth throughout the lifecycle of the user interaction:

```python
session = {
    "query": query,                          # str: Original raw user prompt
    "parsed": {                              # dict: Extracted search parameters
        "description": "...",                # str: Keywords for search
        "size": "...",                       # str or None: Extracted size filter
        "max_price": 0.0                     # float or None: Extracted price ceiling
    },
    "search_results": [],                    # list[dict]: All matching listings from search_listings()
    "selected_item": None,                   # dict or None: Top candidate listing chosen for styling
    "price_comparison": None,                # dict or None: Stretch market price fairness analysis
    "wardrobe": wardrobe,                    # dict: User's closet items (example or empty template)
    "outfit_suggestion": None,               # str: Generated outfit combinations from suggest_outfit()
    "fit_card": None,                        # str: Social media caption from create_fit_card()
    "error": None,                           # str or None: Actionable error message if halted early
    "fallback_applied": False,               # bool: Stretch indicator for fallback analysis
    "fallback_notes": None,                  # str or None: Stretch diagnostic notes
    "style_profile": style_profile or {},    # dict: User style memory (aesthetic tags, viewed categories)
}
```

### State Flow Between Tools:
- **`query` → `parsed`**: Raw user text is parsed into parameters without requiring manual form inputs.
- **`parsed` → `search_listings` → `search_results`**: Parameters are passed into Tool 1, storing the result list in session state.
- **`search_results[0]` → `selected_item`**: The top-ranked item is stored in `selected_item`.
- **`selected_item` → `compare_price` → `price_comparison`**: Top find is evaluated for market fairness.
- **`selected_item` + `wardrobe` → `suggest_outfit` → `outfit_suggestion`**: Both data structures flow into Tool 2 without user re-entry.
- **`outfit_suggestion` + `selected_item` → `create_fit_card` → `fit_card`**: Both previous outputs flow into Tool 3.
- **`selected_item` → `style_profile`**: Aesthetic tags are saved to style memory across runs.
- **`session["error"]`**: Serves as a circuit breaker. If an error occurs, downstream tools are bypassed and the error is cleanly surfaced.

---

## Interaction Walkthrough

**User query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Tool called:**
- **Tool:** `search_listings`
- **Input:** `description="vintage graphic tee", size=None, max_price=30.0`
- **Why this tool:** The agent must search the inventory to identify candidate thrifted pieces matching the user's aesthetic keywords and budget ceiling before any outfit coordination can take place.
- **Output:** Returns matching listings, with the top-ranked item being:
  `{'id': 'lst_006', 'title': 'Graphic Tee — 2003 Tour Bootleg Style', 'category': 'tops', 'price': 24.0, 'size': 'L', 'condition': 'good', 'platform': 'depop', 'style_tags': ['vintage', 'grunge', 'graphic tee', 'streetwear'], ...}`

**Step 2 — Tool called (Stretch Tool):**
- **Tool:** `compare_price`
- **Input:** `item=session["selected_item"]`
- **Why this tool:** Evaluates the listing price against all tops in the dataset to inform the user of potential savings and market fairness.
- **Output:** `{'item_price': 24.0, 'category_avg': 21.73, 'difference_pct': 10.4, 'deal_rating': 'Fair Market Value', 'summary': '⚖️ Fair Market Value ($24.00 vs tops average of $21.73, 10% above category average)'}`

**Step 3 — Tool called:**
- **Tool:** `suggest_outfit`
- **Input:**
  - `new_item`: Listing `lst_006` ("Graphic Tee — 2003 Tour Bootleg Style")
  - `wardrobe`: User wardrobe containing `w_001` ("Baggy straight-leg jeans, dark wash"), `w_008` ("Black combat boots"), and `w_005` ("Black cropped zip hoodie")
- **Why this tool:** Analyzes the thrifted band tee against the user's specific closet pieces to provide personalized, complete outfit combinations and styling advice.
- **Output:**
  *"Look 1: Grunge Classic — Pair the boxy Graphic Tee with your [w_001] Baggy straight-leg jeans. The high waist anchors the loose tee, preventing a shapeless silhouette. Lace up your [w_008] Black combat boots and layer with your [w_010] Black crossbody bag for a utilitarian touch."*

**Step 4 — Tool called:**
- **Tool:** `create_fit_card`
- **Input:**
  - `outfit`: The outfit suggestion string from Step 3
  - `new_item`: Listing `lst_006`
- **Why this tool:** Synthesizes the find and styling concept into an authentic, shareable social media caption.
- **Output:** *"pulled this 2003 tour bootleg style graphic tee off Depop for only $24.00 and it’s the ultimate layering piece 🖤. threw it under a cropped hoodie with wide-leg khakis for that perfect mix of grunge and streetwear."*

**Final output to user:**
The Gradio web interface renders all three panels:
1. **🛍️ Top listing found:** Displays item title, price ($24.00), platform (Depop), condition (Good), size (L), market price check (`⚖️ Fair Market Value`), tags, and description.
2. **👗 Outfit idea:** Displays the coordinated outfit recommendations featuring specific wardrobe pieces.
3. **✨ Your fit card:** Displays the shareable social media caption.

---

## Error Handling and Fail Points

Every tool is designed to handle failure modes gracefully without crashing the agent or failing silently.

| Tool / Component | Failure mode | Agent response |
|------------------|-------------|----------------|
| **User Query** | Empty or whitespace-only input string. | Immediately detected by the planning loop. Halts execution and returns actionable instructions asking the user to provide garment keywords, size, or price. |
| `search_listings` | No listings match search description, size, or price limit. | Returns `[]` without raising an exception. The planning loop detects the empty result list, executes an automated diagnostic test (checking whether relaxing the size filter or raising the price ceiling reveals matches), halts execution, and populates `session["error"]` with specific, numbered recommendations. Downstream tools are skipped. |
| `suggest_outfit` | User's wardrobe is empty (`wardrobe['items'] == []`). | The tool detects the empty wardrobe and dynamically switches prompts to ask the LLM for versatile, general styling principles, silhouette balancing tips, and color combinations for the piece rather than failing. |
| `create_fit_card` | Outfit input string is missing, empty, or whitespace-only. | The tool validates the `outfit` string before invoking the LLM. If invalid or empty, it returns a descriptive error string: `"Could not generate fit card: outfit description is missing or empty. Please ensure an outfit recommendation is generated first."` without raising an exception. |
| `compare_price` | Item is missing, unpriced, or has no category peers. | Returns a safe fallback dictionary with `"deal_rating": "Fair Market Value"` without disrupting the agent loop. |

### Concrete Examples from Testing:

1. **`search_listings` zero-match test:**
   - *Test input:* `search_listings("designer ballgown", size="XXS", max_price=5.0)`
   - *Observed behavior:* Returned `[]`. When executed via `run_agent()`, the agent halted early and returned:
     ```text
     No secondhand listings found matching 'designer ballgown' with constraints (size 'XXS', max price $5.00).

     What to try next:
     1. Broaden your search terms (e.g., try simpler keywords like 'jacket', 'tee', or 'jeans').
     2. Remove or relax the size filter to see pieces with flexible fits or adjacent sizes.
     3. Raise your price ceiling to view premium or vintage collector pieces.
     ```
     `session["selected_item"]`, `session["outfit_suggestion"]`, and `session["fit_card"]` remained `None`. Downstream tools were completely bypassed.

2. **`suggest_outfit` empty wardrobe test:**
   - *Test input:* `suggest_outfit(new_item=top_item, wardrobe=get_empty_wardrobe())`
   - *Observed behavior:* Successfully returned versatile general styling concepts:
     ```text
     This faded, boxy 2003 bootleg tee is a grunge essential! Since your wardrobe is empty, start with these two versatile concepts:
     1. The Streetwear Staple: Pair the tee with high-waisted, wide-leg denim jorts or relaxed cargo pants.
     2. The Casual Chic: Style the tee with black or dark wash skinny jeans to contrast the boxy top...
     ```
     No exceptions raised; generated complete styling guidance for a new user.

3. **`create_fit_card` empty outfit test:**
   - *Test input:* `create_fit_card(outfit="", new_item=top_item)`
   - *Observed behavior:* Returned descriptive error string:
     ```text
     Could not generate fit card: outfit description is missing or empty. Please ensure an outfit recommendation is generated first.
     ```
     Zero crashes or unhandled exceptions.

4. **Input query validation test:**
   - *Test input:* `handle_query("", "Example wardrobe")`
   - *Observed behavior:* Returned `"⚠️ Please enter a query in the search box above..."` in the listing output panel, leaving outfit and fit card panels empty.

---

## Stretch Goals Implemented

We implemented three distinct stretch goals to enhance FitFindr beyond the baseline specifications:

1. **Price Comparison Tool (`compare_price`)**:
   - Compares the candidate listing's price against all available listings in the same garment category.
   - Computes category average, percentage deviation, and assigns a qualitative deal badge (`"🔥 Steal"`, `"🏷️ Great Deal"`, `"⚖️ Fair Market Value"`, `"💎 Premium / Splurge"`).
   - Displayed prominently in the top listing panel in the UI.

2. **Automated Diagnostic Analysis on Zero Results**:
   - When a query yields 0 results, the agent does not merely stop; it programmatically tests relaxed constraints:
     - Checks if dropping the size constraint uncovers matching pieces and lists available sizes.
     - Checks if increasing the budget uncovers matching pieces and identifies the lowest price threshold.
   - Formats these diagnostic insights directly into actionable user feedback.

3. **Style Profile Memory System (`style_profile`)**:
   - The session state tracks user style history across multiple interactions.
   - Automatically harvests style tags (e.g., `vintage`, `grunge`, `streetwear`) and viewed categories from selected finds to maintain an evolving user aesthetic profile.

---

## Spec Reflection

**One way planning.md helped during implementation:**
Defining the exact function signatures, parameter schemas, and session dictionary fields in `planning.md` prior to writing code established clear contracts between the tools and the planning loop. Because the session state structure (`query`, `parsed`, `search_results`, `selected_item`, `price_comparison`, `wardrobe`, `outfit_suggestion`, `fit_card`, `error`) was fully designed beforehand, each tool could be implemented and tested in isolation with pytest before assembling the planning loop in `agent.py`. In addition, pre-specifying the zero-results failure condition made the conditional circuit breaker in the planning loop obvious and straightforward to implement.

**One divergence from your spec, and why:**
Our initial spec anticipated using simple string splitting to extract search terms, but during early testing with natural language inputs like `"vintage graphic tee under $30, size M"`, numeric price tokens and size abbreviations contaminated the description keywords and degraded search relevance. To resolve this, we diverged from simple string splitting and implemented dedicated regex-based extraction to peel off price constraints and clothing sizes first, passing only the clean residual garment keywords to `search_listings()`.

---

## AI Usage Transparency

In accordance with AI usage transparency standards, here is the full record of how AI tools were directed and reviewed during this project:

1. **Tool 1 Implementation (`search_listings`):**
   - *Direction given:* Prompted AI with the Tool 1 specification from `planning.md` (inputs, return schemas, keyword overlap scoring, and failure handling) along with the structure of `data/listings.json`.
   - *AI output:* Generated an initial implementation that used exact string equality for size (`item["size"] == size`) and only checked keywords against `item["description"]`.
   - *Revision/Override:* We revised the size matching logic to be case-insensitive and support composite sizes (such as matching `"M"` against `"S/M"` or `"XL"` against `"XL (oversized)"`). We also expanded the keyword scoring function to check against `item["title"]`, `item["description"]`, `item["category"]`, and `item["style_tags"]`, weighting title matches higher for better relevance.

2. **Planning Loop Architecture (`agent.py`):**
   - *Direction given:* Provided the architecture diagram and Planning Loop section from `planning.md` and asked AI to scaffold `run_agent()`.
   - *AI output:* Generated code that unconditionally executed all three tools in a single `try/except` block, passing empty results into `suggest_outfit`.
   - *Revision/Override:* We discarded the unconditional sequence and replaced it with explicit state-based conditional branching (`if not session["search_results"]:`), ensuring that the agent halts early on empty search results and returns actionable advice rather than propagating empty data into LLM prompts. We also added diagnostic relaxation analysis.

3. **LLM Runtime Integration (`tools.py`):**
   - *Model Selected:* Groq API with `qwen/qwen3.8-27b` (high-speed, highly articulate open-weights model).
   - *Review & Safeguards:* Wrapped all external LLM completions in structured `try/except` blocks with deterministic, domain-aware fallback text so that network blips or rate limits never crash the application.

4. **Automated Verification:**
   - Designed and ran a 25-test automated test suite (`pytest`) covering tool functions, error branches, state persistence, query parsing, and Gradio interface handling with 100% pass rate.

---

## Demo Video

- **Link:** [FitFindr 3–5 Minute Walkthrough on YouTube](https://youtu.be/hF7dO5rGr_Y) (`https://youtu.be/hF7dO5rGr_Y`)
- **Duration:** 3–5 minutes
- **What the demo demonstrates:**
  1. Complete multi-step interaction from natural language query to final fit card using all 3 core tools and stretch tools.
  2. Narration explaining each tool invocation, why it was chosen, and how state flows through the session dict.
  3. Visible inspection of state passing from `search_listings` → `suggest_outfit` → `create_fit_card`.
  4. Deliberate failure triggering with an impossible query (`"designer ballgown size XXS under $5"`), demonstrating graceful recovery and actionable error messaging.
