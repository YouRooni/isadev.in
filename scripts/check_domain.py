#!/usr/bin/env python3
"""
Runs on every Pull Request.
Validates the new entry in domains.json.
Checks for duplicates, formatting, and valid NS records.
Does NOT require external API keys, so it works reliably on PRs from forks.
"""

import json
import os
import re
import sys
import subprocess

import requests

ROOT_DOMAIN = "isadev.in"
DOMAINS_FILE = "domains.json"

GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
PR_NUMBER = os.environ.get("PR_NUMBER", "")

SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$")
NS_RE = re.compile(r"^[a-z0-9]([a-z0-9\-\.]{0,253}[a-z0-9])?$", re.IGNORECASE)
RESERVED = {"example", "@", "www", "mail", "api", "dns", "ns1", "ns2", "admin", "root"}


def gh_comment(body: str):
    if not (GH_TOKEN and REPO and PR_NUMBER):
        return
    try:
        requests.post(
            f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/comments",
            headers={"Authorization": f"Bearer {GH_TOKEN}", "Content-Type": "application/json"},
            json={"body": body},
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Failed to post GitHub comment: {e}", file=sys.stderr)


def gh_close():
    if not (GH_TOKEN and REPO and PR_NUMBER):
        return
    try:
        requests.patch(
            f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}",
            headers={"Authorization": f"Bearer {GH_TOKEN}", "Content-Type": "application/json"},
            json={"state": "closed"},
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Failed to close PR: {e}", file=sys.stderr)


def gh_label(label: str):
    if not (GH_TOKEN and REPO and PR_NUMBER):
        return
    try:
        requests.post(
            f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/labels",
            headers={"Authorization": f"Bearer {GH_TOKEN}", "Content-Type": "application/json"},
            json={"labels": [label]},
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Failed to add GitHub label: {e}", file=sys.stderr)


def get_base_domains() -> list:
    """Fetch domains.json from the main branch to know existing domains."""
    for ref in ["origin/main:domains.json", "HEAD~1:domains.json", "main:domains.json"]:
        result = subprocess.run(["git", "show", ref], capture_output=True, text=True)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue
    return []


def get_pr_domains() -> list:
    with open(DOMAINS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    base = get_base_domains()

    try:
        pr = get_pr_domains()
    except json.JSONDecodeError as e:
        msg = (
            f"❌ **`domains.json` is not valid JSON:**\n```\n{e}\n```\n\n"
            "**Common fix:** Add your object inside the existing `[...]` array, separated by a comma. "
            "Do not start a second `[...]` block."
        )
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    if not isinstance(pr, list):
        msg = "❌ `domains.json` must be a JSON array `[...]`."
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    base_subs = {e.get("subdomain", "").lower() for e in base if isinstance(e, dict)}
    pr_subs = [e.get("subdomain", "").lower() for e in pr if isinstance(e, dict)]

    # Check for duplicates within this file
    seen = set()
    for sub in pr_subs:
        if sub in seen:
            msg = f"❌ Duplicate subdomain `{sub}` found in `domains.json`. Subdomains must be unique."
            print(msg, file=sys.stderr)
            gh_comment(msg)
            gh_close()
            sys.exit(1)
        seen.add(sub)

    # Check that existing approved domains weren't deleted or altered
    pr_sub_set = set(pr_subs)
    removed = base_subs - pr_sub_set
    if removed:
        msg = (
            f"❌ Existing approved entries were removed: `{', '.join(removed)}`.\n\n"
            "You can only add your new entry; do not delete or edit other domains."
        )
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    # Identify new additions
    new_entries = [e for e in pr if isinstance(e, dict) and e.get("subdomain", "").lower() not in base_subs]

    if len(new_entries) == 0:
        msg = "❌ No new domain entry found in `domains.json`. Please add your entry to the list."
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    if len(new_entries) > 1:
        msg = f"❌ Please submit only 1 subdomain per PR (found {len(new_entries)} new entries)."
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    entry = new_entries[0]
    subdomain = entry.get("subdomain", "")
    owner = entry.get("owner", "")
    ns_list = entry.get("ns", [])

    if not subdomain or not SUBDOMAIN_RE.match(subdomain):
        msg = (
            f"❌ Invalid subdomain `{subdomain}`.\n\n"
            "Must be lowercase alphanumeric and hyphens only (1-63 chars, no uppercase)."
        )
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    if subdomain.lower() in RESERVED:
        msg = f"❌ The subdomain `{subdomain}` is reserved and cannot be registered."
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    if not owner or not isinstance(owner, str):
        msg = "❌ Missing or invalid `owner` field. Must be your GitHub username."
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    if not isinstance(ns_list, list) or len(ns_list) < 1:
        msg = "❌ `ns` must be a list with at least 1 valid nameserver."
        print(msg, file=sys.stderr)
        gh_comment(msg)
        gh_close()
        sys.exit(1)

    for ns in ns_list:
        if not isinstance(ns, str) or not NS_RE.match(ns.strip()):
            msg = f"❌ Invalid nameserver hostname: `{ns}`."
            print(msg, file=sys.stderr)
            gh_comment(msg)
            gh_close()
            sys.exit(1)

    full_domain = f"{subdomain}.{ROOT_DOMAIN}"
    ns_display = ", ".join(f"`{n.strip()}`" for n in ns_list)

    gh_label("pending review")
    gh_comment(
        f"✅ **`{full_domain}` is available!**\n\n"
        f"| Field | Value |\n"
        f"| :--- | :--- |\n"
        f"| **Domain** | `{full_domain}` |\n"
        f"| **Owner** | [@{owner}](https://github.com/{owner}) |\n"
        f"| **Nameservers** | {ns_display} |\n\n"
        "Your PR is queued for maintainer merge. Once merged, DNS records will be added automatically."
    )
    print(f"Validation successful: {full_domain} is available.")


if __name__ == "__main__":
    main()
