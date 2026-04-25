# DnD 5.5e All-in-One BEYOND — Russian Localization

<p align="center">
  <img src="Projects/thumbnail.png" style="max-width: 100%; width: 80%; height: auto;" alt="Логотип мода" />
</p>

<p align="center">
  Русская локализация <strong>DnD 5.5e All-in-One BEYOND</strong> для <strong>Baldur's Gate 3</strong>.
</p>

<p align="center">
  <a href="https://mod.io/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization">mod.io</a>
  ·
  <a href="https://github.com/Yoonmoonsik/dnd55e">Оригинальный мод</a>
</p>

---

## О моде

Это русский перевод мода **DnD 5.5e All-in-One BEYOND**, который переносит в **Baldur's Gate 3** широкий пласт контента и правил **D&D 5.5e / PHB 2024**.

Локализация поддерживается в темпе с апстримом, который развивается в сторону более полного охвата классов, рас, предысторий, фитов, заклинаний и связанных игровых описаний.

Перевод все еще находится в активной доработке: автоматизация помогает быстрее обновлять тексты после апдейтов оригинального мода, а финальная вычитка и правки выполняются вручную.

## Что входит в локализацию

- описания классов, подклассов, рас и предысторий
- тексты способностей, фитов, заклинаний и связанных механик
- интерфейсные и служебные строки, добавленные оригинальным модом
- упаковка и метаданные отдельного русификатора, который ставится поверх основного мода

## Важно

Этот мод является **отдельной локализацией**, а не самостоятельной переработкой правил.

Для работы требуется установленный оригинальный мод [**DnD 5.5e All-in-One BEYOND**](https://github.com/Yoonmoonsik/dnd55e).

## Установка

1. Установите оригинальный мод **DnD 5.5e All-in-One BEYOND**.
2. Установите русскую локализацию через [mod.io](https://mod.io/g/baldursgate3/m/dnd-55e-all-in-one-beyond-russian-localization) или из релизов репозитория.
3. Убедитесь, что в игре активны и основной мод, и русификатор.

## Публикация

Релизы по тегам `v*` автоматически собираются в GitHub Actions и публикуются на mod.io через официальный **Baldur's Gate 3 Toolkit** на self-hosted Windows runner с меткой `bg3-toolkit`.

Перед первым запуском runner нужно один раз открыть Toolkit, войти в Larian/mod.io и проверить, что проект публикуется вручную. Путь к Toolkit можно задать переменной окружения или GitHub variable `BG3TOOL_PATH`; по умолчанию используется `C:\Program Files (x86)\Steam\steamapps\common\Baldurs Gate 3 Toolkit\Glasses.exe`.

Файл для mod.io создаёт и загружает Toolkit. После загрузки GitHub Actions использует secret `MODIO_ACCESS_TOKEN`, чтобы через официальный mod.io API дождаться сканирования, выставить платформы `windows,mac,xboxseriesx,ps5` и сделать новый файл live.
