import os
import json
import time
import requests
import fcntl
import hashlib

CONFIG_FILE = "config.json"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("[ERROR] config.json not found.")
        return None
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print("[INFO] config.json updated.")


def is_new_version(remote_url, local_path):
    try:
        response = requests.get(remote_url)
        if response.status_code != 200:
            return False
        remote_hash = hashlib.sha256(response.content).hexdigest()
        if not os.path.exists(local_path):
            return True
        with open(local_path, "rb") as f:
            local_hash = hashlib.sha256(f.read()).hexdigest()
        return remote_hash != local_hash
    except Exception as e:
        print(f"[ERROR] Failed to compare versions: {e}")
        return False


def update_scripts(config):
    repo = config.get("github_repo")
    files = config.get("files_to_update", [])
    if not repo.endswith("/"):
        repo += "/"

    for script in files:
        raw_url = repo.replace("github.com", "raw.githubusercontent.com").replace("/tree/", "/") + script
        if is_new_version(raw_url, script):
            try:
                response = requests.get(raw_url)
                if response.status_code == 200:
                    with open(script, "wb") as f:
                        f.write(response.content)
                    print(f"[INFO] Updated: {script}")
                else:
                    print(f"[ERROR] Failed to fetch {script}: {response.status_code}")
            except Exception as e:
                print(f"[ERROR] Exception while updating {script}: {e}")
        else:
            print(f"[INFO] {script} is up-to-date.")


def fetch_and_update_config(config):
    config_url = config.get("config_url")
    token = config.get("token")
    if not config_url or not token:
        print("[ERROR] Missing 'config_url' or 'token'.")
        return

    try:
        response = requests.post(config_url, json={"token": token}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                print("[INFO] Merging API config fields into config.json.")
                new_config = config.copy()
                new_config.update(data)
                if new_config != config:
                    save_config(new_config)
                else:
                    print("[INFO] Config unchanged. No update needed.")
            else:
                print("[WARN] Unexpected response format from API.")
        else:
            print(f"[WARN] API response {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch config from API: {e}")


def main():
    config = load_config()
    if not config:
        return

    lock_path = config.get("lock_file", "/tmp/update_agent.lock")
    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fetch_and_update_config(config)
            update_scripts(config)
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    except BlockingIOError:
        print("[INFO] Another instance is already running. Exiting.")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")


if __name__ == "__main__":
    main()
