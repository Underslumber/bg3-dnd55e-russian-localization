# bg3-dnd55e-russian-localization

Русская локализация для мода **DnD 5.5e All-in-One BEYOND** для Baldur's Gate 3.

Оригинальный мод: [Yoonmoonsik/dnd55e](https://github.com/Yoonmoonsik/dnd55e)

Оригинальный `meta.lsx`: [Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/meta.lsx](https://github.com/Yoonmoonsik/dnd55e/blob/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/meta.lsx)

Репозиторий содержит только исходники локализации. Готовый `.pak` в репозиторий не добавляется.

## Installation

1. Установите оригинальный мод **DnD 5.5e All-in-One BEYOND**.
2. Получите собранный `.pak` локализации из CI-артефакта или соберите его локально.
3. Откройте **BG3ModManager**.
4. Импортируйте `.pak` локализации в менеджер модов.
5. Убедитесь, что локализация стоит после основного мода в активном порядке загрузки.
6. Сохраните порядок и экспортируйте его в игру.

## Build

Сборка выполняется вне репозитория: локально или через CI.

Для локальной сборки требуется **LSLib (Divine)**. Пример команд находится в:

- `scripts/build.sh`
- `scripts/build.ps1`

Пример упаковки:

```bash
Divine -a pack -s Mods -d build/DnD55eRussian.pak
```

В CI должен формироваться только артефакт `.pak`, без коммита бинарников обратно в репозиторий.
