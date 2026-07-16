"""
Hakiki uptime monitor.
Checks TARGET_URL, and on a state change (up->down or down->up),
asks Groq (llama-3.3-70b-versatile) for a one-line plain-English diagnosis
and posts an alert to a Discord webhook.

Env vars required:
  TARGET_URL           - e.g. https://hakiki.vercel.app
  GROQ_API_KEY          - your Groq API key
  DISCORD_WEBHOOK_URL   - Discord channel webhook (Server Settings > Integrations > Webhooks)
"""

import os
import sys
import time
import json
import requests

TARGET_URL = os.environ.get("TARGET_URL")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "uptime_state.json"


def check_site():
    try:
        start = time.time()
        resp = requests.get(TARGET_URL, timeout=15)
        elapsed = round((time.time() - start) * 1000)
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}", elapsed
        if elapsed > 8000:
            return False, f"Slow response ({elapsed}ms)", elapsed
        return True, f"OK ({resp.status_code})", elapsed
    except requests.exceptions.Timeout:
        return False, "Request timed out (>15s)", None
    except requests.exceptions.ConnectionError as e:
        return False, f"Connection failed: {e}", None
    except Exception as e:
        return False, f"Unexpected error: {e}", None


def get_llm_diagnosis(reason):
    if not GROQ_API_KEY:
        return "No diagnosis available (GROQ_API_KEY not set)."
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a concise DevOps assistant. In 2-3 short sentences, "
                            "explain the likely cause of a website outage and give one "
                            "concrete next step. No preamble."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Site check failed with: {reason}. Site is hosted on Vercel.",
                    },
                ],
                "max_tokens": 150,
                "temperature": 0.3,
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(diagnosis unavailable: {e})"


def send_alert(message):
    if not DISCORD_WEBHOOK_URL:
        print("ALERT (no webhook configured):", message)
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except Exception as e:
        print("Failed to send Discord alert:", e)


def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f).get("status", "unknown")
    return "unknown"


def save_state(status):
    with open(STATE_FILE, "w") as f:
        json.dump(
            {"status": status, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())},
            f,
        )


def main():
    if not TARGET_URL:
        print("TARGET_URL not set")
        sys.exit(1)

    is_up, detail, elapsed = check_site()
    current_status = "up" if is_up else "down"
    last_status = load_last_state()

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}] {TARGET_URL} -> {detail}")

    if current_status != last_status:
        if current_status == "down":
            diagnosis = get_llm_diagnosis(detail)
            send_alert(
                f"🔴 **Hakiki is DOWN**\nURL: {TARGET_URL}\nReason: {detail}\n\n🤖 Diagnosis: {diagnosis}"
            )
        else:
            send_alert(f"🟢 **Hakiki is back UP**\nURL: {TARGET_URL}\nResponse: {detail} ({elapsed}ms)")
    else:
        print(f"No state change ({current_status}), skipping alert.")

    save_state(current_status)


if __name__ == "__main__":
    main()