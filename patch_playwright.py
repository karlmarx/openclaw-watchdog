"""
Patch property_scout.py:
1. Replace requests-based fetch_page with Playwright headless browser fetch
2. Replace anthropic client calls with DeepSeek (OpenAI-compatible) + Gemini fallback
3. Add deepseek_api_key to config usage
"""
import sys

path = r"C:\Users\50420\.openclaw\watchdog\property_scout.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

if "playwright" in content:
    print("Already patched with playwright.")
    sys.exit(0)

# ── 1. Replace fetch_page ─────────────────────────────────────────────────────
OLD_FETCH = '''def fetch_page(url: str, log_fn=None) -> str | None:
    """Fetch the portal page HTML."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    _print(f"Fetching listings page\u2026", log_fn)
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        _print(f"Fetched page ({len(resp.text):,} bytes, status {resp.status_code})", log_fn)
        return resp.text
    except Exception as exc:
        _print(f"Failed to fetch page: {exc}", log_fn)
        return None'''

NEW_FETCH = '''def fetch_page(url: str, log_fn=None) -> str | None:
    """Fetch portal page using Playwright headless Chromium (handles JS SPAs)."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _print("Launching headless browser to fetch listings\u2026", log_fn)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=45000)
            # Wait for listing cards to appear
            try:
                page.wait_for_selector(
                    "[class*='property'], [class*='listing'], [class*='card'], [data-testid*='property']",
                    timeout=15000,
                )
            except PWTimeout:
                _print("Selector wait timed out \u2014 grabbing page anyway", log_fn)
            html = page.content()
            browser.close()
        _print(f"Fetched page ({len(html):,} bytes via Playwright)", log_fn)
        return html
    except Exception as exc:
        _print(f"Playwright fetch error: {exc}", log_fn)
        return None'''

if OLD_FETCH not in content:
    print("ERROR: could not find fetch_page to replace")
    sys.exit(1)
content = content.replace(OLD_FETCH, NEW_FETCH)
print("Patched fetch_page -> Playwright")

# ── 2. Replace anthropic client in extract_properties_with_claude ────────────
OLD_EXTRACT_CLIENT = '''    _print(f"Sending {len(text):,} chars to Claude for extraction\u2026", log_fn)

    client = anthropic.Anthropic(api_key=api_key)
    prompt = f"""You are analyzing a real estate listings page. Extract ALL property listings from the text below.

For each property return a JSON object with these fields (use null if unknown):
- id: unique identifier or MLS number
- address: full street address
- city: city name
- price: asking price as integer
- beds: number of bedrooms (integer)
- baths: number of bathrooms (float)
- sqft: interior square footage (integer)
- lot_sqft: lot size in square feet (integer, convert acres: 1 acre=43560 sqft)
- year_built: year built (integer)
- pool: true/false or null
- waterfront: true/false
- water_description: any water-related text (canal, ocean, intracoastal, lake, etc.)
- description: full property description text
- features: list of feature strings
- url: link to individual listing if present
- days_on_market: integer or null

Return ONLY a JSON array of property objects, no other text.

PAGE TEXT:
{text}"""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()'''

NEW_EXTRACT_CLIENT = '''    _print(f"Sending {len(text):,} chars to AI for extraction\u2026", log_fn)

    prompt = f"""You are analyzing a real estate listings page. Extract ALL property listings from the text below.

For each property return a JSON object with these fields (use null if unknown):
- id: unique identifier or MLS number
- address: full street address
- city: city name
- price: asking price as integer
- beds: number of bedrooms (integer)
- baths: number of bathrooms (float)
- sqft: interior square footage (integer)
- lot_sqft: lot size in square feet (integer, convert acres: 1 acre=43560 sqft)
- year_built: year built (integer)
- pool: true/false or null
- waterfront: true/false
- water_description: any water-related text (canal, ocean, intracoastal, lake, etc.)
- description: full property description text
- features: list of feature strings
- url: link to individual listing if present
- days_on_market: integer or null

Return ONLY a JSON array of property objects, no other text.

PAGE TEXT:
{text}"""

    try:
        raw = _ai_complete(api_key, prompt, max_tokens=8000)'''

if OLD_EXTRACT_CLIENT not in content:
    print("ERROR: could not find extract client block")
    sys.exit(1)
content = content.replace(OLD_EXTRACT_CLIENT, NEW_EXTRACT_CLIENT)
print("Patched extract_properties_with_claude")

# ── 3. Replace anthropic client in score_property ────────────────────────────
OLD_SCORE = '''def score_property(prop: dict, api_key: str) -> dict:
    """Score a single property using Claude Sonnet."""
    client = anthropic.Anthropic(api_key=api_key)
    prop_json = json.dumps(prop, indent=2)[:4000]  # cap size

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": SCORING_PROMPT.format(property_json=prop_json),
            }],
        )
        raw = msg.content[0].text.strip()'''

NEW_SCORE = '''def score_property(prop: dict, api_key: str) -> dict:
    """Score a single property using AI (DeepSeek/Gemini)."""
    prop_json = json.dumps(prop, indent=2)[:4000]
    try:
        raw = _ai_complete(api_key, SCORING_PROMPT.format(property_json=prop_json), max_tokens=1000)'''

if OLD_SCORE not in content:
    print("ERROR: could not find score_property client block")
    sys.exit(1)
content = content.replace(OLD_SCORE, NEW_SCORE)
print("Patched score_property")

# ── 4. Add _ai_complete helper + import openai before the fetch_page fn ──────
AI_HELPER = '''
def _ai_complete(api_key: str, prompt: str, max_tokens: int = 2000) -> str:
    """
    Call DeepSeek (primary) or Gemini (fallback) via OpenAI-compatible API.
    Falls back automatically on 401/402/429.
    """
    import openai as _openai

    # --- DeepSeek first ---
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "sk-a2f4a39d653a413b921057182e53320e")
    try:
        client = _openai.OpenAI(api_key=ds_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning(f"DeepSeek failed ({e}), trying Gemini\u2026")

    # --- Gemini fallback ---
    gem_key = os.environ.get("GEMINI_API_KEY", "AIzaSyC-IKzzMcu3A4F9DSTABTkuW5cLuy2nvAU")
    try:
        client = _openai.OpenAI(
            api_key=gem_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        resp = client.chat.completions.create(
            model="gemini-2.0-flash",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"Both AI backends failed. Last error: {e}")


'''

# Insert before fetch_page
insert_at = content.find("\ndef fetch_page(")
if insert_at == -1:
    print("ERROR: could not find fetch_page insertion point")
    sys.exit(1)
content = content[:insert_at] + "\n" + AI_HELPER + content[insert_at:]
print("Added _ai_complete helper")

# ── 5. Add openai to imports ──────────────────────────────────────────────────
if "import openai" not in content:
    content = content.replace("import anthropic\n", "import anthropic\ntry:\n    import openai\nexcept ImportError:\n    openai = None  # installed on demand\n")
    print("Added openai import guard")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("\nAll patches applied successfully.")
