#!/usr/bin/env python3
import requests
import json
import os
from datetime import datetime

# === CONFIG ===
AGENT_TOKEN = "xxxxxx" # read token from checks.json
CONFIG_URL = "https://www.zapacit.com/api/agent_config.php"
OUTPUT_FILE = "/etc/zapacit-agent/checks.json"

def get_existing_urls():
    if not os.path.exists(OUTPUT_FILE):
        return []
    try:
        with open(OUTPUT_FILE, "r") as f:
            data = json.load(f)
            return sorted([check["url"] for check in data.get("checks", [])])
    except Exception:
        return []

def get_new_urls(checks_list):
    try:
        return sorted([check["url"] for check in checks_list])
    except Exception as e:
        print(f"[ERROR] Unexpected data format in checks list: {e}")
        return []

def fetch_config():
    now = datetime.now().isoformat()
    print(f"[{now}] Fetching config...")

    try:
        response = requests.post(CONFIG_URL, json={"token": AGENT_TOKEN}, timeout=10)
        if response.status_code != 200:
            print(f"[ERROR] HTTP {response.status_code}: {response.text}")
            return

        data = response.json()
        # Handle both {"checks": [...]} or just [...] as the response
        new_checks = data["checks"] if isinstance(data, dict) and "checks" in data else data

        if not isinstance(new_checks, list):
            print("[ERROR] API response does not contain a valid list of checks.")
            return

        existing_urls = get_existing_urls()
        new_urls = get_new_urls(new_checks)

        if existing_urls == new_urls:
            print(f"[{now}] No change in check URLs. Skipping update.")
            return

        output = {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "agent_token": AGENT_TOKEN,
            "checks": new_checks
        }

        with open(OUTPUT_FILE, "w") as f:
            json.dump(output, f, indent=2)

        print(f"[{now}] Configuration updated and saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"[EXCEPTION] Could not fetch config: {e}")

if __name__ == "__main__":
    fetch_config()
