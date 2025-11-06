#!/usr/bin/env python3
import os, sys, re, requests, yaml
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

def ensure_label(repo, name, color_hex):
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

def get_issue(repo, number):
    return gh("GET", f"/repos/{repo}/issues/{number}")

def extract_paths(title, body):
    text = f"{title}\n\n{body or ''}"
    paths = set()
    # common patterns: docs/foo/bar.md, guides/..., or URLs to repo files
    for m in re.finditer(r'((?:docs|guides|content|articles)/[^\s`]+?\.md)', text, re.I):
        paths.add(m.group(1).strip().strip('.,)'))
    for m in re.finditer(r'https?://github\.com/[^/]+/[^/]+/blob/[^/]+/([^\s#]+?\.md)', text, re.I):
        paths.add(m.group(1))
    # issue form field "Affected page" sometimes shows alone on a line
    for m in re.finditer(r'(?im)^(?:affected page|affected|path|file)\s*[:\-]\s*(.+\.md)\s*$', text):
        paths.add(m.group(1).strip())
    return list(paths)

def pick_assignees_by_routes(cfg, candidate_paths):
    routes = cfg.get("routes") or []
    for p in candidate_paths:
        p_norm = p.strip().lstrip("/")
        for rule in routes:
            patt = rule.get("pattern")
            cds = [u.lstrip("@") for u in (rule.get("content_developers") or [])]
            if patt and cds:
                # glob match
                from fnmatch import fnmatch
                if fnmatch(p_norm, patt):
                    return cds, p_norm
    return None, None

def main():
    repo = arg("repo")
    issue_number = int(arg("issue"))
    cfg = yaml.safe_load(Path(arg("config") or ".github/agent.yml").read_text(encoding="utf-8"))

    default_cds = [u.lstrip("@") for u in cfg.get("content_developers", [])]
    mgrs = [u.lstrip("@") for u in cfg.get("cd_managers", [])]
    triage_hex = (cfg.get("labels", {}) or {}).get("triage", "B36B00")
    overdue_hex = (cfg.get("labels", {}) or {}).get("overdue", "D93F0B")

    # Ensure labels exist
    ensure_label(repo, "triage", triage_hex)
    ensure_label(repo, "overdue", overdue_hex)

    issue = get_issue(repo, issue_number)
    title, body = issue["title"], issue.get("body","")
    paths = extract_paths(title, body)
    route_cds, matched_path = pick_assignees_by_routes(cfg, paths)

    assignees = route_cds or default_cds

    # Label, assign, notify
    add_labels(repo, issue_number, ["triage"])
    if assignees:
        add_assignees(repo, issue_number, assignees)

    mention_cds = " ".join(f"@{u}" for u in assignees) if assignees else "(none)"
    mention_mgrs = " ".join(f"@{u}" for u in mgrs) if mgrs else "(none)"
    path_note = f"\n- Matched path: `{matched_path}`" if matched_path else ""
    body = (
        f"🔔 **New issue intake**\n\n"
        f"- Content Developer(s): {mention_cds}\n"
        f"- CD Manager(s): {mention_mgrs}"
        f"{path_note}\n\n"
        f"Labelled with `triage` and assigned to Content Developer(s)."
    )
    comment(repo, issue_number, body)

if __name__ == "__main__":
    main()
