#!/usr/bin/env python3
"""Refresh the Contributors block in README.md from the GitHub contributors API.

Self-contained — no third-party action, no view-time third-party image service. It
fetches the authoritative contributor list and writes an avatar grid (GitHub's own
avatar CDN) between the markers in README.md. Run by .github/workflows/contributors.yml
on every push to main; safe to run locally (uses the gh CLI's auth).
"""
import json
import os
import re
import subprocess
import sys

REPO = os.environ.get("GITHUB_REPOSITORY", "4242labs/tron")
README = os.environ.get("README_PATH", "README.md")
START, END = "<!-- contributors:start -->", "<!-- contributors:end -->"
SIZE = 64

def contributors():
    out = subprocess.run(
        ["gh", "api", "--paginate", f"repos/{REPO}/contributors?per_page=100"],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    # Real people only, most contributions first (the API already sorts by count).
    return [c for c in data if c.get("type") != "Bot"]

def cell(c):
    login, av = c["login"], c["avatar_url"]
    sep = "&" if "?" in av else "?"
    return (f'<a href="https://github.com/{login}" title="{login}">'
            f'<img src="{av}{sep}s={SIZE}" width="{SIZE}" height="{SIZE}" alt="{login}" /></a>')

def main():
    block = "".join(cell(c) for c in contributors()) or "_Be the first to contribute._"
    text = open(README, encoding="utf-8").read()
    if START not in text or END not in text:
        sys.exit(f"markers not found in {README}")
    new = f"{START}\n{block}\n{END}"
    text = re.sub(re.escape(START) + r"[\s\S]*?" + re.escape(END), lambda _: new, text)
    open(README, "w", encoding="utf-8").write(text)
    print("contributors block refreshed")

if __name__ == "__main__":
    main()
