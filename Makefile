.PHONY: setup build test test-fast dev publish schema
PY ?= python3

setup:            ## install pipeline and web dependencies
	$(PY) -m pip install -e "pipeline[dev]"
	cd web && npm ci

build:            ## run all adapters on fixtures, compile registry and health
	mm build

test:             ## everything (Claude runs this locally before every merge)
	cd pipeline && $(PY) -m pytest -q -n 2
	mm schema && git diff --exit-code schemas/
	mm build
	cd web && npm run gen:types && git diff --exit-code src/generated/ && npm run typecheck && npm test && npx vite build

test-fast:        ## the CI subset
	cd pipeline && $(PY) -m pytest -q -n 2 -m "not slow"

publish:          ## publish from stored live data (fixtures where none); no network
	mm publish

dev: publish      ## local site at http://127.0.0.1:5173
	cd web && npm run dev
