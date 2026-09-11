# ticket (tk)

House fork of [wedow/ticket](https://github.com/wedow/ticket). Minimal
git-backed ticket system used across all house projects.

- Part number: SJ-ACC-0001
- License: MIT (upstream, kept per adopted-fork rule)
- Canonical: gitlab.com/tools-of-the-trade/ticket
- Mirror: github.com/shakeyourbunny/ticket

## Architecture

Single-file bash script (`ticket`, ~1400 lines). Uses awk for bulk
operations on large ticket sets. Tickets are markdown files with YAML
frontmatter in `.tickets/`.

Key functions:
- `generate_id()` - prefix from `.tickets/prefix` or directory name + random suffix
- `ticket_path()` - resolves partial IDs to full file paths
- `yaml_field()` / `update_yaml_field()` - YAML frontmatter via sed
- `cmd_*()` - command handlers
- `cmd_ready()`, `cmd_blocked()`, `cmd_ls()` - awk-based bulk listing

Dependencies: bash 4+, sed, awk, find. Optional: ripgrep, jq (for plugins).

## Plugin system

Commands extend via `tk-<cmd>` or `ticket-<cmd>` executables in PATH.
`tk super foo` bypasses plugins and runs the built-in. Plugins receive
`TICKETS_DIR` and `TK_SCRIPT` environment variables.

## House changes from upstream

- `.tickets/prefix` file overrides the auto-derived ticket ID prefix
- `find -L` follows symlinks in ticket directories
- `list` command as alias for `ready`
- `--version` / `-V` prints version and part number
- License header and attribution per house rules

## Install

`make install` symlinks to `~/.local/bin/tk`. `make uninstall` removes it.
`make check` runs bash -n and shellcheck.

## Changelog

Update CHANGELOG.md when committing notable changes. Core script changes
(commands, flags, bug fixes, behavior) go under Added/Fixed/Changed/Removed.
Plugin changes go under a Plugins subsection. Doc-only and CI-only changes
do not need logging.

## Commits

This repo is public, process it according to the global rules.
