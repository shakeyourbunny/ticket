#!/usr/bin/env python3
# Portions adapted from ticket (https://github.com/wedow/ticket)
# Copyright (c) Greg Wedow and ticket contributors
# Licensed under MIT
# Local changes: full Python rewrite with tree and recent commands.
#
# This file is part of the ticket Project.
# License: MIT. Contact: ticket-project@trinity2k.net
#

from __future__ import annotations

import argparse
import os
import random
import re
import string
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

TK_VERSION = "0.5.0"
TK_PART_NUMBER = "SJ-ACC-0001-20260912"

VALID_STATUSES = ("open", "in_progress", "closed")
VALID_TYPES = ("bug", "feature", "task", "epic", "chore")

TYPE_MARKERS: dict[str, str] = {
    "epic": "(E)",
    "bug": "(B)",
    "feature": "(F)",
    "chore": "(C)",
}


@dataclass
class Ticket:
    id: str = ""
    status: str = "open"
    deps: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    created: str = ""
    type: str = "task"
    priority: int = 2
    assignee: str = ""
    external_ref: str = ""
    parent: str = ""
    tags: list[str] = field(default_factory=list)
    title: str = ""
    path: Path | None = None


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_list(raw: str) -> list[str]:
    """Parse a bracket list like '[a, b, c]' into a list of strings."""
    raw = raw.strip()
    if raw in ("[]", ""):
        return []
    raw = raw.strip("[]")
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_ticket(path: Path) -> Ticket:
    """Load a ticket from a markdown file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    boundaries = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(boundaries) < 2:
        return Ticket(path=path)

    fields: dict[str, str] = {}
    for line in lines[boundaries[0] + 1 : boundaries[1]]:
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()

    title = ""
    for line in lines[boundaries[1] + 1 :]:
        if line.startswith("# "):
            title = line[2:].strip()
            break

    priority_raw = fields.get("priority", "2")
    try:
        priority = int(priority_raw)
    except ValueError:
        priority = 2

    return Ticket(
        id=fields.get("id", ""),
        status=fields.get("status", "open"),
        deps=_parse_list(fields.get("deps", "[]")),
        links=_parse_list(fields.get("links", "[]")),
        created=fields.get("created", ""),
        type=fields.get("type", "task"),
        priority=priority,
        assignee=fields.get("assignee", ""),
        external_ref=fields.get("external-ref", ""),
        parent=fields.get("parent", ""),
        tags=_parse_list(fields.get("tags", "[]")),
        title=title,
        path=path,
    )


def load_all(tickets_dir: Path) -> list[Ticket]:
    """Load all tickets from a directory, following symlinks."""
    tickets = []
    seen_inodes: set[tuple[int, int]] = set()
    for dirpath, dirnames, filenames in os.walk(tickets_dir, followlinks=True):
        dp = Path(dirpath)
        rel = dp.relative_to(tickets_dir)
        if any(part.startswith(".") for part in rel.parts):
            dirnames.clear()
            continue
        # Guard against symlink loops
        st = dp.stat()
        inode_key = (st.st_dev, st.st_ino)
        if inode_key in seen_inodes:
            dirnames.clear()
            continue
        seen_inodes.add(inode_key)
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                tickets.append(load_ticket(dp / fn))
    return tickets


def save_field(path: Path, field_name: str, value: str) -> None:
    """Update one YAML field in a ticket file, preserving the rest."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    boundaries = [i for i, line in enumerate(lines) if line.strip() == "---"]
    if len(boundaries) < 2:
        return

    found = False
    for i in range(boundaries[0] + 1, boundaries[1]):
        if lines[i].startswith(f"{field_name}:"):
            lines[i] = f"{field_name}: {value}"
            found = True
            break

    if not found:
        lines.insert(boundaries[0] + 1, f"{field_name}: {value}")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Ticket discovery and ID generation
# ---------------------------------------------------------------------------

def find_tickets_dir(start: Path | None = None) -> Path | None:
    """Walk parent directories to find .tickets/. Returns None if not found."""
    env_dir = os.environ.get("TICKETS_DIR")
    if env_dir:
        return Path(env_dir)

    current = start or Path.cwd()
    while True:
        candidate = current / ".tickets"
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def generate_id(tickets_dir: Path) -> str:
    """Generate a ticket ID with prefix from .tickets/prefix or directory name."""
    prefix = ""
    prefix_file = tickets_dir / "prefix"
    if prefix_file.is_file():
        prefix = prefix_file.read_text(encoding="utf-8").split("\n")[0].strip()

    if not prefix:
        dir_name = tickets_dir.parent.name
        parts = re.split(r"[-_]", dir_name)
        prefix = "".join(p[0] for p in parts if p)
        if len(prefix) < 2:
            prefix = dir_name[:3]

    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{prefix}-{suffix}"


def resolve_ticket(tickets_dir: Path, partial_id: str) -> Path:
    """Resolve a partial ticket ID to a file path.

    Raises SystemExit on ambiguous or not-found.
    """
    partial_id = partial_id.strip()

    exact = tickets_dir / f"{partial_id}.md"
    if exact.is_file():
        return exact

    matches = []
    for dirpath, dirnames, filenames in os.walk(tickets_dir, followlinks=True):
        dp = Path(dirpath)
        rel = dp.relative_to(tickets_dir)
        if any(part.startswith(".") for part in rel.parts):
            dirnames.clear()
            continue
        for fn in filenames:
            if fn.endswith(".md") and partial_id in Path(fn).stem:
                matches.append(dp / fn)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        lines = [f"Ambiguous ID '{partial_id}' matches {len(matches)} tickets:"]
        for m in sorted(matches):
            t = load_ticket(m)
            lines.append(f"  {t.id} - {t.title}")
        _error("\n".join(lines))

    _error(f"Ticket '{partial_id}' not found")


def _error(msg: str) -> None:
    """Print error and exit."""
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def _iso_date() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Lifecycle commands
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Create a new ticket."""
    tickets_dir.mkdir(parents=True, exist_ok=True)

    parent_id = ""
    if args.parent:
        parent_path = resolve_ticket(tickets_dir, args.parent)
        parent_id = parent_path.stem

    title = args.title or "Untitled"
    for _ in range(20):
        ticket_id = generate_id(tickets_dir)
        if not (tickets_dir / f"{ticket_id}.md").exists():
            break
    else:
        _error("Could not generate a unique ticket ID after 20 attempts")
    now = _iso_date()

    assignee = args.assignee
    if not assignee:
        try:
            result = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                assignee = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    lines = [
        "---",
        f"id: {ticket_id}",
        "status: open",
        "deps: []",
        "links: []",
        f"created: {now}",
        f"type: {args.type}",
        f"priority: {args.priority}",
    ]
    if assignee:
        lines.append(f"assignee: {assignee}")
    if args.external_ref:
        lines.append(f"external-ref: {args.external_ref}")
    if parent_id:
        lines.append(f"parent: {parent_id}")
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",")]
        lines.append(f"tags: [{', '.join(tags)}]")
    lines.append("---")
    lines.append(f"# {title}")
    lines.append("")

    if args.description:
        lines.append(args.description)
        lines.append("")
    if args.design:
        lines.append("## Design")
        lines.append("")
        lines.append(args.design)
        lines.append("")
    if args.acceptance:
        lines.append("## Acceptance Criteria")
        lines.append("")
        lines.append(args.acceptance)
        lines.append("")

    path = tickets_dir / f"{ticket_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(ticket_id)


def cmd_status(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Set ticket status."""
    new_status = args.new_status
    if new_status not in VALID_STATUSES:
        _error(
            f"Invalid status '{new_status}'. "
            f"Must be one of: {', '.join(VALID_STATUSES)}"
        )
    path = resolve_ticket(tickets_dir, args.id)
    save_field(path, "status", new_status)
    print(f"Updated {path.stem} -> {new_status}")


def cmd_start(args: argparse.Namespace, tickets_dir: Path) -> None:
    args.new_status = "in_progress"
    cmd_status(args, tickets_dir)


def cmd_close(args: argparse.Namespace, tickets_dir: Path) -> None:
    args.new_status = "closed"
    cmd_status(args, tickets_dir)


def cmd_reopen(args: argparse.Namespace, tickets_dir: Path) -> None:
    args.new_status = "open"
    cmd_status(args, tickets_dir)


# ---------------------------------------------------------------------------
# Dependency commands
# ---------------------------------------------------------------------------

def cmd_dep(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Dep command router: 'dep tree', 'dep cycle', or 'dep <id> <dep-id>'."""
    positionals = args.dep_args
    if not positionals:
        _error(
            "Usage: tk dep <id> <dep-id>\n"
            "       tk dep tree [--full] <id>\n"
            "       tk dep cycle"
        )

    if positionals[0] == "tree":
        _cmd_dep_tree(positionals[1:], tickets_dir)
    elif positionals[0] == "cycle":
        _cmd_dep_cycle(tickets_dir)
    elif len(positionals) >= 2:
        _dep_add(positionals[0], positionals[1], tickets_dir)
    else:
        _error("Usage: tk dep <id> <dep-id>")


def _dep_add(id_str: str, dep_str: str, tickets_dir: Path) -> None:
    """Add a dependency."""
    path = resolve_ticket(tickets_dir, id_str)
    dep_path = resolve_ticket(tickets_dir, dep_str)
    dep_id = dep_path.stem

    t = load_ticket(path)
    if dep_id in t.deps:
        print("Dependency already exists")
        return

    new_deps = t.deps + [dep_id]
    save_field(path, "deps", "[" + ", ".join(new_deps) + "]")
    print(f"Added dependency: {path.stem} -> {dep_id}")


def cmd_undep(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Remove a dependency."""
    path = resolve_ticket(tickets_dir, args.id)
    dep_path = resolve_ticket(tickets_dir, args.dep_id)
    dep_id = dep_path.stem

    t = load_ticket(path)
    if dep_id not in t.deps:
        _error("Dependency not found")

    new_deps = [d for d in t.deps if d != dep_id]
    save_field(path, "deps", "[" + ", ".join(new_deps) + "]" if new_deps else "[]")
    print(f"Removed dependency: {path.stem} -/-> {dep_id}")


def _cmd_dep_tree(argv: list[str], tickets_dir: Path) -> None:
    """Show dependency tree for a ticket."""
    full_mode = "--full" in argv
    argv = [a for a in argv if a != "--full"]

    if not argv:
        _error("Usage: tk dep tree [--full] <id>")

    root_path = resolve_ticket(tickets_dir, argv[0])
    root_id = root_path.stem
    all_tickets = load_all(tickets_dir)
    by_id = {t.id: t for t in all_tickets}

    if root_id not in by_id:
        _error(f"Ticket '{root_id}' not found")

    printed: set[str] = set()

    def print_node(
        tid: str, prefix: str, connector: str, visited: set[str],
    ) -> None:
        if tid not in by_id or tid in visited:
            return
        if not full_mode and tid in printed:
            return

        t = by_id[tid]
        print(f"{prefix}{connector}{tid} [{t.status}] {t.title}")
        if not full_mode:
            printed.add(tid)

        children = [d for d in t.deps if d in by_id and d not in visited]
        new_visited = visited | {tid}
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            if connector == "":
                child_prefix = prefix
            elif connector == "└── ":
                child_prefix = prefix + "    "
            else:
                child_prefix = prefix + "│   "
            child_conn = "└── " if is_last else "├── "
            print_node(child, child_prefix, child_conn, new_visited)

    root = by_id[root_id]
    print(f"{root_id} [{root.status}] {root.title}")
    printed.add(root_id)
    children = [d for d in root.deps if d in by_id]
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        print_node(child, "", connector, {root_id})


def _cmd_dep_cycle(tickets_dir: Path) -> None:
    """Find dependency cycles in open tickets."""
    all_tickets = load_all(tickets_dir)
    by_id = {t.id: t for t in all_tickets if t.status != "closed"}

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {tid: WHITE for tid in by_id}
    cycles: list[list[str]] = []
    seen_normalized: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)

        for dep in by_id[node].deps:
            if dep not in by_id:
                continue
            if color[dep] == GRAY:
                idx = path.index(dep)
                cycle = path[idx:]
                min_idx = cycle.index(min(cycle))
                normalized = cycle[min_idx:] + cycle[:min_idx]
                norm_key = ",".join(normalized)
                if norm_key not in seen_normalized:
                    seen_normalized.add(norm_key)
                    cycles.append(normalized)
            elif color[dep] == WHITE:
                dfs(dep, path)

        path.pop()
        color[node] = BLACK

    for tid in by_id:
        if color[tid] == WHITE:
            dfs(tid, [])

    if not cycles:
        print("No dependency cycles found")
        return

    for i, cycle in enumerate(cycles):
        if i > 0:
            print()
        cycle_str = " -> ".join(cycle + [cycle[0]])
        print(f"Cycle {i + 1}: {cycle_str}")
        for tid in cycle:
            t = by_id[tid]
            print(f"  {tid:<8s} [{t.status}] {t.title}")


# ---------------------------------------------------------------------------
# Link commands
# ---------------------------------------------------------------------------

def cmd_link(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Link tickets together (symmetric)."""
    raw_ids = args.ids
    if len(raw_ids) < 2:
        _error("Usage: tk link <id> <id> [id...]")

    paths = []
    ids = []
    for raw in raw_ids:
        p = resolve_ticket(tickets_dir, raw)
        paths.append(p)
        ids.append(p.stem)

    count = 0
    for i, (p, self_id) in enumerate(zip(paths, ids)):
        t = load_ticket(p)
        others = [oid for j, oid in enumerate(ids) if j != i]
        new_links = list(t.links)
        for oid in others:
            if oid not in new_links:
                new_links.append(oid)
                count += 1
        fmt = "[" + ", ".join(new_links) + "]" if new_links else "[]"
        save_field(p, "links", fmt)

    if count == 0:
        print("All links already exist")
    else:
        print(f"Added {count} link(s) between {len(ids)} tickets")


def cmd_unlink(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Remove link between two tickets (symmetric)."""
    path = resolve_ticket(tickets_dir, args.id)
    target_path = resolve_ticket(tickets_dir, args.target_id)
    self_id = path.stem
    target_id = target_path.stem

    for p, remove_id in [(path, target_id), (target_path, self_id)]:
        t = load_ticket(p)
        if remove_id in t.links:
            new_links = [lid for lid in t.links if lid != remove_id]
            fmt = "[" + ", ".join(new_links) + "]" if new_links else "[]"
            save_field(p, "links", fmt)

    print(f"Removed link: {self_id} <-> {target_id}")


# ---------------------------------------------------------------------------
# Listing commands
# ---------------------------------------------------------------------------

def cmd_ready(args: argparse.Namespace, tickets_dir: Path) -> None:
    """List open/in_progress tickets with all deps resolved."""
    all_tickets = load_all(tickets_dir)
    by_id = {t.id: t for t in all_tickets}

    assignee_filter = getattr(args, "assignee", "") or ""
    tag_filter = getattr(args, "tag", "") or ""

    ready = []
    for t in all_tickets:
        if t.status not in ("open", "in_progress"):
            continue
        if assignee_filter and t.assignee != assignee_filter:
            continue
        if tag_filter and tag_filter not in t.tags:
            continue

        all_closed = all(
            by_id[d].status == "closed"
            for d in t.deps
            if d in by_id
        )
        if all_closed:
            ready.append(t)

    ready.sort(key=lambda t: (t.priority, t.id))
    for t in ready:
        print(f"{t.id:<8s} [P{t.priority}][{t.status}] - {t.title}")


def cmd_blocked(args: argparse.Namespace, tickets_dir: Path) -> None:
    """List open/in_progress tickets with unresolved deps."""
    all_tickets = load_all(tickets_dir)
    by_id = {t.id: t for t in all_tickets}

    assignee_filter = getattr(args, "assignee", "") or ""
    tag_filter = getattr(args, "tag", "") or ""

    blocked: list[tuple[Ticket, list[str]]] = []
    for t in all_tickets:
        if t.status not in ("open", "in_progress"):
            continue
        if assignee_filter and t.assignee != assignee_filter:
            continue
        if tag_filter and tag_filter not in t.tags:
            continue

        blockers = [d for d in t.deps if d in by_id and by_id[d].status != "closed"]
        if blockers:
            blocked.append((t, blockers))

    blocked.sort(key=lambda pair: (pair[0].priority, pair[0].id))
    for t, blockers in blocked:
        blocker_str = ", ".join(blockers)
        print(f"{t.id:<8s} [P{t.priority}][{t.status}] - {t.title} <- [{blocker_str}]")


def cmd_closed(args: argparse.Namespace, tickets_dir: Path) -> None:
    """List recently closed tickets by mtime."""
    limit = getattr(args, "limit", 20) or 20
    assignee_filter = getattr(args, "assignee", "") or ""
    tag_filter = getattr(args, "tag", "") or ""

    all_tickets = load_all(tickets_dir)

    closed: list[tuple[float, Ticket]] = []
    for t in all_tickets:
        if t.status not in ("closed", "done"):
            continue
        if assignee_filter and t.assignee != assignee_filter:
            continue
        if tag_filter and tag_filter not in t.tags:
            continue
        mtime = t.path.stat().st_mtime if t.path else 0
        closed.append((mtime, t))

    closed.sort(key=lambda pair: pair[0], reverse=True)
    for _, t in closed[:limit]:
        print(f"{t.id:<8s} [{t.status}] - {t.title}")


def cmd_recent(args: argparse.Namespace, tickets_dir: Path) -> None:
    """List last N modified tickets regardless of status."""
    limit = getattr(args, "limit", 5) or 5

    all_tickets = load_all(tickets_dir)
    with_mtime: list[tuple[float, Ticket]] = []
    for t in all_tickets:
        mtime = t.path.stat().st_mtime if t.path else 0
        with_mtime.append((mtime, t))

    with_mtime.sort(key=lambda pair: pair[0], reverse=True)
    for _, t in with_mtime[:limit]:
        marker = TYPE_MARKERS.get(t.type, "")
        marker_str = f" {marker}" if marker else ""
        print(f"{t.id:<8s} [P{t.priority}][{t.status}]{marker_str} - {t.title}")


# ---------------------------------------------------------------------------
# Display commands
# ---------------------------------------------------------------------------

def cmd_show(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Display ticket with computed sections."""
    path = resolve_ticket(tickets_dir, args.id)
    target_id = path.stem
    all_tickets = load_all(tickets_dir)
    by_id = {t.id: t for t in all_tickets}
    target = by_id.get(target_id)

    text = path.read_text(encoding="utf-8")
    for line in text.split("\n"):
        if line.startswith("parent:") and target and target.parent in by_id:
            parent_title = by_id[target.parent].title
            print(f"{line}  # {parent_title}")
        else:
            print(line)

    if not target:
        return

    blockers = [d for d in target.deps if d in by_id and by_id[d].status != "closed"]
    if blockers:
        print()
        print("## Blockers")
        print()
        for d in blockers:
            t = by_id[d]
            print(f"- {d} [{t.status}] {t.title}")

    blocking = [
        t for t in all_tickets
        if target_id in t.deps and t.status != "closed"
    ]
    if blocking:
        print()
        print("## Blocking")
        print()
        for t in blocking:
            print(f"- {t.id} [{t.status}] {t.title}")

    children = [t for t in all_tickets if t.parent == target_id]
    if children:
        print()
        print("## Children")
        print()
        for t in children:
            print(f"- {t.id} [{t.status}] {t.title}")

    if target.links:
        print()
        print("## Linked")
        print()
        for lid in target.links:
            if lid in by_id:
                t = by_id[lid]
                print(f"- {lid} [{t.status}] {t.title}")


def cmd_add_note(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Append a timestamped note to a ticket."""
    path = resolve_ticket(tickets_dir, args.id)

    note_parts = getattr(args, "text", []) or []
    if note_parts:
        note = " ".join(note_parts)
    elif not sys.stdin.isatty():
        note = sys.stdin.read()
    else:
        _error("No note provided")

    timestamp = _iso_date()
    content = path.read_text(encoding="utf-8")

    if "## Notes" not in content:
        content += "\n## Notes\n"

    content += f"\n**{timestamp}**\n\n{note}\n"
    path.write_text(content, encoding="utf-8")
    print(f"Note added to {path.stem}")


# ---------------------------------------------------------------------------
# Tree command (parent-child hierarchy)
# ---------------------------------------------------------------------------

def _format_tree_line(t: Ticket) -> str:
    """Format a single tree line with type marker."""
    marker = TYPE_MARKERS.get(t.type, "")
    marker_str = f" {marker}" if marker else ""
    return f"{t.id} [P{t.priority}][{t.status}]{marker_str} {t.title}"


def _print_tree_node(
    tid: str,
    prefix: str,
    connector: str,
    by_id: dict[str, Ticket],
    children_map: dict[str, list[str]],
    visited: set[str] | None = None,
) -> None:
    """Recursively print a tree node and its children."""
    if visited is None:
        visited = set()
    if tid in visited:
        return
    visited = visited | {tid}

    t = by_id[tid]
    print(f"{prefix}{connector}{_format_tree_line(t)}")

    kids = children_map.get(tid, [])
    for i, child_id in enumerate(kids):
        is_last = i == len(kids) - 1
        child_connector = "└── " if is_last else "├── "
        if connector == "":
            child_prefix = prefix
        elif connector == "└── ":
            child_prefix = prefix + "    "
        else:
            child_prefix = prefix + "│   "
        _print_tree_node(
            child_id, child_prefix, child_connector,
            by_id, children_map, visited,
        )


def cmd_tree(args: argparse.Namespace, tickets_dir: Path) -> None:
    """Show parent-child hierarchy."""
    all_tickets = load_all(tickets_dir)
    by_id = {t.id: t for t in all_tickets}

    children_map: dict[str, list[str]] = {}
    for t in all_tickets:
        if t.parent and t.parent in by_id:
            children_map.setdefault(t.parent, []).append(t.id)

    for parent_id in children_map:
        children_map[parent_id].sort(
            key=lambda cid: (by_id[cid].priority, cid)
        )

    root_id = getattr(args, "id", None)

    if root_id:
        root_path = resolve_ticket(tickets_dir, root_id)
        root_id = root_path.stem
        if root_id not in by_id:
            _error(f"Ticket '{root_id}' not found")
        _print_tree_node(root_id, "", "", by_id, children_map)
    else:
        roots = [
            t for t in all_tickets
            if not t.parent or t.parent not in by_id
        ]
        roots.sort(key=lambda t: (t.priority, t.id))
        for i, root in enumerate(roots):
            if i > 0:
                print()
            _print_tree_node(root.id, "", "", by_id, children_map)


# ---------------------------------------------------------------------------
# Plugin system
# ---------------------------------------------------------------------------

def _find_plugin(cmd: str) -> str | None:
    """Find a plugin executable (tk-cmd or ticket-cmd) in PATH."""
    for prefix in ("tk", "ticket"):
        plugin_name = f"{prefix}-{cmd}"
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / plugin_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def _list_plugins() -> list[tuple[str, str]]:
    """List installed plugins with descriptions."""
    seen: set[str] = set()
    plugins: list[tuple[str, str]] = []

    for prefix in ("tk", "ticket"):
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            d = Path(directory)
            if not d.is_dir():
                continue
            try:
                entries = sorted(d.iterdir())
            except PermissionError:
                continue
            for candidate in entries:
                if not candidate.name.startswith(f"{prefix}-"):
                    continue
                if not candidate.is_file() or not os.access(candidate, os.X_OK):
                    continue
                cmd = candidate.name[len(prefix) + 1 :]
                if cmd in seen:
                    continue
                seen.add(cmd)

                desc = ""
                try:
                    with open(candidate, encoding="utf-8", errors="replace") as f:
                        for _, line in zip(range(10), f):
                            if line.startswith("# tk-plugin:"):
                                desc = line[len("# tk-plugin:") :].strip()
                                break
                except (OSError, UnicodeDecodeError):
                    pass

                if not desc:
                    try:
                        result = subprocess.run(
                            [str(candidate), "--tk-describe"],
                            capture_output=True, text=True, timeout=1,
                        )
                        if result.returncode == 0:
                            first = result.stdout.strip().split("\n")[0]
                            if first.startswith("tk-plugin:"):
                                desc = first[len("tk-plugin:") :].strip()
                    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                        pass

                plugins.append((cmd, desc or "(no description)"))

    return plugins


def _exec_plugin(plugin_path: str, argv: list[str]) -> None:
    """Execute a plugin, setting up the environment."""
    tickets_dir = find_tickets_dir()
    if tickets_dir and tickets_dir.is_dir():
        os.environ["TICKETS_DIR"] = str(tickets_dir)
    os.environ["TK_SCRIPT"] = str(Path(__file__).resolve())
    os.execv(plugin_path, [plugin_path] + argv)


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tk",
        description="Minimal ticket system with dependency tracking.",
    )
    parser.add_argument(
        "--version", "-V", action="version",
        version=f"tk {TK_VERSION} ({TK_PART_NUMBER})",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # create
    p = sub.add_parser("create", help="Create a new ticket.")
    p.add_argument("title", nargs="?", default="")
    p.add_argument("-d", "--description", default="")
    p.add_argument("-p", "--priority", type=int, default=2)
    p.add_argument("-t", "--type", default="task", choices=VALID_TYPES)
    p.add_argument("-a", "--assignee", default="")
    p.add_argument("--parent", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--external-ref", dest="external_ref", default="")
    p.add_argument("--design", default="")
    p.add_argument("--acceptance", default="")

    for name, help_text in [
        ("start", "Set status to in_progress."),
        ("close", "Set status to closed."),
        ("reopen", "Set status to open."),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("id")

    # status
    p = sub.add_parser("status", help="Update ticket status.")
    p.add_argument("id")
    p.add_argument("new_status", metavar="status", choices=VALID_STATUSES)

    # dep (raw args for sub-dispatch)
    p = sub.add_parser("dep", help="Manage dependencies.")
    p.add_argument("dep_args", nargs="*")

    # undep
    p = sub.add_parser("undep", help="Remove a dependency.")
    p.add_argument("id")
    p.add_argument("dep_id")

    # link
    p = sub.add_parser("link", help="Link tickets together.")
    p.add_argument("ids", nargs="+")

    # unlink
    p = sub.add_parser("unlink", help="Remove link between tickets.")
    p.add_argument("id")
    p.add_argument("target_id")

    # ready / list
    for name in ("ready", "list"):
        p = sub.add_parser(name, help="List ready tickets.")
        p.add_argument("-a", "--assignee", default="")
        p.add_argument("-T", "--tag", default="")

    # blocked
    p = sub.add_parser("blocked", help="List blocked tickets.")
    p.add_argument("-a", "--assignee", default="")
    p.add_argument("-T", "--tag", default="")

    # closed
    p = sub.add_parser("closed", help="List recently closed tickets.")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("-a", "--assignee", default="")
    p.add_argument("-T", "--tag", default="")

    # recent
    p = sub.add_parser("recent", help="List last N modified tickets.")
    p.add_argument("--limit", type=int, default=5)

    # show
    p = sub.add_parser("show", help="Display a ticket.")
    p.add_argument("id")

    # tree
    p = sub.add_parser("tree", help="Show parent-child hierarchy.")
    p.add_argument("id", nargs="?", default=None)

    # add-note
    p = sub.add_parser("add-note", help="Append a timestamped note.")
    p.add_argument("id")
    p.add_argument("text", nargs="*")

    # super
    p = sub.add_parser("super", help="Bypass plugins, run built-in.")
    p.add_argument("super_args", nargs=argparse.REMAINDER)

    return parser


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

COMMAND_DISPATCH = {
    "create": cmd_create,
    "start": cmd_start,
    "close": cmd_close,
    "reopen": cmd_reopen,
    "status": cmd_status,
    "dep": cmd_dep,
    "undep": cmd_undep,
    "link": cmd_link,
    "unlink": cmd_unlink,
    "ready": cmd_ready,
    "list": cmd_ready,
    "blocked": cmd_blocked,
    "closed": cmd_closed,
    "recent": cmd_recent,
    "show": cmd_show,
    "tree": cmd_tree,
    "add-note": cmd_add_note,
}

WRITE_COMMANDS = {"create"}


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    is_super = False
    if argv and argv[0] == "super":
        is_super = True
        argv = argv[1:]

    # Plugin check before argparse so unknown commands route to plugins
    if not is_super and argv and argv[0] not in (
        "--help", "-h", "--version", "-V", "help", "super",
    ):
        cmd = argv[0]
        plugin = _find_plugin(cmd)
        if plugin:
            _exec_plugin(plugin, argv[1:])
            return

    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return

    tickets_dir = find_tickets_dir()
    if tickets_dir is None:
        if args.command in WRITE_COMMANDS:
            tickets_dir = Path(".tickets")
        else:
            _error(
                "No .tickets directory found (searched parent directories).\n"
                "Run 'tk create' to initialize, or set TICKETS_DIR env var."
            )

    handler = COMMAND_DISPATCH.get(args.command)
    if handler:
        if args.command == "show":
            pager = os.environ.get("TICKET_PAGER") or os.environ.get("PAGER")
            if pager and sys.stdout.isatty():
                import io
                buf = io.StringIO()
                old_stdout = sys.stdout
                sys.stdout = buf
                try:
                    handler(args, tickets_dir)
                finally:
                    sys.stdout = old_stdout
                try:
                    proc = subprocess.Popen(
                        pager.split(), stdin=subprocess.PIPE, text=True,
                    )
                    proc.communicate(input=buf.getvalue())
                except (FileNotFoundError, BrokenPipeError):
                    print(buf.getvalue(), end="")
            else:
                handler(args, tickets_dir)
        else:
            handler(args, tickets_dir)
    else:
        _error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
