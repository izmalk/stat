# Root Makefile for STAT self-testing.
#
# This wraps Makefile.template with STAT-specific paths so the tutorial
# pages (docs/tutorial/) can be tested directly.
#
# Usage:
#   make test              # classic (shell) implementation
#   make test-jubilant     # Jubilant implementation
#   make test-waitfor      # juju wait-for implementation (Juju 3.6 only)
#   make test-continue     # run all stages, don't abort on failure
#   make test-debug        # interactive shell on failure
#   make extract           # regenerate scripts only
#   make help              # show all targets
#
# Or via tox (runs each implementation in isolation):
#   tox -e stat-shell
#   tox -e stat-jubilant
#   tox -e stat-waitfor
#   tox -e stat-all

# STAT root directory (where this Makefile lives).
STAT_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# Override paths for STAT self-testing:
#   TUTORIAL_SRC — point at the real tutorial (docs/tutorial/)
#   THIS_DIR     — same as STAT_ROOT (Makefile.template uses this for EXTRACT,
#                  TASKS_DIR, and the spread working directory)
#   ROOT         — same as STAT_ROOT (Makefile.template calculates this as
#                  two levels up, which is wrong for the root Makefile)
TUTORIAL_SRC := $(STAT_ROOT)docs/tutorial

# Delegate everything else to Makefile.template.
MAKEFILE_NAME := $(notdir $(firstword $(MAKEFILE_LIST)))

%: FORCE
	@if [ "$@" != "$(MAKEFILE_NAME)" ]; then \
		$(MAKE) -f Makefile.template --no-print-directory \
			THIS_DIR="$(STAT_ROOT)" \
			ROOT="$(STAT_ROOT)" \
			TUTORIAL_SRC="$(TUTORIAL_SRC)" $@; \
	fi

FORCE: ;
.PHONY: FORCE
