"""Patch property_scout.py to add Discord webhook support."""
import sys

DISCORD_FN = r'''

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

'''

OLD_SEND = '''    if config.get("send_emails", True):
        send_report_email(html_report, config, run_date, log_fn)'''

NEW_SEND = '''    if config.get("send_emails", True):
        send_report_email(html_report, config, run_date, log_fn)
    send_discord_notification(filtered, run_date, url, config, log_fn)'''

path = r"C:\Users\50420\.openclaw\watchdog\property_scout.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

if "send_discord_notification" in content:
    print("Already patched.")
    sys.exit(0)

# Insert function before run_check
insert_at = content.find("\ndef run_check(")
if insert_at == -1:
    print("ERROR: could not find run_check")
    sys.exit(1)

content = content[:insert_at] + DISCORD_FN + content[insert_at:]

# Wire into run_check
if OLD_SEND not in content:
    print("ERROR: could not find send_emails block")
    sys.exit(1)

content = content.replace(OLD_SEND, NEW_SEND)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched successfully.")
