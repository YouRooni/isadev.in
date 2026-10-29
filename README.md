# isadev.in — Free Subdomains

Get a free `*.isadev.in` subdomain. Point it to your own nameservers.

**Nameservers:** `dns1.int.yt` · `dns2.int.yt` · `dns3.int.yt` · `dns4.int.yt`

---

## How to register

1. **Star** this repo.
2. **Fork** this repo.
3. Add your entry to `domains.json`.
4. Open a **PR** — a bot checks for conflicts instantly.
5. Once merged, your NS records go live within minutes.

---

## Format

Add one entry to `domains.json`:

```json
{
  "subdomain": "yourname",
  "owner": "yourgithubusername",
  "ns": [
    "ns1.yourdomain.com",
    "ns2.yourdomain.com"
  ]
}
```

**Rules:**
- One subdomain per PR
- Subdomain must be lowercase, alphanumeric + hyphens only
- Must point to your own nameservers
- Do not edit or remove existing entries
- No squatting

---

## After merge

Your subdomain `yourname.isadev.in` will be delegated to your nameservers.
Manage all DNS records from your own DNS provider.
