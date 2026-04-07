#!/usr/bin/env bash
set -euo pipefail

mkdir -p build
Divine -a pack -s Mods -d "build/DnD 5.5e AIO Russian.pak"
