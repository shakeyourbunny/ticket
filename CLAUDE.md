# ticket (tk)

House fork of [wedow/ticket](https://github.com/wedow/ticket). Minimal
git-backed ticket system used across all house projects.

- Part number: SJ-ACC-0001
- License: MIT (upstream, kept per adopted-fork rule)
- Canonical: gitlab.com/tools-of-the-trade/ticket
- Mirror: github.com/shakeyourbunny/ticket

## Architecture

Single-file Python script (`ticket.py`, ~570 lines). Tickets are
markdown files with YAML frontmatter in `.tickets/`.

Data model: `Ticket` dataclass with fields parsed by a hand-rolled
frontmatter parser (no PyYAML dependency). No external dependencies,
standard library only.

CLI: argparse with subparsers, `metavar="<command>"`.

Key functions:
- `load_ticket(path)` / `load_all(tickets_dir)` - parse ticket files
- `save_field(path, field, value)` - update one YAML field in place
- `resolve_ticket(tickets_dir, partial_id)` - partial ID matching
- `generate_id(tickets_dir)` - prefix from `.tickets/prefix` or
  directory name, plus random suffix
- `cmd_*()` - command handlers

The bash version (1406 lines) is preserved on the
`20260912-bash-legacy` branch.

## Commands

Lifecycle: create, start, close, reopen, status.
Dependencies: dep, undep, dep tree, dep cycle.
Links: link, unlink.
Listing: ready/list, blocked, closed, recent.
Display: show, tree, add-note.
Meta: super, --version, --help.

## Plugin system

Commands extend via `tk-<cmd>` or `ticket-<cmd>` executables in PATH.
`tk super foo` bypasses plugins and runs the built-in. Plugins receive
`TICKETS_DIR` and `TK_SCRIPT` environment variables.

## House changes from upstream

- Full Python rewrite (was bash/awk)
- `tree [id]` command for parent-child hierarchy with type markers
- `recent [--limit=N]` command for last N modified tickets
- `.tickets/prefix` file overrides the auto-derived ticket ID prefix
- Symlink-aware directory walking
- `list` command as alias for `ready`
- `--version` / `-V` prints version and part number
- Better error messages: per-command --help, ambiguous IDs list
  candidates
- License header and attribution per house rules

## Install

`make install` symlinks ticket.py to `~/.local/bin/tk`.
`make uninstall` removes it. `make check` runs py_compile.
`make test` runs pytest.

## Testing

pytest in `.venv/` (`make test`). Test fixtures in `tests/conftest.py`
with a `make_ticket()` helper. Existing behave BDD tests in `features/`
cover CLI integration.

## Changelog

Update CHANGELOG.md when committing notable changes. Core script changes
(commands, flags, bug fixes, behavior) go under Added/Fixed/Changed/Removed.
Plugin changes go under a Plugins subsection. Doc-only and CI-only changes
do not need logging.

## Commits

This repo is public, process it according to the global rules.
