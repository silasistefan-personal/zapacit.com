#!/usr/bin/env python3
import json
import socket
import ssl
import time
import requests
import dns.resolver
import dns.name
import dns.message
import dns.query
import fcntl
import os
import sys
from datetime import datetime
from urllib.parse import urlparse

CHECKS_FILE = "/etc/zapacit-agent/checks.json"
API_URL = "https://www.zapacit.com/api/index.php"
LOCK_FILE = '/tmp/run_agent.lock'

try:
    lock_file = open(LOCK_FILE, 'w')
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print("Another instance of agent_run.py is already running.")
    sys.exit(1)

def load_checks():
    with open(CHECKS_FILE, "r") as f:
        data = json.load(f)
    return data["agent_token"], data["checks"]

def get_ns(domain):
    try:
        answers = dns.resolver.resolve(domain, 'NS')
        return str(answers[0])
    except Exception:
        return None

def get_ns_ip(ns_domain):
    try:
        answers = dns.resolver.resolve(ns_domain, 'A')
        return str(answers[0])
    except Exception:
        return None

def time_dns_ns(domain):
    try:
        ns = get_ns(domain)
        if not ns:
            return None
        ns_ip = get_ns_ip(ns)
        if not ns_ip:
            return None
        start = time.time()
        qname = dns.name.from_text(domain)
        query = dns.message.make_query(qname, dns.rdatatype.A)
        dns.query.udp(query, ns_ip, timeout=3)
        return int((time.time() - start) * 1000)
    except Exception:
        return None

def time_dns_local(domain):
    try:
        start = time.time()
        dns.resolver.resolve(domain, 'A')
        return int((time.time() - start) * 1000)
    except Exception:
        return None

def time_tcp_handshake(host, port):
    try:
        start = time.time()
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        return int((time.time() - start) * 1000)
    except Exception:
        return None

def time_ssl_handshake(host, port=443):
    try:
        start = time.time()
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=3) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                end = time.time()
                cert = ssock.getpeercert()
                not_after = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y %Z")
                days_remaining = (not_after - datetime.utcnow()).days
        return int((end - start) * 1000), days_remaining
    except Exception:
        return None, None

def time_http_get(url):
    try:
        start = time.time()
        requests.get(url, timeout=5)
        return int((time.time() - start) * 1000)
    except Exception:
        return None

def run_checks():
    token, checks = load_checks()
    for check in checks:
        url = check["url"]
        parsed = urlparse(url)
        domain = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        print(f"Running checks for: {url}")
        metrics = []

        val = time_dns_ns(domain)
        if val is not None:
            metrics.append({"name": "dns_ns_time", "value": val})

        val = time_dns_local(domain)
        if val is not None:
            metrics.append({"name": "dns_local_time", "value": val})

        val = time_tcp_handshake(domain, port)
        if val is not None:
            metrics.append({"name": "tcp_time", "value": val})

        if parsed.scheme == "https":
            ssl_time, days_remaining = time_ssl_handshake(domain, port)
            if ssl_time is not None:
                metrics.append({"name": "ssl_time", "value": ssl_time})
            if days_remaining is not None:
                metrics.append({"name": "ssl_days_remaining", "value": days_remaining})

        val = time_http_get(url)
        if val is not None:
            metrics.append({"name": "http_time", "value": val})

        payload = {
            "token": token,
            "url": url,
            "metrics": metrics
        }

        # print(payload)

        try:
            response = requests.post(API_URL, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"[{url}] Data posted successfully.")
            else:
                print(f"[{url}] API error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[{url}] Failed to post data: {e}")

if __name__ == "__main__":
    run_checks()
