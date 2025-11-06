#!/usr/bin/env python3
import os, sys, requests, yaml
from pathlib import Path

API = "https://api.github.com"

def arg(name):
    for i,a in enumerate(sys.argv):
        if a == f"--{name}" and i+1 < len(sys.argv): return sys.argv[i+1]
    return None

def gh(method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json"
    })
    r = requests.request(method, f"{API}{path}", headers=headers, **kwargs)
    if r.status_code >= 300:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text}")
    return r.json() if r.text else {}

def get_issue(repo, number):
    return gh("GET", f"/repos/{repo}/issues/{number}")

def has_label(issue, name):
    return any(l["name"].lower() == name.lower() for l in issue.get("labels", []))

def remove_label(repo, number, name):
    # DELETE /repos/{owner}/{repo}/issues/{issue_number}/labels/{name}
    requests.delete(
        f"{API}/repos/{repo}/issues/{number}/labels/{requests.utils.quote(name, safe='')}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json"}
    )

def main():
    repo = arg("repo")
    issue_number = int(arg("issue"))
    commenter = (arg("commenter") or "").strip().lower()
    cfg = yaml.safe_load(Path(arg("config") or ".github/agent.yml").read_text(encoding="utf-8"))

    cds = [u.lstrip("@").lower() for u in cfg.get("content_developers", [])]

    # If the commenter is a Content Developer, remove 'overdue' label if present
    if commenter and commenter in cds:
        issue = get_issue(repo, issue_number)
        if has_label(issue, "overdue"):
            remove_label(repo, issue_number, "overdue")

if __name__ == "__main__":
    main()
