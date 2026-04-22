"""Vault schema linter — checks project files against the contract.

Run: venv/bin/python -m pm.vault_lint [--verbose] [--project NAME]

Schema contract lives in the auto-memory directory:
  ~/.claude/projects/<cwd-slug>/memory/reference_vault_schema.md
"""
import argparse
import os
import re
from pathlib import Path

VAULT = Path(os.environ.get("VAULT_PATH", Path.home() / "Documents" / "Obsidian Vault")).expanduser()
PROJECTS = VAULT / "Projects"

REQUIRED_FRONTMATTER = ["status"]
RECOMMENDED_FRONTMATTER = ["area", "type", "owner", "tags"]

REQUIRED_SECTIONS = ["## Open Tasks"]
AUTO_MANAGED_SECTIONS = [r"## Roadmap Status \(as of [\d-]+\)"]

VALID_STATUSES = {
    "Measuring", "Dev in progress", "DTD", "PTD", "Ready for dev",
    "Design in progress", "Product review", "Discovery", "Paused",
    "Blocked", "Done",
}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def lint_project(path: Path) -> list[str]:
    issues = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"cannot read: {e}"]

    fm, body = parse_frontmatter(text)

    if not fm:
        issues.append("missing YAML frontmatter")
    else:
        for req in REQUIRED_FRONTMATTER:
            if req not in fm:
                issues.append(f"missing required frontmatter: {req}")
        if "status" in fm and fm["status"] not in VALID_STATUSES:
            issues.append(f"invalid status: '{fm['status']}'")
        for rec in RECOMMENDED_FRONTMATTER:
            if rec not in fm:
                issues.append(f"recommended frontmatter missing: {rec}")

    for req in REQUIRED_SECTIONS:
        if req not in body:
            issues.append(f"missing required section: {req}")

    if "last_roadmap_sync" in fm:
        has_roadmap_status = any(re.search(pat, body) for pat in AUTO_MANAGED_SECTIONS)
        if not has_roadmap_status:
            issues.append("has last_roadmap_sync YAML but missing '## Roadmap Status' section")

    if re.search(r"^## Previous Context\s*$", body, re.MULTILINE):
        issues.append("'## Previous Context' missing date/event context")

    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--project", help="lint only this project folder")
    args = parser.parse_args()

    if not PROJECTS.exists():
        print(f"Vault not found at {VAULT}")
        return 1

    projects = sorted(p for p in PROJECTS.glob("*/") if p.is_dir())
    if args.project:
        projects = [p for p in projects if p.name == args.project]

    total = len(projects)
    bad = 0
    for p in projects:
        md_file = p / f"{p.name}.md"
        if not md_file.exists():
            bad += 1
            print(f"MISSING_FILE  {p.name}")
            continue
        issues = lint_project(md_file)
        if issues:
            bad += 1
            print(f"FAIL  {p.name}")
            for i in issues:
                print(f"      - {i}")
        elif args.verbose:
            print(f"OK    {p.name}")

    print(f"\nLint complete: {bad} of {total} projects have issues")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
