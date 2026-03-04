#!/usr/bin/env python3
"""
skill_install.py - Python port of `npx skill install`

Install and manage AI agent skills (SKILL.md-based).
No external dependencies — stdlib only.

Usage:
    python skill_install.py install owner/repo
    python skill_install.py install ./local-skills/
    python skill_install.py list
    python skill_install.py read <name>
    python skill_install.py remove <name>
    python skill_install.py sync
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ── Frontmatter parser ────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown string.

    Returns (meta_dict, body_text).
    Supports simple key: value pairs only (no nested YAML needed).
    """
    match = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*\n", text, re.DOTALL)
    if not match:
        return {}, text

    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    return meta, text[match.end():]


# ── Skill discovery ───────────────────────────────────────────────────────────

def find_skills(root: Path) -> list[Path]:
    """Recursively find all SKILL.md files under *root*."""
    return sorted(root.rglob("SKILL.md"))


def load_skill_meta(skill_dir: Path) -> dict:
    """Load metadata dict from SKILL.md inside *skill_dir*."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {}
    meta, body = parse_frontmatter(skill_md.read_text())
    meta["_body"] = body
    meta.setdefault("name", skill_dir.name)
    return meta


# ── Source resolution ─────────────────────────────────────────────────────────

def resolve_source(source: str, tmp_dir: Path) -> Path:
    """Resolve *source* to a local directory that contains skills.

    Accepted formats
    ----------------
    - ``./rel/path`` or ``/abs/path``  — local filesystem
    - ``https://...`` or ``git@...``   — git URL (cloned automatically)
    - ``owner/repo``                   — shorthand for GitHub HTTPS URL
    """
    # Local path (explicit prefix or existing directory)
    if source.startswith((".", "/", "~")) or (
        "/" in source and os.path.exists(source)
    ):
        p = Path(source).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Local path not found: {source!r}")
        return p

    # Full git URL
    if source.startswith(("https://", "git@", "http://")):
        git_url = source
    # GitHub shorthand: owner/repo (exactly one slash, no spaces)
    elif re.fullmatch(r"[\w.\-]+/[\w.\-]+", source):
        git_url = f"https://github.com/{source}.git"
    else:
        raise ValueError(
            f"Unrecognised source {source!r}. "
            "Use a local path, owner/repo, or a git URL."
        )

    clone_dir = tmp_dir / "repo"
    result = subprocess.run(
        ["git", "clone", "--depth=1", git_url, str(clone_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed:\n{result.stderr.strip()}")
    return clone_dir


# ── Install destination ───────────────────────────────────────────────────────

def get_skills_dir(global_install: bool, universal: bool) -> Path:
    """Return the skills directory based on install scope."""
    if global_install:
        return Path.home() / ".claude" / "skills"
    if universal:
        return Path.cwd() / ".agent" / "skills"
    return Path.cwd() / ".claude" / "skills"


# ── AGENTS.md sync ────────────────────────────────────────────────────────────

def _build_xml(skills: list[dict]) -> str:
    """Render <available_skills> XML block from a list of metadata dicts."""
    lines = ["<available_skills>"]
    for meta in skills:
        name = meta.get("name", "")
        desc = meta.get("description", "")
        user_inv = meta.get("user-invocable", "true").lower() != "false"
        invocable = "user" if user_inv else "model"
        lines += [
            f'  <skill name="{name}">',
            f"    <description>{desc}</description>",
            f"    <invocable_by>{invocable}</invocable_by>",
            "  </skill>",
        ]
    lines.append("</available_skills>")
    return "\n".join(lines)


def sync_agents_md(skills_dir: Path) -> int:
    """Regenerate the <available_skills> block in AGENTS.md.

    Returns the number of skills synced.
    """
    metas: list[dict] = []
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                meta = load_skill_meta(d)
                if meta:
                    metas.append(meta)

    xml = _build_xml(metas)
    agents_md = Path.cwd() / "AGENTS.md"
    block_re = re.compile(
        r"<available_skills>.*?</available_skills>", re.DOTALL
    )

    if agents_md.exists():
        content = agents_md.read_text()
        if block_re.search(content):
            content = block_re.sub(xml, content)
        else:
            content = content.rstrip() + f"\n\n{xml}\n"
        agents_md.write_text(content)
    else:
        agents_md.write_text(xml + "\n")

    return len(metas)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_install(args: argparse.Namespace) -> None:
    skills_dir = get_skills_dir(args.global_install, args.universal)
    skills_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        try:
            source_dir = resolve_source(args.source, Path(tmp))
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            sys.exit(f"Error: {exc}")

        skill_files = find_skills(source_dir)
        if not skill_files:
            print(f"No SKILL.md files found in {args.source!r}.")
            return

        installed: list[str] = []
        for skill_md in skill_files:
            skill_dir = skill_md.parent
            meta = load_skill_meta(skill_dir)
            name = meta.get("name", skill_dir.name)

            # Optional glob filter (e.g. --skill 'core-*')
            if args.skill and not re.fullmatch(
                args.skill.replace("*", ".*"), name
            ):
                continue

            dest = skills_dir / name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)
            installed.append(name)
            print(f"  installed: {name}")

        if not installed:
            print("No matching skills found.")
            return

        print(f"\n{len(installed)} skill(s) installed → {skills_dir}")

    count = sync_agents_md(skills_dir)
    print(f"AGENTS.md synced ({count} skill(s))")


def cmd_list(args: argparse.Namespace) -> None:
    skills_dir = get_skills_dir(args.global_install, args.universal)
    if not skills_dir.exists():
        print("No skills installed.")
        return

    dirs = [d for d in sorted(skills_dir.iterdir()) if d.is_dir()]
    if not dirs:
        print("No skills installed.")
        return

    print(f"Skills in {skills_dir}:\n")
    for d in dirs:
        meta = load_skill_meta(d)
        desc = meta.get("description", "(no description)")
        print(f"  {d.name:<30}  {desc}")


def cmd_read(args: argparse.Namespace) -> None:
    skills_dir = get_skills_dir(args.global_install, args.universal)
    skill_md = skills_dir / args.name / "SKILL.md"
    if not skill_md.exists():
        sys.exit(f"Skill not found: {args.name!r}")
    print(skill_md.read_text(), end="")


def cmd_remove(args: argparse.Namespace) -> None:
    skills_dir = get_skills_dir(args.global_install, args.universal)
    skill_dir = skills_dir / args.name
    if not skill_dir.exists():
        sys.exit(f"Skill not found: {args.name!r}")
    shutil.rmtree(skill_dir)
    print(f"Removed: {args.name}")
    sync_agents_md(skills_dir)


def cmd_sync(args: argparse.Namespace) -> None:
    skills_dir = get_skills_dir(args.global_install, args.universal)
    count = sync_agents_md(skills_dir)
    print(f"AGENTS.md synced ({count} skill(s))")


# ── CLI wiring ────────────────────────────────────────────────────────────────

def _location_flags() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(
        "-g", "--global", dest="global_install", action="store_true",
        help="Use ~/.claude/skills/ (system-wide)",
    )
    p.add_argument(
        "-u", "--universal", action="store_true",
        help="Use .agent/skills/ (multi-agent compatible)",
    )
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_install",
        description="Install and manage AI agent skills.",
    )
    loc = _location_flags()
    sub = parser.add_subparsers(dest="command", required=True)

    # install
    p = sub.add_parser("install", parents=[loc], help="Install skills from a source")
    p.add_argument("source", help="owner/repo, local path, or git URL")
    p.add_argument("-y", "--yes", action="store_true", help="Skip prompts")
    p.add_argument("--skill", metavar="PATTERN", help="Filter by name glob, e.g. 'core-*'")
    p.set_defaults(func=cmd_install)

    # list
    p = sub.add_parser("list", parents=[loc], help="List installed skills")
    p.set_defaults(func=cmd_list)

    # read
    p = sub.add_parser("read", parents=[loc], help="Print a skill's SKILL.md")
    p.add_argument("name", help="Skill name")
    p.set_defaults(func=cmd_read)

    # remove
    p = sub.add_parser("remove", parents=[loc], help="Remove an installed skill")
    p.add_argument("name", help="Skill name")
    p.set_defaults(func=cmd_remove)

    # sync
    p = sub.add_parser("sync", parents=[loc], help="Regenerate AGENTS.md")
    p.set_defaults(func=cmd_sync)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
