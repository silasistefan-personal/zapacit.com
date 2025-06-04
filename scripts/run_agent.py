import os
import json
import time
import socket
import ssl
import http.client
import requests
import fcntl
import dns.resolver
import dns.name
import dns.query
import dns.message
import subprocess
from datetime import datetime
from urllib.parse import urlparse

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
FAILED_METRICS_FILE = "failed_metrics.json"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("[ERROR] config.json not found.")
        return None
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def resolve_dns_ns(hostname: str) -> float:
    # Extract the base domain (e.g., google.com)
    domain_parts = hostname.split('.')
    if len(domain_parts) < 2:
        raise ValueError("Invalid hostname")

    base_domain = '.'.join(domain_parts[-2:])

    # Step 1: Get NS records for the base domain
    try:
        ns_response = dns.resolver.resolve(base_domain, 'NS')
        ns_servers = [str(rdata.target).rstrip('.') for rdata in ns_response]
    except Exception as e:
        raise RuntimeError(f"Failed to resolve NS for domain {base_domain}: {e}")

    if not ns_servers:
        raise RuntimeError(f"No NS records found for domain {base_domain}")

    # Step 2: Resolve the IP of one of the authoritative nameservers
    try:
        ns_ip_response = dns.resolver.resolve(ns_servers[0], 'A')
        ns_ip = ns_ip_response[0].to_text()
    except Exception as e:
        raise RuntimeError(f"Failed to resolve IP for NS {ns_servers[0]}: {e}")

    # Step 3: Create and send a DNS query directly to the authoritative NS
    try:
        query = dns.message.make_query(hostname, 'A')
        start = time.perf_counter()
        response = dns.query.udp(query, ns_ip, timeout=5)
        end = time.perf_counter()
    except Exception as e:
        raise RuntimeError(f"DNS query to authoritative NS failed: {e}")

    # Return the time taken in milliseconds
    return (end - start) * 1000


def resolve_dns_local(hostname):
    try:
        start = time.time()
        socket.gethostbyname(hostname)
        end = time.time()
        return int((end - start) * 1000)
    except Exception as e:
        print(f"[WARN] DNS local resolution failed for {hostname}: {e}")
        return None


def tcp_handshake_time(host, port):
    try:
        start = time.time()
        s = socket.create_connection((host, port), timeout=5)
        end = time.time()
        s.close()
        return int((end - start) * 1000)
    except Exception as e:
        print(f"[WARN] TCP connection failed: {e}")
        return None


def ssl_handshake_time(host, port):
    try:
        context = ssl.create_default_context()
        start = time.time()
        with socket.create_connection((host, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                end = time.time()
        return int((end - start) * 1000)
    except Exception as e:
        print(f"[WARN] SSL handshake failed: {e}")
        return None


def ssl_days_remaining(host, port):
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                expire_date = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y %Z")
                remaining = (expire_date - datetime.utcnow()).days
                return remaining
    except Exception as e:
        print(f"[WARN] SSL cert check failed: {e}")
        return None


def http_get_time(url):
    try:
        parsed = urlparse(url)
        conn_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        start = time.time()
        conn = conn_class(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), timeout=5)
        conn.request("GET", "/")
        response = conn.getresponse()
        end = time.time()
        conn.close()
        return int((end - start) * 1000)
    except Exception as e:
        print(f"[WARN] HTTP GET failed: {e}")
        return None


def run_check(url):
    if not isinstance(url, str):
        raise ValueError(f"Expected URL string, got {type(url)}")

    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    metrics = []

    ns_time = resolve_dns_ns(host)
    if ns_time is not None:
        metrics.append({"name": "dns_ns_time", "value": ns_time})

    local_time = resolve_dns_local(host)
    if local_time is not None:
        metrics.append({"name": "dns_local_time", "value": local_time})

    tcp_time = tcp_handshake_time(host, port)
    if tcp_time is not None:
        metrics.append({"name": "tcp_time", "value": tcp_time})

    ssl_time = ssl_handshake_time(host, port)
    if ssl_time is not None:
        metrics.append({"name": "ssl_time", "value": ssl_time})

    ssl_days = ssl_days_remaining(host, port)
    if ssl_days is not None:
        metrics.append({"name": "ssl_days_remaining", "value": ssl_days})

    http_time = http_get_time(url)
    if http_time is not None:
        metrics.append({"name": "http_time", "value": http_time})

    return metrics


def post_metrics(api_url, token, url, metrics):
    payload = {"token": token, "url": url, "metrics": metrics}
    for attempt in range(3):
        try:
            response = requests.post(api_url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                print(f"[WARN] API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[WARN] Post attempt {attempt + 1} failed: {e}")
        time.sleep(1)
    return False


def retry_failed_posts(api_url, token):
    if not os.path.exists(FAILED_METRICS_FILE):
        return

    try:
        with open(FAILED_METRICS_FILE, "r") as f:
            failed_data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read {FAILED_METRICS_FILE}: {e}")
        return

    new_failed = []
    for item in failed_data:
        url = item["url"]
        metrics = item["metrics"]
        if not post_metrics(api_url, token, url, metrics):
            new_failed.append(item)

    if new_failed:
        with open(FAILED_METRICS_FILE, "w") as f:
            json.dump(new_failed, f)
    else:
        os.remove(FAILED_METRICS_FILE)


def save_failed(url, metrics):
    try:
        if os.path.exists(FAILED_METRICS_FILE):
            with open(FAILED_METRICS_FILE, "r") as f:
                existing = json.load(f)
        else:
            existing = []
        existing.append({"url": url, "metrics": metrics})
        with open(FAILED_METRICS_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to write failed metrics: {e}")


def main():
    config = load_config()
    if not config:
        return

    token = config.get("token")
    api_url = config.get("api_url")
    checks = config.get("checks", [])
    lock_path = os.path.join(os.path.dirname(__file__), "run_agent.lock")
    
    if not token or not api_url:
        print("[ERROR] Missing token or api_url in config.")
        return

    try:
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            retry_failed_posts(api_url, token)

            for check in checks:
                url = check.get("url")
                if not url or not check.get("enabled", True):
                    continue
                print(f"[INFO] Checking {url}")
                try:
                    metrics = run_check(url)
                    if metrics:
                        if not post_metrics(api_url, token, url, metrics):
                            save_failed(url, metrics)
                    else:
                        print(f"[WARN] No metrics generated for {url}")
                except Exception as e:
                    print(f"[ERROR] Failed check for {url}: {e}")
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    except BlockingIOError:
        print("[INFO] Another instance is running. Exiting.")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")


if __name__ == "__main__":
    main()
