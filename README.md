# skill_install.py

Python port of `npx skill install` — install and manage AI agent skills.

- **Single file** (`skill_install.py`)
- **No external dependencies** — stdlib only (`argparse`, `pathlib`, `shutil`, `subprocess`, `re`, `tempfile`)
- **Python 3.10+**

---

## What are skills?

Skills are portable AI-agent capabilities defined by a `SKILL.md` file (with YAML frontmatter). They live in `.claude/skills/` and are indexed in `AGENTS.md` so Claude Code and other agents can discover and invoke them.

```
.claude/skills/
└── explain-code/
    ├── SKILL.md      ← required (name, description, …)
    └── reference.md  ← optional supporting files
AGENTS.md             ← auto-generated index
```

---

## Installation

No install needed — just copy `skill_install.py` to your project.

```bash
# optional: make it executable
chmod +x skill_install.py
```

---

## Usage

```
python skill_install.py <command> [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `install <source>` | Install skills from a source |
| `list` | List installed skills |
| `read <name>` | Print a skill's `SKILL.md` |
| `remove <name>` | Remove an installed skill |
| `sync` | Regenerate `AGENTS.md` |

### Source formats

| Format | Example |
|--------|---------|
| GitHub shorthand | `owner/repo` |
| Local path | `./my-skills/` |
| Git URL | `https://github.com/owner/repo.git` |

### Options

| Flag | Description |
|------|-------------|
| `-g, --global` | Install to `~/.claude/skills/` (system-wide) |
| `-u, --universal` | Install to `.agent/skills/` (multi-agent) |
| `--skill PATTERN` | Filter by name glob, e.g. `core-*` |
| `-y, --yes` | Skip confirmation prompts |

### Examples

```bash
# Install all skills from a GitHub repo
python skill_install.py install anthropics/skills

# Install only skills whose name starts with "core-"
python skill_install.py install anthropics/skills --skill 'core-*'

# Install from a local directory
python skill_install.py install ./my-custom-skills/

# Install system-wide
python skill_install.py install anthropics/skills --global

# List what's installed
python skill_install.py list

# Print a skill's content (for agents)
python skill_install.py read explain-code

# Remove a skill
python skill_install.py remove explain-code

# Regenerate AGENTS.md after manual changes
python skill_install.py sync
```

---

## SKILL.md format

Each skill is a directory containing a `SKILL.md` file with YAML frontmatter:

```markdown
---
name: explain-code
description: Explains code with diagrams and step-by-step breakdowns
user-invocable: true
---

## Overview

This skill generates clear explanations of code...
```

Supported frontmatter keys:

| Key | Required | Description |
|-----|----------|-------------|
| `name` | recommended | Skill identifier (defaults to directory name) |
| `description` | recommended | One-line description shown to agents |
| `user-invocable` | optional | `false` = agent-only skill (default: `true`) |

---

## AGENTS.md output

After install/sync, `AGENTS.md` in the project root will contain:

```xml
<available_skills>
  <skill name="explain-code">
    <description>Explains code with diagrams and step-by-step breakdowns</description>
    <invocable_by>user</invocable_by>
  </skill>
</available_skills>
```

Claude Code reads this at startup to make skills available.

---

## Running tests

```bash
pip install pytest
pytest test_skill_install.py -v
```

Tests cover: frontmatter parsing, skill discovery, source resolution, install/remove/list/read/sync commands, and CLI argument parsing. No network access is required (GitHub clone is monkeypatched).

---

## File layout

```
skills_p/
├── skill_install.py      ← main script (single file, no deps)
├── test_skill_install.py ← pytest test suite
└── README.md
```
