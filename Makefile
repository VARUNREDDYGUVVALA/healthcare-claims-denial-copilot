PYTHON ?= python

.PHONY: data train evaluate export test build compose

data:
	$(PYTHON) -m scripts.generate_data

train:
	$(PYTHON) -m scripts.train_models

evaluate:
	$(PYTHON) -m scripts.evaluate_models

export:
	$(PYTHON) -m scripts.export_demo

test:
	$(PYTHON) -m pytest -q
	npm --prefix apps/frontend run check
	npm --prefix apps/frontend run build
	npm --prefix apps/frontend test

build:
	npm --prefix apps/frontend run build

compose:
	docker compose up --build -d
