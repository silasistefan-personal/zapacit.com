import os
import json
import time
import socket
import psutil
import requests
from datetime import datetime

CONFIG_FILE = "config.json"
FAILED_POSTS_FILE = "local_agent_failed.json"
MAX_RETRIES = 3


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("[ERROR] config.json not found.")
        return None
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def gather_metrics():
    metrics = []

    # CPU
    cpu_times = psutil.cpu_times_percent(interval=1)
    metrics.append({"name": "cpu_user", "value": cpu_times.user})
    metrics.append({"name": "cpu_system", "value": cpu_times.system})
    metrics.append({"name": "cpu_idle", "value": cpu_times.idle})
    metrics.append({"name": "cpu_iowait", "value": getattr(cpu_times, "iowait", 0.0)})

    # Memory
    mem = psutil.virtual_memory()
    metrics.append({"name": "mem_total", "value": mem.total})
    metrics.append({"name": "mem_used", "value": mem.used})
    metrics.append({"name": "mem_available", "value": mem.available})

    # Swap
    swap = psutil.swap_memory()
    metrics.append({"name": "swap_total", "value": swap.total})
    metrics.append({"name": "swap_used", "value": swap.used})
    metrics.append({"name": "swap_free", "value": swap.free})

    # Disk usage
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            name = f"disk_usage_percent_{part.mountpoint.replace('/', '_')}".rstrip('_')
            metrics.append({"name": name, "value": usage.percent})
        except Exception:
            continue

    # Network
    net = psutil.net_io_counters()
    metrics.append({"name": "net_bytes_sent", "value": net.bytes_sent})
    metrics.append({"name": "net_bytes_recv", "value": net.bytes_recv})

    # Processes/Threads
    metrics.append({"name": "num_processes", "value": len(psutil.pids())})
    metrics.append({"name": "num_threads", "value": sum(p.num_threads() for p in psutil.process_iter())})

    # Uptime
    uptime_seconds = time.time() - psutil.boot_time()
    metrics.append({"name": "uptime_seconds", "value": int(uptime_seconds)})

    # Load averages
    try:
        load1, load5, load15 = os.getloadavg()
        metrics.append({"name": "load_1min", "value": load1})
        metrics.append({"name": "load_5min", "value": load5})
        metrics.append({"name": "load_15min", "value": load15})
    except Exception:
        pass

    return metrics


def post_payload(api_url, payload):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(api_url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"[INFO] {datetime.now().isoformat()} - Posted metrics OK.")
                return True
            else:
                print(f"[WARN] Attempt {attempt}: Failed with {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[EXCEPTION] Attempt {attempt}: {e}")
        time.sleep(2)
    return False


def save_failed_payload(payload):
    data = []
    if os.path.exists(FAILED_POSTS_FILE):
        try:
            with open(FAILED_POSTS_FILE, "r") as f:
                data = json.load(f)
        except Exception:
            data = []
    data.append(payload)
    with open(FAILED_POSTS_FILE, "w") as f:
        json.dump(data, f)
    print(f"[INFO] Saved failed payload to {FAILED_POSTS_FILE}")


def try_resend_failed(api_url):
    if not os.path.exists(FAILED_POSTS_FILE):
        return
    try:
        with open(FAILED_POSTS_FILE, "r") as f:
            cached = json.load(f)
    except Exception as e:
        print(f"[ERROR] Could not read {FAILED_POSTS_FILE}: {e}")
        return

    remaining = []
    for payload in cached:
        if not post_payload(api_url, payload):
            remaining.append(payload)

    if remaining:
        with open(FAILED_POSTS_FILE, "w") as f:
            json.dump(remaining, f)
        print(f"[INFO] {len(remaining)} failed payload(s) remain.")
    else:
        os.remove(FAILED_POSTS_FILE)
        print(f"[INFO] All cached payloads sent. Cache cleared.")


def main():
    config = load_config()
    if not config:
        return

    token = config.get("token")
    api_url = config.get("api_url")

    if not token or not api_url:
        print("[ERROR] Missing 'token' or 'api_url' in config.json.")
        return

    hostname = socket.gethostname()
    url_id = f"agent:{hostname}"
    metrics = gather_metrics()

    payload = {
        "token": token,
        "url": url_id,
        "metrics": metrics
    }

    try_resend_failed(api_url)

    if not post_payload(api_url, payload):
        save_failed_payload(payload)


if __name__ == "__main__":
    main()
