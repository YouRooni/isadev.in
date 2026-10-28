#!/usr/bin/env python3
"""
Runs on push to main (when a PR is merged).
Reads domains.json and adds NS delegation records for each subdomain
directly into the isadev.in parent zone on Intent-DNS.
"""

import json
import os
import sys

import requests

BASE_URL = "https://panel.dns.int.yt/api/v1"
ROOT_DOMAIN = "isadev.in"
DOMAINS_FILE = "domains.json"

API_KEY = os.environ.get("INTDNS_API_KEY", "").strip()
if not API_KEY:
    print("FATAL: INTDNS_API_KEY secret is not set in environment.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

RESERVED_SUBDOMAINS = {"example", "@"}


def get_parent_zone_id() -> int:
    """Find the zone ID for isadev.in in Intent-DNS account."""
    resp = requests.get(f"{BASE_URL}/domains", headers=HEADERS)
    if resp.status_code != 200:
        print(f"FATAL: GET /domains returned HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()

    domains = resp.json().get("domains", [])
    for d in domains:
        if d.get("domain", "").lower() == ROOT_DOMAIN:
            return d["id"]

    domain_names = [d.get("domain") for d in domains]
    raise RuntimeError(
        f"Zone '{ROOT_DOMAIN}' was not found in your Intent-DNS account. "
        f"Available domains in account: {domain_names}"
    )


def get_existing_records(zone_id: int) -> list:
    """Fetch all current DNS records in the parent zone."""
    resp = requests.get(f"{BASE_URL}/domains/{zone_id}/records", headers=HEADERS)
    if resp.status_code != 200:
        print(f"FATAL: GET /domains/{zone_id}/records returned HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()

    data = resp.json()
    if isinstance(data, dict):
        return data.get("records", [])
    elif isinstance(data, list):
        return data
    return []


def is_record_present(records: list, subdomain: str, ns_target: str) -> bool:
    """Check if an NS record for this subdomain and target already exists."""
    sub = subdomain.lower().strip()
    full = f"{sub}.{ROOT_DOMAIN}".lower()
    target = ns_target.lower().strip().rstrip(".")

    for r in records:
        r_type = r.get("type", "").upper()
        if r_type != "NS":
            continue

        r_name = str(r.get("name", "")).lower().strip().rstrip(".")
        r_content = str(r.get("content", "")).lower().strip().rstrip(".")

        if (r_name == sub or r_name == full) and r_content == target:
            return True

    return False


def add_ns_record(zone_id: int, subdomain: str, ns_target: str):
    """Add a single NS delegation record to the parent zone."""
    target = ns_target.strip().rstrip(".")
    payload = {
        "name": subdomain.lower().strip(),
        "type": "NS",
        "content": target,
        "ttl": 3600,
    }
    resp = requests.post(f"{BASE_URL}/domains/{zone_id}/records", headers=HEADERS, json=payload)
    if resp.status_code in (200, 201):
        print(f"  ✅ NS delegation added: {subdomain}.{ROOT_DOMAIN} -> {target}")
    else:
        print(
            f"  ❌ Failed to add NS for {subdomain} -> {target}: "
            f"HTTP {resp.status_code} - {resp.text}",
            file=sys.stderr,
        )
        resp.raise_for_status()


def main():
    if not os.path.exists(DOMAINS_FILE):
        print(f"FATAL: {DOMAINS_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    with open(DOMAINS_FILE, "r", encoding="utf-8") as f:
        try:
            entries = json.load(f)
        except json.JSONDecodeError as e:
            print(f"FATAL: {DOMAINS_FILE} is invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    zone_id = get_parent_zone_id()
    print(f"Connected to Intent-DNS. Root zone: {ROOT_DOMAIN} (id={zone_id})")

    existing_records = get_existing_records(zone_id)
    print(f"Found {len(existing_records)} existing DNS records in {ROOT_DOMAIN}.")

    errors = []
    deployed_count = 0

    for entry in entries:
        subdomain = entry.get("subdomain", "").strip().lower()
        if not subdomain or subdomain in RESERVED_SUBDOMAINS:
            continue

        ns_list = entry.get("ns", [])
        if not isinstance(ns_list, list):
            continue

        for ns in ns_list:
            ns_clean = str(ns).strip()
            if not ns_clean:
                continue

            if is_record_present(existing_records, subdomain, ns_clean):
                print(f"  ⚡ Already exists: {subdomain}.{ROOT_DOMAIN} -> {ns_clean}")
                continue

            print(f"  Adding {subdomain}.{ROOT_DOMAIN} -> {ns_clean}...")
            try:
                add_ns_record(zone_id, subdomain, ns_clean)
                deployed_count += 1
            except Exception as e:
                errors.append(f"{subdomain} -> {ns_clean}: {e}")

    print(f"\nCompleted: {deployed_count} new NS record(s) created.")

    if errors:
        print("\nErrors encountered during deployment:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
