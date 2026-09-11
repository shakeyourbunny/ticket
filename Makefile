# This file is part of the ticket Project.
# License: MIT. Contact: ticket-project@trinity2k.net
#

PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin

.PHONY: install uninstall check test

install: ticket
	install -d "$(BINDIR)"
	ln -sf "$(CURDIR)/ticket" "$(BINDIR)/tk"
	@printf "Installed: %s/tk -> %s/ticket\n" "$(BINDIR)" "$(CURDIR)"

uninstall:
	rm -f "$(BINDIR)/tk"
	@printf "Removed: %s/tk\n" "$(BINDIR)"

check:
	bash -n ticket
	@if [ -x $(HOME)/bin/shellcheck ]; then \
		$(HOME)/bin/shellcheck ticket; \
	else \
		printf "shellcheck not found at ~/bin/shellcheck, skipping\n"; \
	fi
	@printf "Syntax OK\n"

test:
	uv run --with behave behave
