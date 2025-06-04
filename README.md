# Zapacit - Monitoring Agent

A lightweight, open-source monitoring agent that checks the performance and health of external websites from multiple locations and reports metrics to a central server.

This project is designed for use cases such as:
- DNS response time monitoring
- SSL handshake time measurement
- SSL certificate expiry checks
- Full HTTPS GET `/` response profiling
- Multi-location scanning and reporting
- Centralized metrics collection and visualization

## Components

This agent consists of two separate scripts:

### 1. `update_agent.py` (Updater)
- Fetches the latest config from your central API
- Pulls the latest version of `run_agent.py` from GitHub
- Writes the config to a local file (`agent_config.json`)
- Runs periodically (e.g., every hour via cron or systemd)

### 2. `run_agent.py` (Worker)
- Executes tests on configured target URLs:
  - DNS resolution time
  - SSL handshake time
  - Total time for HTTPS GET `/`
  - SSL certificate expiration info
- Keeps the results locally until disk full or results are sent to the central monitoring API
- Sends results to the central monitoring API
- Runs every minute (via cron or as a service)

- Requirements on the agent node:
```
apt install dnsutils openssl python3-requests python3-certifi python3-psutil python3-dnspython python3-tldextract -y
```

## Workflow

1. The update agent fetches the latest configuration and optionally updates `run_agent.py` if a new version is available.
2. The run agent uses the latest configuration to perform website scans.
3. Results are sent to your API for storage, alerting, and graphing.
