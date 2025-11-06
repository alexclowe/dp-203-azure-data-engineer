#!/usr/bin/env python3
import os, sys, re, requests, yaml
from pathlib import Path
from fnmatch import fnmatch

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
    for m in re.finditer(r'((?:docs|guides|content|articles)/[^\s`]+?\.md)', text, re.I):
        paths.add(m.group(1).strip().strip('.,)'))
    for m in re.finditer(r'https?://github\.com/[^/]+/[^/]+/blob/[^/]+/([^\s#]+?\.md)', text, re.I):
        paths.add(m.group(1))
    for m in re.finditer(r'(?im)^(?:affected page|affected|path|file)\s*[:\-]\s*(.+\.md)\s*$', text):
        paths.add(m.group(1).strip())
    return list(paths)

def match_route(cfg, candidate_paths):
    routes = cfg.get("routes") or []
    for p in candidate_paths:
        p_norm = p.strip().lstrip("/")
        for rule in routes:
            patt = rule.get("pattern")
            if patt and fnmatch(p_norm, patt):
                cds = [u.lstrip("@") for u in (rule.get("content_developers") or [])]
                mgrs = [u.lstrip("@") for u in (rule.get("cd_managers") or [])]
                return cds, mgrs, p_norm
    return None, None, None

def split_assignables(user_or_team_list):
    """Return (assignable_usernames, mentionables_including_teams).
    Teams contain '/', cannot be assignees for issues."""
    assignable = []
    mentions = []
    for s in user_or_team_list or []:
        s = s.lstrip("@")
        mentions.append(s)
        if "/" not in s:
            assignable.append(s)
    return assignable, mentions

def main():
    repo = arg("repo")
    issue_number = int(arg("issue"))
    cfg = yaml.safe_load(Path(arg("config") or ".github/agent.yml").read_text(encoding="utf-8"))

    default_cds = [u.lstrip("@") for u in cfg.get("content_developers", [])]
    default_mgrs = [u.lstrip("@") for u in cfg.get("cd_managers", [])]
    triage_hex = (cfg.get("labels", {}) or {}).get("triage", "B36B00")
    overdue_hex = (cfg.get("labels", {}) or {}).get("overdue", "D93F0B")

    ensure_label(repo, "triage", triage_hex)
    ensure_label(repo, "overdue", overdue_hex)

    issue = get_issue(repo, issue_number)
    title, body = issue["title"], issue.get("body","")
    paths = extract_paths(title, body)

    route_cds, route_mgrs, matched_path = match_route(cfg, paths)
    cds = route_cds or default_cds
    mgrs = route_mgrs or default_mgrs

    # Assign only real usernames; still @mention teams
    assignable_cds, mention_cds = split_assignables(cds)
    _, mention_mgrs = split_assignables(mgrs)

    # triage label + assignment
    add_labels(repo, issue_number, ["triage"])
    if assignable_cds:
        add_assignees(repo, issue_number, assignable_cds)

    mcds = " ".join(f"@{u}" for u in mention_cds) if mention_cds else "(none)"
    mmgrs = " ".join(f"@{u}" for u in mention_mgrs) if mention_mgrs else "(none)"
    path_note = f"\n- Matched path: `{matched_path}`" if matched_path else ""
    body = (
        f"🔔 **New issue intake**\n\n"
        f"- Content Developer(s): {mcds}\n"
        f"- CD Manager(s): {mmgrs}"
        f"{path_note}\n\n"
        f"Labelled with `triage` and assigned to Content Developer(s)."
    )
    comment(repo, issue_number, body)

if __name__ == "__main__":
    main()
