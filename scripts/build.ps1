$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath "build")) {
    New-Item -ItemType Directory -Path "build" | Out-Null
}

Divine -a pack -s Mods -d "build/DnD 5.5e AIO Russian.pak"
