"""
Property Scout — South Florida Listings Analyzer
─────────────────────────────────────────────────
Checks daily for new property listing emails from Aaron Burke,
fetches the Matrix MLS portal, scores each property on:
  • Privacy / nudity-friendly backyard
  • Water access (direct or <500 ft)
  • Pool
  • Rental separation potential

Sends an HTML email report to configured recipients.

Usage:
  python property_scout.py           # run one check cycle
  python property_scout.py --test    # use saved test data, no email sent
"""

from __future__ import annotations

import imaplib
import email as email_lib
import smtplib
import json
import os
import re
import ssl
import sys
import logging
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "property_scout_config.json"
STATE_PATH  = SCRIPT_DIR / "property_scout_state.json"
LOG_PATH    = SCRIPT_DIR / "property_scout.log"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)
log = logging.getLogger("property_scout")

def _print(msg: str, log_fn=None) -> None:
    """Log to file and optionally to an external log function (e.g. watchdog)."""
    log.info(msg)
    if log_fn:
        log_fn(f"[Scout] {msg}")
    else:
        print(f"[Scout] {msg}")


# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "gmail_email":      "karlmarx9193@gmail.com",
    "gmail_app_password": "",          # fill in: myaccount.google.com/apppasswords
    "sender_filter":    "southfloridaproperties@southeastmatrixmail.com",
    "recipients":       ["brian.mina17@gmail.com", "karlmarx9193@gmail.com"],
    "anthropic_api_key": "",           # or set ANTHROPIC_API_KEY env var
    "permalink_url":    "",            # optional: stable URL to skip email parsing
    "send_emails":      True,
    "score_threshold":  0,             # min overall score to include in report (0=all)
}

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            return {**DEFAULT_CONFIG, **data}
        except Exception as e:
            log.warning(f"Bad config file, using defaults: {e}")
    return dict(DEFAULT_CONFIG)

def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


# ── State (deduplication) ──────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"last_report_date": None, "seen_message_ids": [], "last_url": ""}

def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ── Step 1: Get the listings URL ───────────────────────────────────────────────
def get_listing_url_via_imap(config: dict, state: dict, log_fn=None) -> str | None:
    """
    Connect to Gmail via IMAP, find the latest email from the sender,
    and extract the 'View All Properties' link href.
    Returns the URL string, or None if not found.
    """
    app_pw = config.get("gmail_app_password", "").strip()
    if not app_pw:
        _print("No Gmail app password set — cannot read email via IMAP.", log_fn)
        return None

    _print("Connecting to Gmail IMAP…", log_fn)
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(config["gmail_email"], app_pw)
        imap.select("INBOX")

        # Search for emails from the sender
        sender = config["sender_filter"]
        _, data = imap.search(None, f'FROM "{sender}"')
        msg_ids = data[0].split()
        if not msg_ids:
            _print(f"No emails from {sender} found in INBOX.", log_fn)
            imap.logout()
            return None

        # Take the most recent
        latest_id = msg_ids[-1]
        _, msg_data = imap.fetch(latest_id, "(RFC822)")
        imap.logout()

        raw = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw)

        # Walk MIME parts for HTML body
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                html = part.get_payload(decode=True).decode("utf-8", errors="replace")
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True).lower()
                    href = a["href"]
                    if ("view all" in text or "all properties" in text or "view properties" in text):
                        _print(f"Found listing URL: {href[:80]}…", log_fn)
                        return href

        _print("Could not find 'View All Properties' link in email HTML.", log_fn)
        return None

    except Exception as exc:
        _print(f"IMAP error: {exc}", log_fn)
        return None


def get_listing_url(config: dict, state: dict, log_fn=None) -> str | None:
    """Return the URL to scrape: permalink > saved URL > IMAP extraction."""
    # 1. Explicit permalink in config
    if config.get("permalink_url", "").strip():
        return config["permalink_url"].strip()
    # 2. IMAP extraction
    return get_listing_url_via_imap(config, state, log_fn)


# ── Step 2: Fetch & extract property data ──────────────────────────────────────

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
        log.warning(f"DeepSeek failed ({e}), trying Gemini…")

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



def fetch_page(url: str, log_fn=None) -> str | None:
    """Fetch portal page using Playwright headless Chromium (handles JS SPAs)."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _print("Launching headless browser to fetch listings…", log_fn)
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
                _print("Selector wait timed out — grabbing page anyway", log_fn)
            html = page.content()
            browser.close()
        _print(f"Fetched page ({len(html):,} bytes via Playwright)", log_fn)
        return html
    except Exception as exc:
        _print(f"Playwright fetch error: {exc}", log_fn)
        return None


def extract_properties_with_claude(html: str, api_key: str, log_fn=None) -> list[dict]:
    """
    Use Claude to extract structured property data from the HTML page.
    Returns a list of property dicts.
    """
    # Truncate HTML to stay within context limits — keep first 80k chars
    # Also strip scripts/styles to focus on content
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "meta", "head"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Limit to ~60k characters
    text = text[:60000]

    _print(f"Sending {len(text):,} chars to AI for extraction…", log_fn)

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
        raw = _ai_complete(api_key, prompt, max_tokens=8000)
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        properties = json.loads(raw)
        _print(f"Extracted {len(properties)} properties.", log_fn)
        return properties
    except Exception as exc:
        _print(f"Extraction error: {exc}", log_fn)
        return []


# ── Step 3: Score properties ───────────────────────────────────────────────────
SCORING_PROMPT = """\
Score this South Florida property listing on four criteria. \
Return ONLY a JSON object, no explanation.

PROPERTY DATA:
{property_json}

SCORING CRITERIA — each 0–10:

1. privacy_score: How suitable is the backyard for clothing-optional/nudist use?
   10 = large private fenced yard, screened pool, no neighbors visible, "private" in description
   7  = decent-sized yard with fence/hedges
   4  = small yard, partial privacy
   1  = little to no yard, townhouse/condo with open patios
   0  = no outdoor private space

2. water_score: Proximity and quality of water access
   10 = direct ocean/intracoastal/bay frontage with dock
   9  = canal with dock/seawall
   7  = water view, water access nearby
   5  = within 500 feet of water (infer from description/address clues)
   3  = water access in neighborhood
   0  = no water access or mention

3. pool_score: Pool quality and features
   10 = private heated salt-water pool + spa/hot tub
   8  = private pool, screened/covered
   6  = private pool (basic)
   4  = community pool
   0  = no pool

4. rental_score: Potential for rental income separation
   10 = legal in-law suite / guest house / ADU with separate entrance
   8  = convertible space (garage apt, bonus room with bath)
   5  = extra bedroom/bathroom that could function as unit
   2  = large enough home to potentially split
   0  = no rental potential

Also provide:
- overall_score: weighted average (privacy×0.3, water×0.3, pool×0.2, rental×0.2)
- summary: 2–3 sentence plain-English summary of why this scored as it did
- highlights: list of 3–5 key selling points for THIS buyer's criteria
- concerns: list of any notable negatives

Return JSON with keys: privacy_score, water_score, pool_score, rental_score, \
overall_score, summary, highlights, concerns
"""

def score_property(prop: dict, api_key: str) -> dict:
    """Score a single property using AI (DeepSeek/Gemini)."""
    prop_json = json.dumps(prop, indent=2)[:4000]
    try:
        raw = _ai_complete(api_key, SCORING_PROMPT.format(property_json=prop_json), max_tokens=1000)
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        scores = json.loads(raw)
        return {**prop, **scores}
    except Exception as exc:
        log.warning(f"Scoring failed for {prop.get('address', '?')}: {exc}")
        return {**prop, "overall_score": 0, "summary": f"Scoring error: {exc}",
                "privacy_score": 0, "water_score": 0, "pool_score": 0,
                "rental_score": 0, "highlights": [], "concerns": []}


def score_all_properties(properties: list[dict], api_key: str, log_fn=None) -> list[dict]:
    """Score all properties and return sorted by overall_score descending."""
    _print(f"Scoring {len(properties)} properties…", log_fn)
    scored = []
    for i, prop in enumerate(properties, 1):
        addr = prop.get("address", f"Property {i}")
        _print(f"  Scoring {i}/{len(properties)}: {addr}", log_fn)
        scored.append(score_property(prop, api_key))

    scored.sort(key=lambda p: p.get("overall_score", 0), reverse=True)
    return scored


# ── Step 4: Build HTML report ──────────────────────────────────────────────────
def _score_bar(score: float | None) -> str:
    """Render a colored score bar."""
    if score is None:
        return "N/A"
    s = float(score)
    color = "#2ecc71" if s >= 7 else "#f39c12" if s >= 4 else "#e74c3c"
    filled = int(s)
    bar = "█" * filled + "░" * (10 - filled)
    return f'<span style="color:{color};font-family:monospace">{bar}</span> {s:.1f}/10'


def build_html_report(scored: list[dict], run_date: str, source_url: str) -> str:
    """Build a full HTML email body."""
    cards = []
    for rank, p in enumerate(scored, 1):
        addr      = p.get("address", "Unknown")
        city      = p.get("city", "")
        price     = f"${p.get('price', 0):,}" if p.get("price") else "—"
        beds      = p.get("beds", "—")
        baths     = p.get("baths", "—")
        sqft      = f"{p.get('sqft', 0):,}" if p.get("sqft") else "—"
        lot       = f"{p.get('lot_sqft', 0):,} sqft" if p.get("lot_sqft") else "—"
        yr        = p.get("year_built", "—")
        pool_yn   = "Yes" if p.get("pool") else ("Community" if p.get("pool") == "community" else "No")
        water_d   = p.get("water_description") or ("Waterfront" if p.get("waterfront") else "None mentioned")
        listing_url = p.get("url", "")
        link_html = f'<a href="{listing_url}" style="color:#3498db">View Listing</a>' if listing_url else ""
        dom       = f"{p.get('days_on_market')} days" if p.get("days_on_market") is not None else "—"

        overall   = p.get("overall_score", 0)
        ov_color  = "#2ecc71" if overall >= 7 else "#f39c12" if overall >= 4 else "#e74c3c"

        highlights_html = "".join(
            f"<li>{h}</li>" for h in (p.get("highlights") or [])
        )
        concerns_html = "".join(
            f"<li style='color:#e74c3c'>{c}</li>" for c in (p.get("concerns") or [])
        )

        cards.append(f"""
<div style="border:1px solid #ddd;border-radius:8px;margin:16px 0;padding:16px;
            background:#fafafa;font-family:Arial,sans-serif;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div>
      <span style="font-size:13px;color:#888">#{rank}</span>
      <strong style="font-size:17px;margin-left:8px">{addr}</strong>
      <span style="color:#888;margin-left:6px">{city}</span>
    </div>
    <div style="text-align:right">
      <div style="font-size:22px;font-weight:bold;color:{ov_color}">{overall:.1f}</div>
      <div style="font-size:11px;color:#888">overall</div>
    </div>
  </div>

  <table style="width:100%;font-size:13px;margin-bottom:10px">
    <tr>
      <td><strong>Price:</strong> {price}</td>
      <td><strong>Beds/Baths:</strong> {beds} bd / {baths} ba</td>
      <td><strong>Sqft:</strong> {sqft}</td>
      <td><strong>Lot:</strong> {lot}</td>
    </tr>
    <tr>
      <td><strong>Built:</strong> {yr}</td>
      <td><strong>Pool:</strong> {pool_yn}</td>
      <td><strong>Water:</strong> {water_d}</td>
      <td><strong>DOM:</strong> {dom}</td>
    </tr>
  </table>

  <table style="width:100%;font-size:13px;margin-bottom:10px;border-collapse:collapse">
    <tr>
      <td style="padding:3px 0;width:25%"><strong>🌿 Privacy:</strong></td>
      <td>{_score_bar(p.get("privacy_score"))}</td>
      <td style="padding:3px 0 3px 16px;width:25%"><strong>💧 Water:</strong></td>
      <td>{_score_bar(p.get("water_score"))}</td>
    </tr>
    <tr>
      <td style="padding:3px 0"><strong>🏊 Pool:</strong></td>
      <td>{_score_bar(p.get("pool_score"))}</td>
      <td style="padding:3px 0 3px 16px"><strong>🏠 Rental:</strong></td>
      <td>{_score_bar(p.get("rental_score"))}</td>
    </tr>
  </table>

  <p style="font-size:13px;color:#444;margin:8px 0">{p.get("summary", "")}</p>

  {"<ul style='font-size:12px;margin:4px 0'>" + highlights_html + "</ul>" if highlights_html else ""}
  {"<ul style='font-size:12px;margin:4px 0'>" + concerns_html + "</ul>" if concerns_html else ""}
  {f'<div style="margin-top:6px">{link_html}</div>' if link_html else ""}
</div>""")

    top3_summary = ""
    for p in scored[:3]:
        top3_summary += f"<li><strong>{p.get('address','?')}</strong> — {p.get('price','')}, Score {p.get('overall_score',0):.1f}/10</li>"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Property Scout Report {run_date}</title></head>
<body style="max-width:800px;margin:0 auto;padding:20px;font-family:Arial,sans-serif;color:#222">
  <h1 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:8px">
    🏠 Property Scout Report — {run_date}
  </h1>
  <p style="color:#666">
    {len(scored)} properties analyzed and ranked by suitability.
    Criteria: backyard privacy, water access, pool quality, rental potential.
  </p>
  {"<h3>Top Picks</h3><ol style='font-size:14px'>" + top3_summary + "</ol>" if top3_summary else ""}
  <hr style="border:none;border-top:1px solid #eee;margin:16px 0">
  {"".join(cards)}
  <p style="font-size:11px;color:#aaa;margin-top:24px">
    Source: <a href="{source_url}" style="color:#aaa">{source_url[:80]}</a><br>
    Generated by Property Scout at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
  </p>
</body>
</html>"""


# ── Step 5: Send email ─────────────────────────────────────────────────────────
def send_report_email(html_body: str, config: dict, run_date: str, log_fn=None) -> bool:
    """Send the HTML report via Gmail SMTP."""
    app_pw = config.get("gmail_app_password", "").strip()
    if not app_pw:
        _print("No Gmail app password — cannot send email. Saving report to disk.", log_fn)
        out = SCRIPT_DIR / f"property_report_{run_date.replace(' ','_')}.html"
        out.write_text(html_body, encoding="utf-8")
        _print(f"Report saved to {out}", log_fn)
        return False

    sender = config["gmail_email"]
    recipients = config.get("recipients", [sender])
    subject = f"Property Scout Report — {run_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Property Scout <{sender}>"
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    _print(f"Sending report to {recipients}…", log_fn)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(sender, app_pw)
            s.sendmail(sender, recipients, msg.as_string())
        _print("Report email sent successfully.", log_fn)
        return True
    except Exception as exc:
        _print(f"SMTP error: {exc}", log_fn)
        return False


# ── Main orchestrator ──────────────────────────────────────────────────────────

# ── Discord notification ───────────────────────────────────────────────────────
def send_discord_notification(scored, run_date, source_url, config, log_fn=None):
    """Post rich embeds to #house-search Discord channel via webhook."""
    webhook_url = config.get("discord_webhook_url", "").strip()
    if not webhook_url:
        return False

    def score_emoji(s):
        if s is None:
            return "\u2753"
        s = float(s)
        if s >= 8:
            return "\U0001f7e2"   # green circle
        if s >= 6:
            return "\U0001f7e1"   # yellow
        if s >= 4:
            return "\U0001f7e0"   # orange
        return "\U0001f534"       # red

    def bar(s):
        if s is None:
            return "N/A"
        filled = round(float(s))
        return "\u2588" * filled + "\u2591" * (10 - filled) + f" {float(s):.1f}"

    embeds = []

    # ── Summary embed (top 5) ─────────────────────────────────────────────────
    lines = []
    for i, p in enumerate(scored[:5], 1):
        addr  = p.get("address", "?")
        city  = p.get("city", "")
        price = f"${p.get('price', 0):,}" if p.get("price") else "\u2014"
        ov    = p.get("overall_score", 0)
        lines.append(f"{score_emoji(ov)} **#{i}** {addr}, {city} \u2014 {price} \u2014 **{ov:.1f}/10**")

    embeds.append({
        "title": f"\U0001f3e0 House Search \u2014 {run_date}",
        "description": f"**{len(scored)} properties** ranked.\n\n" + "\n".join(lines),
        "color": 0x3498DB,
        "footer": {"text": "Scored: privacy \u00b7 water \u00b7 pool \u00b7 rental"},
    })

    # ── Detail embeds for top 3 ───────────────────────────────────────────────
    for p in scored[:3]:
        ov    = p.get("overall_score", 0)
        addr  = p.get("address", "Unknown")
        city  = p.get("city", "")
        price = f"${p.get('price', 0):,}" if p.get("price") else "\u2014"
        color = 0x2ECC71 if ov >= 7 else 0xF39C12 if ov >= 4 else 0xE74C3C

        fields = [
            {"name": "Price",      "value": price,                                          "inline": True},
            {"name": "Beds/Baths", "value": f"{p.get('beds','?')} / {p.get('baths','?')}",  "inline": True},
            {"name": "Sqft",       "value": f"{p.get('sqft',0):,}" if p.get("sqft") else "\u2014", "inline": True},
            {"name": "\U0001f33f Privacy", "value": bar(p.get("privacy_score")), "inline": True},
            {"name": "\U0001f30a Water",   "value": bar(p.get("water_score")),   "inline": True},
            {"name": "\U0001f3ca Pool",    "value": bar(p.get("pool_score")),    "inline": True},
            {"name": "\U0001f3e1 Rental",  "value": bar(p.get("rental_score")),  "inline": True},
        ]
        if p.get("summary"):
            fields.append({"name": "Summary", "value": p["summary"][:300], "inline": False})
        if p.get("highlights"):
            fields.append({"name": "\u2705 Highlights",
                           "value": "\n".join(f"\u2022 {h}" for h in p["highlights"][:4]),
                           "inline": False})
        if p.get("concerns"):
            fields.append({"name": "\u26a0\ufe0f Concerns",
                           "value": "\n".join(f"\u2022 {c}" for c in p["concerns"][:3]),
                           "inline": False})

        embed = {
            "title": f"{score_emoji(ov)} {addr}, {city} \u2014 {ov:.1f}/10",
            "color": color,
            "fields": fields,
        }
        if p.get("url"):
            embed["url"] = p["url"]
        embeds.append(embed)

    payload = {"username": "Property Scout", "embeds": embeds}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=15)
        if resp.status_code in (200, 204):
            _print("Discord notification sent.", log_fn)
            return True
        _print(f"Discord webhook {resp.status_code}: {resp.text[:200]}", log_fn)
        return False
    except Exception as exc:
        _print(f"Discord error: {exc}", log_fn)
        return False


def run_check(log_fn=None, force: bool = False) -> bool:
    """
    Run one full check cycle.
    Returns True if a report was generated, False otherwise.

    Args:
        log_fn: optional callable(str) for status messages (e.g. watchdog's add_log)
        force:  if True, skip the 'already ran today' guard
    """
    config = load_config()
    state  = load_state()

    # API key passed through to _ai_complete (DeepSeek/Gemini — no Anthropic needed)
    api_key = config.get("anthropic_api_key", "").strip() or os.environ.get("ANTHROPIC_API_KEY", "") or "unused"

    today = date.today().isoformat()
    if not force and state.get("last_report_date") == today:
        _print(f"Already ran today ({today}). Use --force to rerun.", log_fn)
        return False

    run_date = datetime.now().strftime("%Y-%m-%d")
    _print(f"=== Property Scout starting {run_date} ===", log_fn)

    # 1. Get URL
    url = get_listing_url(config, state, log_fn)
    if not url:
        _print("No listing URL available. Set permalink_url in config or add Gmail app password.", log_fn)
        return False

    # 2. Fetch page
    html = fetch_page(url, log_fn)
    if not html:
        return False

    # 3. Extract properties
    properties = extract_properties_with_claude(html, api_key, log_fn)
    if not properties:
        _print("No properties extracted. The page may require JavaScript rendering.", log_fn)
        # Save raw HTML for inspection
        (SCRIPT_DIR / "last_fetch_debug.html").write_text(html, encoding="utf-8")
        _print("Saved raw HTML to last_fetch_debug.html for inspection.", log_fn)
        return False

    # 4. Score
    min_score = config.get("score_threshold", 0)
    scored = score_all_properties(properties, api_key, log_fn)
    filtered = [p for p in scored if p.get("overall_score", 0) >= min_score]
    _print(f"{len(filtered)} properties meet score threshold (>= {min_score}).", log_fn)

    # 5. Build and send report
    html_report = build_html_report(filtered, run_date, url)

    # Always save locally too
    out = SCRIPT_DIR / f"property_report_{run_date}.html"
    out.write_text(html_report, encoding="utf-8")
    _print(f"Report saved locally: {out}", log_fn)

    if config.get("send_emails", True):
        send_report_email(html_report, config, run_date, log_fn)
    send_discord_notification(filtered, run_date, url, config, log_fn)

    # Update state
    state["last_report_date"] = today
    state["last_url"] = url
    save_state(state)

    _print(f"=== Property Scout done. Top score: {scored[0].get('overall_score',0):.1f} ({scored[0].get('address','?')}) ===", log_fn)
    return True


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    force_run = "--force" in sys.argv or "--test" in sys.argv

    # Create default config if missing
    if not CONFIG_PATH.exists():
        cfg = dict(DEFAULT_CONFIG)
        # Pull API key from env if available
        cfg["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
        save_config(cfg)
        print(f"Created config template at {CONFIG_PATH}")
        print("Please fill in:")
        print("  • gmail_app_password  (https://myaccount.google.com/apppasswords)")
        print("  • permalink_url       (optional, from your Matrix MLS saved search)")
        print("  • anthropic_api_key   (or set ANTHROPIC_API_KEY env var)")

    success = run_check(force=force_run)
    sys.exit(0 if success else 1)
