"""Guardrails for the match-data rule (AGENTS.md). Never reads the data, only paths and git metadata.

python guard.py setup    check this machine: MTAH_DATA, exclusion files, pre-commit hook
python guard.py staged   pre-commit hook: block data files and the Drive link in staged changes
python guard.py repo     CI: block data files anywhere in the tracked tree
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
BLOCKED = re.compile(r"BAR-ATH|\.npz$|\.mp4$|(^|/)data/|(^|/)output/", re.I)
MAX_BYTES = 1_000_000
CLOUD = re.compile(r"onedrive|google ?drive|dropbox|icloud", re.I)
EXCLUSION_FILES = [".claude/settings.json", ".cursorignore", ".aiexclude"]


def git(*args, check=True):
    # git writes UTF-8; text=True decodes with the console's code page (cp1252 on Windows), fails on bytes
    # like the 0x8d of "Í" and returns None
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, encoding="utf-8", errors="replace",
                          check=check).stdout


def bad_files(paths):
    out = []
    for p in paths:
        if BLOCKED.search(p):
            out.append(f"{p}: match data or a derived output")
        elif os.path.isfile(os.path.join(REPO, p)) and os.path.getsize(os.path.join(REPO, p)) > MAX_BYTES:
            out.append(f"{p}: larger than 1 MB")
    return out


def setup():
    errors = []
    data = os.environ.get("MTAH_DATA")
    if not data:
        errors.append("MTAH_DATA is not set (Windows: setx MTAH_DATA C:\\mtah-data, then reopen the terminal)")
    else:
        data = os.path.realpath(data)
        if not os.path.isdir(data):
            errors.append(f"MTAH_DATA={data} does not exist")
        if CLOUD.search(data):
            errors.append(f"MTAH_DATA={data} is inside a cloud-synced folder")
        d = data
        while os.path.dirname(d) != d:
            if os.path.exists(os.path.join(d, ".git")):
                errors.append(f"MTAH_DATA={data} is inside the git repo {d}")
                break
            d = os.path.dirname(d)
    errors += [f"{f} is missing" for f in EXCLUSION_FILES if not os.path.exists(os.path.join(REPO, f))]
    if git("config", "core.hooksPath", check=False).strip() != ".githooks":  # exit 1 when unset
        errors.append("pre-commit hook is off: run  git config core.hooksPath .githooks")
    return errors


def staged():
    errors = bad_files(git("diff", "--cached", "--name-only", "--diff-filter=AM").split())
    added = [l for l in git("diff", "--cached", "-U0").splitlines() if l.startswith("+") and not l.startswith("+++")]
    if any(re.search(r"drive\.google\.com", l) for l in added):  # regex so this line doesn't match itself
        errors.append("a staged change adds a Google Drive link")
    return errors


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    checks = {"setup": setup, "staged": staged, "repo": lambda: bad_files(git("ls-files").splitlines())}
    if mode not in checks:
        sys.exit(__doc__)
    errors = checks[mode]()
    for e in errors:
        print("FAIL", e)
    print("OK" if not errors else f"{len(errors)} problem(s), see AGENTS.md")
    sys.exit(1 if errors else 0)
