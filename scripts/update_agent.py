import os
import json
import requests
from datetime import datetime
from urllib.parse import urljoin
from filelock import FileLock, Timeout

CONFIG_FILE = "config.json"
DEFAULT_REPO = "https://raw.githubusercontent.com/silasistefan-personal/zapacit.com/main/scripts/"
DEFAULT_LOCK_FILE = "update_agent.lock"
DEFAULT_SCRIPTS = ["run_agent.py", "local_agent.py"]
CONFIG_URL = "https://www.zapacit.com/api/agent_config.php"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to read {CONFIG_FILE}: {e}")
    return {}

def fetch_config_from_api(token):
    try:
        response = requests.post(CONFIG_URL, json={"token": token}, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[ERROR] Could not fetch config: {response.text}")
    except Exception as e:
        print(f"[ERROR] Exception while fetching config: {e}")
    return None

def checks_changed(old_config, new_config):
    return json.dumps(old_config.get("checks", []), sort_keys=True) != json.dumps(new_config.get("checks", []), sort_keys=True)

def update_scripts(repo_url, script_list):
    for script in script_list:
        script_url = urljoin(repo_url, script)
        try:
            print(f"[INFO] Checking {script} for updates...")
            r = requests.get(script_url, timeout=10)
            if r.status_code == 200:
                remote_code = r.text
                local_code = ""
                if os.path.exists(script):
                    with open(script, "r") as f:
                        local_code = f.read()
                if local_code != remote_code:
                    with open(script, "w") as f:
                        f.write(remote_code)
                    print(f"[INFO] {script} updated.")
                else:
                    print(f"[INFO] {script} is up to date.")
            else:
                print(f"[WARN] Failed to fetch {script_url}: {r.status_code}")
        except Exception as e:
            print(f"[ERROR] Exception while downloading {script}: {e}")

def main():
    print(f"[INFO] update_agent.py started at {datetime.now().isoformat()}")

    config_data = load_config()
    token = config_data.get("token")
    github_repo = config_data.get("github_repo", DEFAULT_REPO)
    lock_file = config_data.get("lock_file", DEFAULT_LOCK_FILE)
    script_list = config_data.get("scripts_to_update", DEFAULT_SCRIPTS)

    if not token:
        print("[ERROR] No token found in config.json.")
        return

    # Lock to prevent multiple runs
    lock = FileLock(lock_file)
    try:
        lock.acquire(timeout=10)
    except Timeout:
        print("[WARN] Another instance is already running. Exiting.")
        return

    remote_config = fetch_config_from_api(token)
    if not remote_config:
        lock.release()
        return

    remote_config["last_updated"] = datetime.now().isoformat()
    remote_config["token"] = token
    remote_config["github_repo"] = github_repo
    remote_config["lock_file"] = lock_file
    remote_config["scripts_to_update"] = script_list

    if checks_changed(config_data, remote_config):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(remote_config, f, indent=2)
            print("[INFO] config.json updated.")
        except Exception as e:
            print(f"[ERROR] Could not write config.json: {e}")
    else:
        print("[INFO] No changes to config.json.")

    update_scripts(github_repo, script_list)

    lock.release()
    print(f"[INFO] update_agent.py finished at {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()
