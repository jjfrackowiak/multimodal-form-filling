.PHONY: check lint format typecheck imports test sync

# All first-party packages, for lint/typecheck (which apply uniformly).
PACKAGES := packages/mff-contracts packages/mff-vision packages/mff-docmodel \
            packages/mff-manifest packages/mff-applier packages/mff-store
SERVICES := services/email-service services/editor-service services/vision-stub

# Coverage-gated at >=85%: B0's own deliverable (mff-contracts) plus the empty
# skeletons B0 owns (trivially at 100%, and stay that way until a later branch adds
# logic and its own tests). mff-vision and vision-stub predate this branch and are not
# B0's to touch — their tests still run (below), just without a new coverage floor
# imposed on code this branch did not write.
COVERAGE_PACKAGES := packages/mff-contracts packages/mff-docmodel packages/mff-manifest \
                      packages/mff-applier packages/mff-store services/email-service \
                      services/editor-service
UNGATED_PACKAGES := packages/mff-vision services/vision-stub

sync:
	uv sync --all-packages

check: lint typecheck imports test

lint:
	uv run ruff format --check packages services
	uv run ruff check packages services

format:
	uv run ruff format packages services
	uv run ruff check --fix packages services

typecheck:
	@set -e; \
	for pkg in $(PACKAGES) $(SERVICES); do \
		echo "== mypy $$pkg =="; \
		uv run mypy "$$pkg/src" "$$pkg/tests"; \
	done

imports:
	uv run lint-imports

# Coverage is measured per package (not globally) so one well-tested package
# cannot hide four untested ones.
test:
	@set -e; \
	for pkg in $(COVERAGE_PACKAGES); do \
		name=$$(basename "$$pkg" | tr '-' '_'); \
		echo "== $$pkg ($$name) =="; \
		uv run pytest "$$pkg/tests" -q \
			--cov="$$name" --cov-report=term-missing --cov-fail-under=85; \
	done
	@for pkg in $(UNGATED_PACKAGES); do \
		echo "== $$pkg (no new coverage gate — pre-existing, not B0's) =="; \
		uv run pytest "$$pkg/tests" -q; \
	done
