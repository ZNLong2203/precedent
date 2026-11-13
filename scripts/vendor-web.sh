#!/usr/bin/env bash
# Vendor the browser dependencies into docs/ so GitHub Pages serves the explorer with no build step.
#   - Relate compiled to WebAssembly (@relate/relate-wasm, Apache-2.0)
#   - force-graph (MIT) for the canvas graph view
set -euo pipefail
cd "$(dirname "$0")/.."
RELATE_WASM_VERSION="${RELATE_WASM_VERSION:-1.0.1}"
FORCE_GRAPH_VERSION="${FORCE_GRAPH_VERSION:-1.51.0}"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
( cd "$tmp" && npm pack "@relate/relate-wasm@${RELATE_WASM_VERSION}" "force-graph@${FORCE_GRAPH_VERSION}" --silent >/dev/null )
mkdir -p "$tmp/relate" "$tmp/fg"
tar xzf "$tmp"/relate-relate-wasm-*.tgz -C "$tmp/relate" --strip-components=1
tar xzf "$tmp"/force-graph-*.tgz -C "$tmp/fg" --strip-components=1
rm -rf docs/assets/relate && mkdir -p docs/assets/relate docs/assets/vendor
cp -R "$tmp"/relate/relate.js "$tmp"/relate/trap.js "$tmp"/relate/relate_bg.wasm "$tmp"/relate/snippets docs/assets/relate/
cp "$tmp/fg/dist/force-graph.min.js" docs/assets/vendor/force-graph.min.js
cat > docs/assets/vendor/LICENSES.md <<LIC
# Vendored third-party files

| file | project | version | license |
| --- | --- | --- | --- |
| assets/relate/* | [@relate/relate-wasm](https://www.npmjs.com/package/@relate/relate-wasm) (Neo4j) | ${RELATE_WASM_VERSION} | Apache-2.0 |
| assets/vendor/force-graph.min.js | [force-graph](https://github.com/vasturiano/force-graph) | ${FORCE_GRAPH_VERSION} | MIT |
LIC
echo "vendored relate-wasm ${RELATE_WASM_VERSION} and force-graph ${FORCE_GRAPH_VERSION}"
