# This file is part of the ticket Project.
# License: MIT. Contact: ticket-project@trinity2k.net
#

PREFIX ?= $(HOME)/.local
BINDIR ?= $(PREFIX)/bin

.PHONY: install uninstall check test

install: ticket.py
	install -d "$(BINDIR)"
	ln -sf "$(CURDIR)/ticket.py" "$(BINDIR)/tk"
	@printf "Installed: %s/tk -> %s/ticket.py\n" "$(BINDIR)" "$(CURDIR)"

uninstall:
	rm -f "$(BINDIR)/tk"
	@printf "Removed: %s/tk\n" "$(BINDIR)"

check:
	python3 -m py_compile ticket.py
	@printf "Syntax OK\n"

test:
	.venv/bin/pytest tests/ -v
