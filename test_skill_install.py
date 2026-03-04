"""Tests for skill_install.py — run with: pytest"""

import argparse
import pytest
from pathlib import Path

import skill_install as si


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_skill(base: Path, name: str, description: str = "A skill") -> Path:
    """Create a minimal skill directory under *base* and return its path."""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nBody text.\n"
    )
    return d


def install_args(**kwargs) -> argparse.Namespace:
    defaults = dict(global_install=False, universal=False, yes=True, skill=None)
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def location_args(**kwargs) -> argparse.Namespace:
    defaults = dict(global_install=False, universal=False)
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ── parse_frontmatter ─────────────────────────────────────────────────────────

class TestParseFrontmatter:
    def test_basic(self):
        text = "---\nname: my-skill\ndescription: Does stuff\n---\nBody\n"
        meta, body = si.parse_frontmatter(text)
        assert meta["name"] == "my-skill"
        assert meta["description"] == "Does stuff"
        assert body.strip() == "Body"

    def test_no_frontmatter(self):
        text = "Just body text"
        meta, body = si.parse_frontmatter(text)
        assert meta == {}
        assert body == "Just body text"

    def test_value_with_colon(self):
        text = "---\ndescription: Foo: bar baz\n---\n"
        meta, _ = si.parse_frontmatter(text)
        assert meta["description"] == "Foo: bar baz"

    def test_empty_frontmatter(self):
        text = "---\n---\nBody\n"
        meta, body = si.parse_frontmatter(text)
        assert meta == {}
        assert "Body" in body

    def test_user_invocable_false(self):
        text = "---\nname: x\nuser-invocable: false\n---\n"
        meta, _ = si.parse_frontmatter(text)
        assert meta["user-invocable"] == "false"


# ── find_skills ───────────────────────────────────────────────────────────────

class TestFindSkills:
    def test_finds_skill_md_files(self, tmp_path):
        make_skill(tmp_path, "skill-a")
        make_skill(tmp_path, "skill-b")
        (tmp_path / "README.md").write_text("not a skill")

        paths = si.find_skills(tmp_path)
        names = {p.parent.name for p in paths}
        assert names == {"skill-a", "skill-b"}

    def test_nested_discovery(self, tmp_path):
        nested = tmp_path / "group"
        make_skill(nested, "deep-skill")
        paths = si.find_skills(tmp_path)
        assert any(p.parent.name == "deep-skill" for p in paths)

    def test_empty_dir(self, tmp_path):
        assert si.find_skills(tmp_path) == []


# ── load_skill_meta ───────────────────────────────────────────────────────────

class TestLoadSkillMeta:
    def test_loads_metadata(self, tmp_path):
        d = make_skill(tmp_path, "test-skill", "Test description")
        meta = si.load_skill_meta(d)
        assert meta["name"] == "test-skill"
        assert meta["description"] == "Test description"
        assert "_body" in meta

    def test_missing_skill_md(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert si.load_skill_meta(d) == {}

    def test_fallback_name_from_dirname(self, tmp_path):
        d = tmp_path / "inferred-name"
        d.mkdir()
        (d / "SKILL.md").write_text("---\n---\n")  # no name key
        meta = si.load_skill_meta(d)
        assert meta["name"] == "inferred-name"


# ── resolve_source ────────────────────────────────────────────────────────────

class TestResolveSource:
    def test_local_path(self, tmp_path):
        source = tmp_path / "skills"
        source.mkdir()
        resolved = si.resolve_source(str(source), tmp_path / "tmp")
        assert resolved == source

    def test_local_dot_prefix(self, tmp_path):
        source = tmp_path / "local"
        source.mkdir()
        resolved = si.resolve_source(str(source), tmp_path / "tmp")
        assert resolved == source

    def test_missing_local_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            si.resolve_source("/nonexistent/xyz/abc", tmp_path)

    def test_invalid_source_raises(self, tmp_path):
        with pytest.raises(ValueError):
            si.resolve_source("not valid!!!", tmp_path)

    def test_github_shorthand_builds_url(self, monkeypatch, tmp_path):
        """resolve_source should call git clone with the right GitHub URL."""
        captured = {}

        def fake_run(cmd, **_):
            captured["cmd"] = cmd
            (tmp_path / "repo").mkdir()
            class R:
                returncode = 0
            return R()

        monkeypatch.setattr(si.subprocess, "run", fake_run)
        si.resolve_source("owner/repo", tmp_path)
        assert "https://github.com/owner/repo.git" in captured["cmd"]

    def test_git_clone_failure_raises(self, monkeypatch, tmp_path):
        class FailResult:
            returncode = 1
            stderr = "authentication failed"

        monkeypatch.setattr(
            si.subprocess, "run", lambda *a, **kw: FailResult()
        )
        with pytest.raises(RuntimeError, match="git clone failed"):
            si.resolve_source("owner/repo", tmp_path)


# ── get_skills_dir ────────────────────────────────────────────────────────────

class TestGetSkillsDir:
    def test_global(self):
        d = si.get_skills_dir(global_install=True, universal=False)
        assert d == Path.home() / ".claude" / "skills"

    def test_universal(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = si.get_skills_dir(global_install=False, universal=True)
        assert d == tmp_path / ".agent" / "skills"

    def test_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        d = si.get_skills_dir(global_install=False, universal=False)
        assert d == tmp_path / ".claude" / "skills"


# ── sync_agents_md ────────────────────────────────────────────────────────────

class TestSyncAgentsMd:
    def test_creates_agents_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "hello", "Says hello")

        count = si.sync_agents_md(skills_dir)

        assert count == 1
        content = (tmp_path / "AGENTS.md").read_text()
        assert '<skill name="hello">' in content
        assert "<description>Says hello</description>" in content

    def test_updates_existing_block(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "AGENTS.md").write_text(
            "# Docs\n\n<available_skills>\n  <skill name='old'/>\n</available_skills>\n"
        )
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "new-skill", "New")

        si.sync_agents_md(skills_dir)

        content = (tmp_path / "AGENTS.md").read_text()
        assert "# Docs" in content          # header preserved
        assert "new-skill" in content
        assert "old" not in content         # old block replaced

    def test_appends_to_existing_md_without_block(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "AGENTS.md").write_text("# My Project\n")
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "s", "desc")

        si.sync_agents_md(skills_dir)

        content = (tmp_path / "AGENTS.md").read_text()
        assert "# My Project" in content
        assert "<available_skills>" in content

    def test_empty_skills_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        skills_dir.mkdir(parents=True)

        count = si.sync_agents_md(skills_dir)

        assert count == 0
        content = (tmp_path / "AGENTS.md").read_text()
        assert "<available_skills>\n</available_skills>" in content

    def test_user_invocable_false(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        d = skills_dir / "bg-skill"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: bg-skill\ndescription: Runs in bg\nuser-invocable: false\n---\n"
        )
        si.sync_agents_md(skills_dir)
        content = (tmp_path / "AGENTS.md").read_text()
        assert "<invocable_by>model</invocable_by>" in content


# ── cmd_install ───────────────────────────────────────────────────────────────

class TestCmdInstall:
    def test_installs_from_local_source(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "src"
        make_skill(source, "hello", "Hello skill")

        si.cmd_install(install_args(source=str(source)))

        installed = tmp_path / ".claude" / "skills" / "hello" / "SKILL.md"
        assert installed.exists()
        assert "hello" in (tmp_path / "AGENTS.md").read_text()

    def test_copies_extra_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "src"
        d = make_skill(source, "rich-skill")
        (d / "reference.md").write_text("extra file")

        si.cmd_install(install_args(source=str(source)))

        assert (tmp_path / ".claude" / "skills" / "rich-skill" / "reference.md").exists()

    def test_skill_filter(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "src"
        make_skill(source, "core-a")
        make_skill(source, "core-b")
        make_skill(source, "extra-c")

        si.cmd_install(install_args(source=str(source), skill="core-*"))

        skills_dir = tmp_path / ".claude" / "skills"
        assert (skills_dir / "core-a").exists()
        assert (skills_dir / "core-b").exists()
        assert not (skills_dir / "extra-c").exists()

    def test_reinstall_replaces_existing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "src"
        d = make_skill(source, "my-skill")

        si.cmd_install(install_args(source=str(source)))
        # Modify installed version
        stale = tmp_path / ".claude" / "skills" / "my-skill" / "stale.txt"
        stale.write_text("stale")

        si.cmd_install(install_args(source=str(source)))

        assert not stale.exists()  # replaced

    def test_no_skills_found(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        source = tmp_path / "empty_src"
        source.mkdir()

        si.cmd_install(install_args(source=str(source)))

        assert "No SKILL.md" in capsys.readouterr().out

    def test_bad_source_exits(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            si.cmd_install(install_args(source="/nonexistent/path"))


# ── cmd_list ──────────────────────────────────────────────────────────────────

class TestCmdList:
    def test_lists_installed_skills(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "alpha", "Alpha skill")
        make_skill(skills_dir, "beta", "Beta skill")

        si.cmd_list(location_args())

        out = capsys.readouterr().out
        assert "alpha" in out
        assert "Alpha skill" in out
        assert "beta" in out

    def test_empty_install(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        si.cmd_list(location_args())
        assert "No skills" in capsys.readouterr().out


# ── cmd_read ──────────────────────────────────────────────────────────────────

class TestCmdRead:
    def test_prints_skill_md(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "my-skill", "Does things")

        si.cmd_read(argparse.Namespace(name="my-skill", global_install=False, universal=False))

        out = capsys.readouterr().out
        assert "my-skill" in out
        assert "Does things" in out

    def test_missing_skill_exits(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            si.cmd_read(argparse.Namespace(name="ghost", global_install=False, universal=False))


# ── cmd_remove ────────────────────────────────────────────────────────────────

class TestCmdRemove:
    def test_removes_skill(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "bye-skill")

        si.cmd_remove(argparse.Namespace(name="bye-skill", global_install=False, universal=False))

        assert not (skills_dir / "bye-skill").exists()

    def test_updates_agents_md_after_remove(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        make_skill(skills_dir, "keep")
        make_skill(skills_dir, "gone")
        si.sync_agents_md(skills_dir)

        si.cmd_remove(argparse.Namespace(name="gone", global_install=False, universal=False))

        content = (tmp_path / "AGENTS.md").read_text()
        assert "keep" in content
        assert "gone" not in content

    def test_missing_skill_exits(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            si.cmd_remove(argparse.Namespace(name="ghost", global_install=False, universal=False))


# ── build_parser ──────────────────────────────────────────────────────────────

class TestBuildParser:
    def test_install_command(self):
        parser = si.build_parser()
        args = parser.parse_args(["install", "owner/repo"])
        assert args.command == "install"
        assert args.source == "owner/repo"
        assert args.func == si.cmd_install

    def test_list_command(self):
        args = si.build_parser().parse_args(["list"])
        assert args.func == si.cmd_list

    def test_global_flag(self):
        args = si.build_parser().parse_args(["list", "--global"])
        assert args.global_install is True

    def test_universal_flag(self):
        args = si.build_parser().parse_args(["install", "x/y", "--universal"])
        assert args.universal is True

    def test_skill_filter_flag(self):
        args = si.build_parser().parse_args(["install", "x/y", "--skill", "core-*"])
        assert args.skill == "core-*"

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            si.build_parser().parse_args([])
