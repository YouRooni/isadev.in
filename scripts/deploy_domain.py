#!/usr/bin/env python3
"""
Runs on push to main. Reads domains.json and registers any subdomain
that isn't already in Intent-DNS. Source of truth is the API, not git.
"""

import json
import os
import sys

import requests

BASE_URL = "https://panel.dns.int.yt/api/v1"
ROOT_DOMAIN = "isadev.in"
DOMAINS_FILE = "domains.json"

API_KEY = os.environ["INTDNS_API_KEY"].strip()
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

SKIP = {"example"}  # placeholder entries to never deploy


def get_registered() -> set[str]:
    resp = requests.get(f"{BASE_URL}/domains", headers=HEADERS)
    resp.raise_for_status()
    return {d["domain"].lower() for d in resp.json().get("domains", [])}


def create_zone(full_domain: str) -> int:
    resp = requests.post(
        f"{BASE_URL}/domains",
        headers=HEADERS,
        json={"domain": full_domain},
    )
    if resp.status_code == 409:
        all_resp = requests.get(f"{BASE_URL}/domains", headers=HEADERS)
        all_resp.raise_for_status()
        for d in all_resp.json().get("domains", []):
            if d["domain"].lower() == full_domain.lower():
                return d["id"]
        raise RuntimeError(f"409 but not found: {full_domain}")
    resp.raise_for_status()
    return resp.json()["domain"]["id"]


def add_ns(domain_id: int, ns: str):
    resp = requests.post(
        f"{BASE_URL}/domains/{domain_id}/records",
        headers=HEADERS,
        json={"name": "@", "type": "NS", "content": ns, "ttl": 3600},
    )
    resp.raise_for_status()
    print(f"  NS → {ns}")


def main():
    with open(DOMAINS_FILE) as f:
        entries = json.load(f)

    registered = get_registered()
    print(f"Already registered: {len(registered)} zones")

    errors = []
    deployed = 0

    for entry in entries:
        subdomain = entry["subdomain"].lower()
        if subdomain in SKIP:
            continue

        full_domain = f"{subdomain}.{ROOT_DOMAIN}"

        if full_domain in registered:
            print(f"Skip (exists): {full_domain}")
            continue

        print(f"\n--- Deploying {full_domain} ---")
        try:
            domain_id = create_zone(full_domain)
            for ns in entry["ns"]:
                add_ns(domain_id, ns)
            print(f"Done: {full_domain}")
            deployed += 1
        except Exception as e:
            errors.append(f"{full_domain}: {e}")
            print(f"ERROR: {e}", file=sys.stderr)

    print(f"\nDeployed {deployed} new zone(s).")

    if errors:
        for e in errors:
            print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
