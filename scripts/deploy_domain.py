#!/usr/bin/env python3
"""
Runs when a PR is merged. Reads the new entry from domains.json,
creates the DNS zone, and adds NS records via Intent-DNS API.
"""

import json
import os
import sys
import subprocess

import requests

BASE_URL = "https://panel.dns.int.yt/api/v1"
ROOT_DOMAIN = "isadev.in"
DOMAINS_FILE = "domains.json"

API_KEY = os.environ["INTDNS_API_KEY"].strip()
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def get_base_domains() -> list:
    """Walk back commits until we find a valid domains.json."""
    for ref in ["HEAD~1", "HEAD~2", "HEAD~3", "HEAD~4", "HEAD~5"]:
        result = subprocess.run(
            ["git", "show", f"{ref}:domains.json"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            continue
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
    return []


def get_current_domains() -> list:
    with open(DOMAINS_FILE) as f:
        return json.load(f)


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
                print(f"Zone already exists: {full_domain} → id={d['id']}")
                return d["id"]
        raise RuntimeError(f"409 but zone not found in list: {full_domain}")
    resp.raise_for_status()
    domain_id = resp.json()["domain"]["id"]
    print(f"Zone created: {full_domain} → id={domain_id}")
    return domain_id


def add_ns_record(domain_id: int, ns: str):
    resp = requests.post(
        f"{BASE_URL}/domains/{domain_id}/records",
        headers=HEADERS,
        json={"name": "@", "type": "NS", "content": ns, "ttl": 3600},
    )
    resp.raise_for_status()
    print(f"  NS → {ns}")


def test_auth():
    """Quick auth check before doing anything."""
    resp = requests.get(f"{BASE_URL}/user", headers=HEADERS)
    if resp.status_code == 401:
        print(f"AUTH FAILED — key prefix: {API_KEY[:12]}... (len={len(API_KEY)})", file=sys.stderr)
        print(f"Response: {resp.text}", file=sys.stderr)
        sys.exit(1)
    resp.raise_for_status()
    print(f"Auth OK — logged in as: {resp.json().get('account', {}).get('username', '?')}")


def main():
    test_auth()
    base = get_base_domains()
    current = get_current_domains()

    base_subs = {e["subdomain"].lower() for e in base}
    new_entries = [e for e in current if e["subdomain"].lower() not in base_subs]

    if not new_entries:
        print("No new entries found — nothing to deploy.")
        return

    errors = []
    for entry in new_entries:
        subdomain = entry["subdomain"]
        full_domain = f"{subdomain}.{ROOT_DOMAIN}"
        ns_list = entry["ns"]

        print(f"\n--- Deploying {full_domain} ---")
        try:
            domain_id = create_zone(full_domain)
            for ns in ns_list:
                add_ns_record(domain_id, ns)
            print(f"Done: {full_domain}")
        except Exception as e:
            errors.append(f"{full_domain}: {e}")
            print(f"ERROR: {full_domain}: {e}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
