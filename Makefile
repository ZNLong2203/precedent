.PHONY: setup test lint demo data data-check eval web vendor-web svgs mcp clean

UPSTREAM        ?= https://github.com/relatedb/relate
UPSTREAM_COMMIT ?= 1ebb65eb6c375a3dbe67b0a2d5618f346f3139d1
CACHE           ?= .cache/relate
STORE           ?= data/relate-adr.rl

setup:                ## install with dev dependencies
	uv sync --extra dev

test:                 ## run the test suite
	uv run pytest

lint:                 ## ruff
	uv run ruff check src tests scripts

demo:                 ## 20-second tour on the committed store
	uv run precedent demo

$(CACHE)/.git:        ## pinned checkout of the corpus
	mkdir -p $(CACHE)
	git -C $(CACHE) init -q
	git -C $(CACHE) remote add origin $(UPSTREAM)
	git -C $(CACHE) fetch -q --depth 1 origin $(UPSTREAM_COMMIT)
	git -C $(CACHE) checkout -q FETCH_HEAD

data: $(CACHE)/.git   ## rebuild the store and the browser export from the pinned corpus
	rm -f $(STORE) $(STORE:.rl=.lsa.npz)
	uv run precedent index $(CACHE) --out $(STORE) --name relatedb/relate --source-url $(UPSTREAM) \
	  --license Apache-2.0 --rename cypherlite=relate
	uv run precedent export-web --store $(STORE) --out docs/data

eval: $(CACHE)/.git   ## recompute every number quoted in docs/evaluation.md
	uv run python scripts/evaluate.py --repo $(CACHE) --store $(STORE)

web:                  ## serve the browser explorer on http://localhost:8765
	python3 -m http.server -d docs 8765

vendor-web:           ## re-vendor the WASM bundle and force-graph into docs/assets
	./scripts/vendor-web.sh

svgs:                 ## re-render the README SVGs from real CLI output
	uv run python scripts/make_cli_svgs.py

mcp:                  ## serve the MCP tools on stdio
	uv run precedent mcp --store $(STORE)

clean:
	rm -rf .cache .pytest_cache .ruff_cache build dist src/*.egg-info

data-check: $(CACHE)/.git  ## rebuild into a temp file and compare content with the committed store
	uv run python scripts/check_reproducible.py --repo $(CACHE) --store $(STORE)
