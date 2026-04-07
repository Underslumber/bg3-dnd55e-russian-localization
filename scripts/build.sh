#!/usr/bin/env bash
set -euo pipefail

mkdir -p build
Divine -a create-package -g bg3 -s Mods -d "build/DnD 5.5e AIO Russian.pak"
