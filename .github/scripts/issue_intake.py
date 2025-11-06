#!/usr/bin/env python3
import os, sys, json, requests, yaml
from pathlib import Path

def arg(name):
    for i,a in enumerate(sys.argv):
        if a == f"--{name}" and i+1 < len(sys.argv): return sys.argv[i+1]
    return None

GITHUB_API = "https://api.github.com"

def gh(method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json"
    })
    r = requests.request(method, f"{GITHUB_API}{path}", headers=headers, **kwargs)
    if r.status_code >= 300:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text}")
    return r.json() if r.text else {}

def ensure_label(repo, name, color_hex):
    # create if missing; update color if exists
    try:
        gh("GET", f"/repos/{repo}/labels/{name}")
    except Exception:
        gh("POST", f"/repos/{repo}/labels", json={"name": name, "color": color_hex.lstrip("#")})

def add_labels(repo, issue_number, labels):
    if labels:
        gh("POST", f"/repos/{repo}/issues/{issue_number}/labels", json={"labels": labels})

def add_assignees(repo, issue_number, assignees):
    if assignees:
        gh("POST", f"/repos/{repo}/issues/{issue_number}/assignees", json={"assignees": assignees})

def comment(repo, issue_number, body):
    gh("POST", f"/repos/{repo}/issues/{issue_number}/comments", json={"body": body})

def main():
    repo = arg("repo")
    issue_number = int(arg("issue"))
    cfg_path = Path(arg("config") or ".github/agent.yml")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    cds = [a.lstrip("@") for a in cfg.get("content_developers", [])]
    mgrs = [a.lstrip("@") for a in cfg.get("cd_managers", [])]
    triage_hex = (cfg.get("labels", {}) or {}).get("triage", "B36B00")

    # ensure triage label exists, then label the issue
    ensure_label(repo, "triage", triage_hex)
    add_labels(repo, issue_number, ["triage"])

    # assign all content developers
    add_assignees(repo, issue_number, cds)

    # notify: mention CDs + managers (mentions trigger GitHub notifications)
    mention_cds = " ".join(f"@{u}" for u in cds) if cds else "(none)"
    mention_mgrs = " ".join(f"@{u}" for u in mgrs) if mgrs else "(none)"
    body = (
        f"🔔 **New issue intake**\n\n"
        f"- Content Developer(s): {mention_cds}\n"
        f"- CD Manager(s): {mention_mgrs}\n\n"
        f"Labelled with `triage` and assigned to Content Developer(s)."
    )
    comment(repo, issue_number, body)

if __name__ == "__main__":
    main()
