.PHONY: analyze run index package lint format test setup trade-demo dashboard

RUN = uv run main.py

analyze:
	$(RUN) analyze

trade-demo:
	uv run python -m src.trading.demo

dashboard:
	uv run python -m src.trading.dashboard.app

run:
	$(RUN) analyze $(filter-out $@,$(MAKECMDGOALS))

index:
	$(RUN) index

package:
	$(RUN) package

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest tests/ -v

setup:
	bash scripts/install-tools.sh
	bash scripts/download.sh

%:
	@:
