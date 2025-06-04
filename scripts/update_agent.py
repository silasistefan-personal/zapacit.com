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
