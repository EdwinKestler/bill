#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$script_dir/src"

for source_file in "$source_dir"/*.mmd; do
  output_file="$script_dir/$(basename "${source_file%.mmd}").png"
  npx --yes @mermaid-js/mermaid-cli@12.0.0 \
    --puppeteerConfigFile "$script_dir/puppeteer-config.json" \
    --configFile "$script_dir/mermaid-config.json" \
    --input "$source_file" \
    --output "$output_file" \
    --backgroundColor white \
    --size 2800 \
    --scale 1
done
