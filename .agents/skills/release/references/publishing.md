# Публикация

## CI flow

`.github/workflows/build.yml` — SSOT порядка jobs и текущей конфигурации. На tag `v*` ожидается:

1. сборка `.pak`, `info.json` и release ZIP;
2. создание или обновление GitHub Release;
3. загрузка на Nexus Mods;
4. публикация на mod.io после успешных предыдущих jobs.

`workflow_dispatch` собирает artifacts, но не публикует release без tag.

## Границы агента

- Обычная публикация запускается push тега; не вызывать локальные publish-скрипты дополнительно.
- Не публиковать build ZIP как источник mod.io: официальный BG3 Toolkit создаёт и загружает mod.io package.
- mod.io API только активирует загруженный Toolkit modfile через `active=true`; API не загружает archive.
- Локальный или ручной fallback запускать только по прямому запросу пользователя.
- Точные variables и secrets читать из `.github/workflows/build.yml`, `.env.example` и вызываемых scripts; не копировать их в корневые инструкции.

## mod.io invariants

- Job: `publish_to_modio`, runner labels: `self-hosted`, `Windows`, `bg3-toolkit`.
- Использовать только официальный BG3 Toolkit/Bg3Tool; default tool path задан в workflow.
- Перед Toolkit publish обновить parent repo, потребовать его чистый worktree, синхронизировать с configured remote branch и только затем заменить parent mod folder в BG3 Mods.
- Первая публикация на runner требует ручной проверки Larian/mod.io авторизации в Toolkit.
- Не хранить account credentials в репозитории.
- Обязательные handles: mod `5965149`, dependency `4419649`.
- Fallback: `scripts/publish-modio-ui.ps1`, только если CLI publish недоступен и пользователь явно разрешил локальную публикацию.
