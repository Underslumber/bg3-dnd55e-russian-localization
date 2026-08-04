# Версия и tag

## Контракт

- SSOT исходной версии: `ModuleInfo/Version64` в `Mods/DnD 5.5e AIO Russian/meta.lsx`.
- XPath: `save/region[@id="Config"]/node[@id="root"]/children/node[@id="ModuleInfo"]/attribute[@id="Version64"]`.
- `Version64` хранится как упакованный `int64`, а не строка `X.Y.Z.N`.
- `PublishVersion/Version64` не изменять.
- Tag должен соответствовать декодированной версии `ModuleInfo/Version64`.

## Форматы

- `vX.Y.Z`: логическая версия `X.Y.Z.0`.
- `vX.Y.Z-suffix`: логическая версия `X.Y.Z.N`; suffix задаёт канал tag, но не кодируется в `Version64`.
- Для suffixed tag `N` равно количеству уже существующих локальных `vX.Y.Z-*` плюс 1, начиная с 1.
- Перед вычислением suffixed версии обновить tags: `git fetch --tags --prune`.
- Stable tag всегда использует build-компонент `0`.

## Команды

Если исходная версия ещё не соответствует выбранному tag:

```powershell
python scripts/set-version.py -VersionTag <tag>
```

Проверка перед релизом:

```powershell
python scripts/validate-repo.py --mode pre-release --version-tag <tag>
```

Команда должна завершиться успешно на чистом worktree. Если несоответствие остаётся, остановить релиз.

`scripts/build.ps1 -VersionTag <tag>` также изменяет исходный `meta.lsx`, а не только staging. Не использовать сборку как скрытый способ bump версии; после локального build всегда проверить diff.
