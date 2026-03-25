path = r"C:\Users\50420\.openclaw\watchdog\property_scout.py"
with open(path, encoding="utf-8") as f:
    c = f.read()

old = """    # --- DeepSeek first ---
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
        raise RuntimeError(f"Both AI backends failed. Last error: {e}")"""

new = """    # --- Gemini first ---
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
        log.warning(f"Gemini failed ({e}), trying DeepSeek\u2026")

    # --- DeepSeek fallback ---
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
        raise RuntimeError(f"Both AI backends failed. Last error: {e}")"""

if old not in c:
    print("ERROR: block not found")
else:
    c = c.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Done — Gemini first, DeepSeek fallback")
