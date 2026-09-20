# This file is part of the ticket Project.
# License: MIT. Contact: ticket-project@trinity2k.net
#

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import ticket as tk
from conftest import make_ticket


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

class TestParseList:
    def test_empty_brackets(self):
        assert tk._parse_list("[]") == []

    def test_empty_string(self):
        assert tk._parse_list("") == []

    def test_single_item(self):
        assert tk._parse_list("[abc]") == ["abc"]

    def test_multiple_items(self):
        assert tk._parse_list("[a, b, c]") == ["a", "b", "c"]

    def test_items_with_extra_spaces(self):
        assert tk._parse_list("[ a , b , c ]") == ["a", "b", "c"]


class TestLoadTicket:
    def test_well_formed(self, tickets_dir):
        path = make_ticket(
            tickets_dir,
            id="tst-1234",
            status="in_progress",
            priority=1,
            title="Important task",
            type="bug",
            deps=["tst-0001"],
            tags=["ui", "backend"],
        )
        t = tk.load_ticket(path)
        assert t.id == "tst-1234"
        assert t.status == "in_progress"
        assert t.priority == 1
        assert t.title == "Important task"
        assert t.type == "bug"
        assert t.deps == ["tst-0001"]
        assert t.tags == ["ui", "backend"]
        assert t.path == path

    def test_missing_optional_fields(self, tickets_dir):
        path = make_ticket(tickets_dir, id="tst-min")
        t = tk.load_ticket(path)
        assert t.assignee == ""
        assert t.parent == ""
        assert t.external_ref == ""

    def test_no_frontmatter(self, tickets_dir):
        path = tickets_dir / "broken.md"
        path.write_text("# No frontmatter here\n", encoding="utf-8")
        t = tk.load_ticket(path)
        assert t.id == ""
        assert t.path == path

    def test_external_ref(self, tickets_dir):
        path = make_ticket(tickets_dir, id="tst-ref", external_ref="gh-123")
        t = tk.load_ticket(path)
        assert t.external_ref == "gh-123"

    def test_repo_field(self, tickets_dir):
        path = make_ticket(tickets_dir, id="tst-repo", repo="msgboard/appskap")
        t = tk.load_ticket(path)
        assert t.repo == "msgboard/appskap"

    def test_repo_defaults_empty(self, tickets_dir):
        path = make_ticket(tickets_dir, id="tst-norepo")
        t = tk.load_ticket(path)
        assert t.repo == ""


class TestLoadAll:
    def test_loads_multiple(self, tickets_dir):
        make_ticket(tickets_dir, id="tst-0001", title="First")
        make_ticket(tickets_dir, id="tst-0002", title="Second")
        all_tickets = tk.load_all(tickets_dir)
        assert len(all_tickets) == 2
        ids = {t.id for t in all_tickets}
        assert ids == {"tst-0001", "tst-0002"}

    def test_skips_hidden_dirs(self, tickets_dir):
        hidden = tickets_dir / ".hidden"
        hidden.mkdir()
        make_ticket(tickets_dir, id="tst-vis")
        (hidden / "tst-hid.md").write_text(
            "---\nid: tst-hid\n---\n# Hidden\n", encoding="utf-8",
        )
        all_tickets = tk.load_all(tickets_dir)
        assert len(all_tickets) == 1
        assert all_tickets[0].id == "tst-vis"

    def test_walks_subdirectories(self, tickets_dir):
        sub = tickets_dir / "closed"
        sub.mkdir()
        make_ticket(tickets_dir, id="tst-root")
        (sub / "tst-sub.md").write_text(
            "---\nid: tst-sub\nstatus: closed\n---\n# Sub\n", encoding="utf-8",
        )
        all_tickets = tk.load_all(tickets_dir)
        assert len(all_tickets) == 2

    def test_follows_symlinked_directories(self, tickets_dir, tmp_path):
        external = tmp_path / "external"
        external.mkdir()
        (external / "tst-ext.md").write_text(
            "---\nid: tst-ext\nstatus: open\n---\n# External\n", encoding="utf-8",
        )
        (tickets_dir / "linked").symlink_to(external)
        make_ticket(tickets_dir, id="tst-local")
        all_tickets = tk.load_all(tickets_dir)
        ids = {t.id for t in all_tickets}
        assert "tst-ext" in ids
        assert "tst-local" in ids


class TestSaveField:
    def test_update_existing_field(self, tickets_dir):
        path = make_ticket(tickets_dir, id="tst-0001", status="open")
        tk.save_field(path, "status", "closed")
        t = tk.load_ticket(path)
        assert t.status == "closed"

    def test_insert_new_field(self, tickets_dir):
        path = make_ticket(tickets_dir, id="tst-0001")
        tk.save_field(path, "assignee", "alice")
        t = tk.load_ticket(path)
        assert t.assignee == "alice"

    def test_preserves_body(self, tickets_dir):
        path = make_ticket(
            tickets_dir, id="tst-0001", title="Keep me", body="Body text here",
        )
        tk.save_field(path, "status", "closed")
        content = path.read_text(encoding="utf-8")
        assert "Body text here" in content
        assert "# Keep me" in content


# ---------------------------------------------------------------------------
# Discovery and ID generation
# ---------------------------------------------------------------------------

class TestFindTicketsDir:
    def test_finds_in_current(self, tmp_path):
        (tmp_path / ".tickets").mkdir()
        result = tk.find_tickets_dir(tmp_path)
        assert result == tmp_path / ".tickets"

    def test_finds_in_parent(self, tmp_path):
        (tmp_path / ".tickets").mkdir()
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)
        result = tk.find_tickets_dir(child)
        assert result == tmp_path / ".tickets"

    def test_returns_none(self, tmp_path):
        child = tmp_path / "empty"
        child.mkdir()
        result = tk.find_tickets_dir(child)
        assert result is None

    def test_env_override(self, tmp_path, monkeypatch):
        target = tmp_path / "custom"
        target.mkdir()
        monkeypatch.setenv("TICKETS_DIR", str(target))
        result = tk.find_tickets_dir(tmp_path)
        assert result == target


class TestGenerateId:
    def test_with_prefix_file(self, tickets_dir):
        (tickets_dir / "prefix").write_text("msg\n", encoding="utf-8")
        id_ = tk.generate_id(tickets_dir)
        assert id_.startswith("msg-")
        assert len(id_) == 8

    def test_from_dirname(self, tmp_path):
        d = tmp_path / "my-project" / ".tickets"
        d.mkdir(parents=True)
        id_ = tk.generate_id(d)
        assert id_.startswith("mp-")

    def test_short_dirname(self, tmp_path):
        d = tmp_path / "x" / ".tickets"
        d.mkdir(parents=True)
        id_ = tk.generate_id(d)
        assert id_[0] == "x"
        assert "-" in id_


class TestResolveTicket:
    def test_exact_match(self, tickets_dir):
        make_ticket(tickets_dir, id="tst-abcd")
        result = tk.resolve_ticket(tickets_dir, "tst-abcd")
        assert result == tickets_dir / "tst-abcd.md"

    def test_partial_match(self, tickets_dir):
        make_ticket(tickets_dir, id="tst-abcd")
        result = tk.resolve_ticket(tickets_dir, "abcd")
        assert result == tickets_dir / "tst-abcd.md"

    def test_ambiguous(self, tickets_dir):
        make_ticket(tickets_dir, id="tst-ab01")
        make_ticket(tickets_dir, id="tst-ab02")
        with pytest.raises(SystemExit):
            tk.resolve_ticket(tickets_dir, "ab")

    def test_not_found(self, tickets_dir):
        with pytest.raises(SystemExit):
            tk.resolve_ticket(tickets_dir, "nonexistent")


# ---------------------------------------------------------------------------
# Lifecycle commands
# ---------------------------------------------------------------------------

class TestCmdCreate:
    def test_creates_ticket(self, tickets_dir, capsys):
        args = argparse.Namespace(
            title="Test ticket", description="", design="", acceptance="",
            priority=2, type="task", assignee="tester", external_ref="",
            parent="", tags="", repo="msgboard/test",
        )
        tk.cmd_create(args, tickets_dir)
        captured = capsys.readouterr()
        ticket_id = captured.out.strip()
        assert (tickets_dir / f"{ticket_id}.md").is_file()
        t = tk.load_ticket(tickets_dir / f"{ticket_id}.md")
        assert t.title == "Test ticket"
        assert t.status == "open"
        assert t.priority == 2
        assert t.repo == "msgboard/test"

    def test_creates_with_parent(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-parent", title="Parent")
        args = argparse.Namespace(
            title="Child", description="", design="", acceptance="",
            priority=2, type="task", assignee="", external_ref="",
            parent="tst-parent", tags="", repo="msgboard/test",
        )
        tk.cmd_create(args, tickets_dir)
        captured = capsys.readouterr()
        child_id = captured.out.strip()
        t = tk.load_ticket(tickets_dir / f"{child_id}.md")
        assert t.parent == "tst-parent"

    def test_creates_with_tags(self, tickets_dir, capsys):
        args = argparse.Namespace(
            title="Tagged", description="", design="", acceptance="",
            priority=1, type="bug", assignee="alice", external_ref="",
            parent="", tags="ui,backend", repo="msgboard/test",
        )
        tk.cmd_create(args, tickets_dir)
        captured = capsys.readouterr()
        ticket_id = captured.out.strip()
        t = tk.load_ticket(tickets_dir / f"{ticket_id}.md")
        assert t.tags == ["ui", "backend"]
        assert t.type == "bug"

    def test_creates_untitled(self, tickets_dir, capsys):
        args = argparse.Namespace(
            title="", description="", design="", acceptance="",
            priority=2, type="task", assignee="", external_ref="",
            parent="", tags="", repo="msgboard/test",
        )
        tk.cmd_create(args, tickets_dir)
        captured = capsys.readouterr()
        ticket_id = captured.out.strip()
        t = tk.load_ticket(tickets_dir / f"{ticket_id}.md")
        assert t.title == "Untitled"

    def test_creates_with_repo(self, tickets_dir, capsys):
        args = argparse.Namespace(
            title="Repo ticket", description="", design="", acceptance="",
            priority=2, type="task", assignee="", external_ref="",
            parent="", tags="", repo="sjaandi-libs/augra-theming",
        )
        tk.cmd_create(args, tickets_dir)
        captured = capsys.readouterr()
        ticket_id = captured.out.strip()
        t = tk.load_ticket(tickets_dir / f"{ticket_id}.md")
        assert t.repo == "sjaandi-libs/augra-theming"

    def test_create_requires_repo(self, tickets_dir, monkeypatch):
        monkeypatch.setenv("TICKETS_DIR", str(tickets_dir))
        with pytest.raises(SystemExit) as exc_info:
            tk.main(["create", "Missing repo"])
        assert exc_info.value.code == 2


class TestStatusCommands:
    def test_close(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001")
        args = argparse.Namespace(id="tst-0001")
        tk.cmd_close(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-0001.md")
        assert t.status == "closed"

    def test_start(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001")
        args = argparse.Namespace(id="tst-0001")
        tk.cmd_start(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-0001.md")
        assert t.status == "in_progress"

    def test_reopen(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", status="closed")
        args = argparse.Namespace(id="tst-0001")
        tk.cmd_reopen(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-0001.md")
        assert t.status == "open"

    def test_invalid_status(self, tickets_dir):
        make_ticket(tickets_dir, id="tst-0001")
        args = argparse.Namespace(id="tst-0001", new_status="invalid")
        with pytest.raises(SystemExit):
            tk.cmd_status(args, tickets_dir)


# ---------------------------------------------------------------------------
# Dependency commands
# ---------------------------------------------------------------------------

class TestDepCommands:
    def test_add_dep(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001")
        make_ticket(tickets_dir, id="tst-0002")
        tk._dep_add("tst-0001", "tst-0002", tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-0001.md")
        assert "tst-0002" in t.deps

    def test_add_duplicate_dep(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002")
        tk._dep_add("tst-0001", "tst-0002", tickets_dir)
        captured = capsys.readouterr()
        assert "already exists" in captured.out

    def test_undep(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002")
        args = argparse.Namespace(id="tst-0001", dep_id="tst-0002")
        tk.cmd_undep(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-0001.md")
        assert "tst-0002" not in t.deps

    def test_dep_cycle_none(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002")
        tk._cmd_dep_cycle(tickets_dir)
        captured = capsys.readouterr()
        assert "No dependency cycles found" in captured.out

    def test_dep_cycle_found(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002", deps=["tst-0001"])
        tk._cmd_dep_cycle(tickets_dir)
        captured = capsys.readouterr()
        assert "Cycle 1:" in captured.out


class TestDepTree:
    def test_simple_tree(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-root", deps=["tst-dep1"], title="Root")
        make_ticket(tickets_dir, id="tst-dep1", title="Dep 1")
        tk._cmd_dep_tree(["tst-root"], tickets_dir)
        captured = capsys.readouterr()
        assert "tst-root" in captured.out
        assert "tst-dep1" in captured.out
        assert "└──" in captured.out


# ---------------------------------------------------------------------------
# Link commands
# ---------------------------------------------------------------------------

class TestLinkCommands:
    def test_link_two(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001")
        make_ticket(tickets_dir, id="tst-0002")
        args = argparse.Namespace(ids=["tst-0001", "tst-0002"])
        tk.cmd_link(args, tickets_dir)
        t1 = tk.load_ticket(tickets_dir / "tst-0001.md")
        t2 = tk.load_ticket(tickets_dir / "tst-0002.md")
        assert "tst-0002" in t1.links
        assert "tst-0001" in t2.links

    def test_link_three(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001")
        make_ticket(tickets_dir, id="tst-0002")
        make_ticket(tickets_dir, id="tst-0003")
        args = argparse.Namespace(ids=["tst-0001", "tst-0002", "tst-0003"])
        tk.cmd_link(args, tickets_dir)
        t1 = tk.load_ticket(tickets_dir / "tst-0001.md")
        assert "tst-0002" in t1.links
        assert "tst-0003" in t1.links

    def test_unlink(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", links=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002", links=["tst-0001"])
        args = argparse.Namespace(id="tst-0001", target_id="tst-0002")
        tk.cmd_unlink(args, tickets_dir)
        t1 = tk.load_ticket(tickets_dir / "tst-0001.md")
        t2 = tk.load_ticket(tickets_dir / "tst-0002.md")
        assert "tst-0002" not in t1.links
        assert "tst-0001" not in t2.links


# ---------------------------------------------------------------------------
# Listing commands
# ---------------------------------------------------------------------------

class TestReadyCommand:
    def test_lists_ready(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", title="Ready one", priority=1)
        make_ticket(tickets_dir, id="tst-0002", title="Ready two", priority=2)
        args = argparse.Namespace(assignee="", tag="")
        tk.cmd_ready(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" in out
        assert "tst-0002" in out
        assert out.index("tst-0001") < out.index("tst-0002")

    def test_filters_blocked(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002")
        args = argparse.Namespace(assignee="", tag="")
        tk.cmd_ready(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" not in out
        assert "tst-0002" in out

    def test_assignee_filter(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", assignee="alice")
        make_ticket(tickets_dir, id="tst-0002", assignee="bob")
        args = argparse.Namespace(assignee="alice", tag="")
        tk.cmd_ready(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" in out
        assert "tst-0002" not in out

    def test_tag_filter(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", tags=["ui"])
        make_ticket(tickets_dir, id="tst-0002", tags=["backend"])
        args = argparse.Namespace(assignee="", tag="ui")
        tk.cmd_ready(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" in out
        assert "tst-0002" not in out

    def test_excludes_closed(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", status="closed")
        make_ticket(tickets_dir, id="tst-0002", status="open")
        args = argparse.Namespace(assignee="", tag="")
        tk.cmd_ready(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" not in out
        assert "tst-0002" in out


class TestBlockedCommand:
    def test_shows_blocked(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"], title="Blocked")
        make_ticket(tickets_dir, id="tst-0002", title="Blocker")
        args = argparse.Namespace(assignee="", tag="")
        tk.cmd_blocked(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" in out
        assert "tst-0002" in out

    def test_not_blocked_when_dep_closed(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"])
        make_ticket(tickets_dir, id="tst-0002", status="closed")
        args = argparse.Namespace(assignee="", tag="")
        tk.cmd_blocked(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" not in out


class TestClosedCommand:
    def test_shows_closed(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", status="closed", title="Done")
        make_ticket(tickets_dir, id="tst-0002", status="open", title="Open")
        args = argparse.Namespace(limit=20, assignee="", tag="")
        tk.cmd_closed(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-0001" in out
        assert "tst-0002" not in out


class TestRecentCommand:
    def test_shows_recent(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", title="Older")
        time.sleep(0.05)
        make_ticket(tickets_dir, id="tst-0002", title="Newer")
        args = argparse.Namespace(limit=5)
        tk.cmd_recent(args, tickets_dir)
        out = capsys.readouterr().out
        assert out.index("tst-0002") < out.index("tst-0001")

    def test_limit(self, tickets_dir, capsys):
        for i in range(10):
            make_ticket(tickets_dir, id=f"tst-{i:04d}")
            time.sleep(0.01)
        args = argparse.Namespace(limit=3)
        tk.cmd_recent(args, tickets_dir)
        out = capsys.readouterr().out
        lines = [line for line in out.strip().split("\n") if line.strip()]
        assert len(lines) == 3

    def test_type_markers(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-epic", type="epic")
        make_ticket(tickets_dir, id="tst-task", type="task")
        args = argparse.Namespace(limit=10)
        tk.cmd_recent(args, tickets_dir)
        out = capsys.readouterr().out
        assert "(E)" in out


# ---------------------------------------------------------------------------
# Show and add-note
# ---------------------------------------------------------------------------

class TestShowCommand:
    def test_show_with_children(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-parent", title="Parent")
        make_ticket(tickets_dir, id="tst-child", title="Child", parent="tst-parent")
        args = argparse.Namespace(id="tst-parent")
        tk.cmd_show(args, tickets_dir)
        out = capsys.readouterr().out
        assert "## Children" in out
        assert "tst-child" in out

    def test_show_with_blockers(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", deps=["tst-0002"], title="Blocked")
        make_ticket(tickets_dir, id="tst-0002", title="Blocker")
        args = argparse.Namespace(id="tst-0001")
        tk.cmd_show(args, tickets_dir)
        out = capsys.readouterr().out
        assert "## Blockers" in out
        assert "tst-0002" in out

    def test_show_annotates_parent(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-parent", title="The Parent")
        make_ticket(tickets_dir, id="tst-child", parent="tst-parent")
        args = argparse.Namespace(id="tst-child")
        tk.cmd_show(args, tickets_dir)
        out = capsys.readouterr().out
        assert "parent: tst-parent  # The Parent" in out

    def test_show_blocking(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-blocker", title="Blocker")
        make_ticket(tickets_dir, id="tst-blocked", deps=["tst-blocker"])
        args = argparse.Namespace(id="tst-blocker")
        tk.cmd_show(args, tickets_dir)
        out = capsys.readouterr().out
        assert "## Blocking" in out
        assert "tst-blocked" in out

    def test_show_repo(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-repo", repo="msgboard/appskap")
        args = argparse.Namespace(id="tst-repo")
        tk.cmd_show(args, tickets_dir)
        out = capsys.readouterr().out
        assert "repo: msgboard/appskap" in out


class TestAddNote:
    def test_adds_note(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001")
        args = argparse.Namespace(id="tst-0001", text=["This", "is", "a", "note"])
        tk.cmd_add_note(args, tickets_dir)
        content = (tickets_dir / "tst-0001.md").read_text(encoding="utf-8")
        assert "## Notes" in content
        assert "This is a note" in content

    def test_appends_to_existing_notes(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-0001", body="## Notes\n\nOld note\n")
        args = argparse.Namespace(id="tst-0001", text=["New", "note"])
        tk.cmd_add_note(args, tickets_dir)
        content = (tickets_dir / "tst-0001.md").read_text(encoding="utf-8")
        assert "Old note" in content
        assert "New note" in content
        assert content.count("## Notes") == 1


# ---------------------------------------------------------------------------
# Tree command (parent-child hierarchy)
# ---------------------------------------------------------------------------

class TestTreeCommand:
    def test_single_root_no_children(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-root", title="Root")
        args = argparse.Namespace(id="tst-root")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-root" in out
        assert "Root" in out

    def test_parent_child(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-root", title="Root")
        make_ticket(tickets_dir, id="tst-child", title="Child", parent="tst-root")
        args = argparse.Namespace(id="tst-root")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-root" in out
        assert "└── tst-child" in out

    def test_multiple_children_sorted(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-root", title="Root")
        make_ticket(tickets_dir, id="tst-c1", title="C1", parent="tst-root", priority=2)
        make_ticket(tickets_dir, id="tst-c2", title="C2", parent="tst-root", priority=1)
        args = argparse.Namespace(id="tst-root")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert out.index("tst-c2") < out.index("tst-c1")
        assert "├── tst-c2" in out
        assert "└── tst-c1" in out

    def test_three_levels(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-root", title="Root")
        make_ticket(tickets_dir, id="tst-mid", title="Mid", parent="tst-root")
        make_ticket(tickets_dir, id="tst-leaf", title="Leaf", parent="tst-mid")
        args = argparse.Namespace(id="tst-root")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-root" in out
        assert "└── tst-mid" in out
        assert "    └── tst-leaf" in out

    def test_type_markers(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-root", type="epic", title="Epic Root")
        make_ticket(tickets_dir, id="tst-bug", type="bug", title="Bug Child", parent="tst-root")
        make_ticket(tickets_dir, id="tst-task", type="task", title="Task Child", parent="tst-root")
        args = argparse.Namespace(id="tst-root")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "(E)" in out
        assert "(B)" in out
        task_line = [line for line in out.strip().split("\n") if "tst-task" in line][0]
        assert "(T)" not in task_line

    def test_forest_mode(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-r1", title="Root 1")
        make_ticket(tickets_dir, id="tst-r2", title="Root 2")
        make_ticket(tickets_dir, id="tst-c1", title="Child of R1", parent="tst-r1")
        args = argparse.Namespace(id=None)
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-r1" in out
        assert "tst-r2" in out
        assert "tst-c1" in out

    def test_parent_cycle_does_not_crash(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-a", title="A", parent="tst-b")
        make_ticket(tickets_dir, id="tst-b", title="B", parent="tst-a")
        args = argparse.Namespace(id="tst-a")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-a" in out
        assert "tst-b" in out

    def test_self_parent_does_not_crash(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-self", title="Self", parent="tst-self")
        args = argparse.Namespace(id="tst-self")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-self" in out
        lines = [l for l in out.strip().split("\n") if l.strip()]
        assert len(lines) == 1

    def test_subtree_excludes_others(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-r1", title="Root 1")
        make_ticket(tickets_dir, id="tst-r2", title="Root 2")
        make_ticket(tickets_dir, id="tst-c1", title="Child of R1", parent="tst-r1")
        args = argparse.Namespace(id="tst-r1")
        tk.cmd_tree(args, tickets_dir)
        out = capsys.readouterr().out
        assert "tst-r1" in out
        assert "tst-c1" in out
        assert "tst-r2" not in out


# ---------------------------------------------------------------------------
# Edit command
# ---------------------------------------------------------------------------

class TestEditCommand:
    def test_edit_priority(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-ed1", title="Editable", priority=3)
        args = argparse.Namespace(
            id="tst-ed1", priority=1, type=None, assignee=None,
            repo=None, parent=None, tags=None, external_ref=None,
        )
        tk.cmd_edit(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-ed1.md")
        assert t.priority == 1

    def test_edit_repo(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-ed2", title="Needs repo")
        args = argparse.Namespace(
            id="tst-ed2", priority=None, type=None, assignee=None,
            repo="msgboard/test", parent=None, tags=None,
            external_ref=None,
        )
        tk.cmd_edit(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-ed2.md")
        assert t.repo == "msgboard/test"

    def test_edit_multiple_fields(self, tickets_dir, capsys):
        make_ticket(tickets_dir, id="tst-ed3", title="Multi")
        args = argparse.Namespace(
            id="tst-ed3", priority=0, type="bug", assignee="stefan",
            repo=None, parent=None, tags=None, external_ref=None,
        )
        tk.cmd_edit(args, tickets_dir)
        t = tk.load_ticket(tickets_dir / "tst-ed3.md")
        assert t.priority == 0
        assert t.type == "bug"
        assert t.assignee == "stefan"

    def test_edit_no_fields_errors(self, tickets_dir):
        make_ticket(tickets_dir, id="tst-ed4", title="Nothing")
        args = argparse.Namespace(
            id="tst-ed4", priority=None, type=None, assignee=None,
            repo=None, parent=None, tags=None, external_ref=None,
        )
        with pytest.raises(SystemExit):
            tk.cmd_edit(args, tickets_dir)


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------

class TestPluginDiscovery:
    def test_finds_plugin(self, tmp_path, monkeypatch):
        plugin = tmp_path / "tk-custom"
        plugin.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")
        plugin.chmod(0o755)
        monkeypatch.setenv("PATH", str(tmp_path))
        result = tk._find_plugin("custom")
        assert result is not None
        assert "tk-custom" in result

    def test_no_plugin(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path))
        result = tk._find_plugin("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

class TestMainDispatch:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            tk.main(["--version"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert tk.TK_VERSION in out
        assert tk.TK_PART_NUMBER in out

    def test_create_via_main(self, tickets_dir, capsys, monkeypatch):
        monkeypatch.setenv("TICKETS_DIR", str(tickets_dir))
        tk.main(["create", "Test from main", "--repo", "msgboard/test"])
        out = capsys.readouterr().out
        ticket_id = out.strip()
        assert (tickets_dir / f"{ticket_id}.md").is_file()

    def test_unknown_command_no_tickets(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("TICKETS_DIR", str(tmp_path))
        monkeypatch.setenv("PATH", "")
        with pytest.raises(SystemExit):
            tk.main(["nonexistent"])
