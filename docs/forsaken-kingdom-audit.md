# Аудит war3observer под Warcraft III: Forsaken Kingdom (патч 3.0)

Дата: 2026-10-16
Проверенная сборка игры: **3.0.0.24268** (`S:\Programs\Battlenet\Games\Warcraft III`, `.build.info`)
Состояние репозитория: `master` @ `898981e`, последние изменения под API — Reforged 1.32 (февраль 2020).

## Как проверялось

- Прочитан код сервера (`war3observer/`), клиента (`client/`) и `tools/extract_icons.py`.
- Данные игры прочитаны из CASC через war3structs (ту же библиотеку, что использует проект; `CascLib.dll` x64 из её репозитория работает с текущим хранилищем).
- Сервер и `extract_icons.py` запускались в отдельном venv: Python 3.14.3, construct 2.10.70, lark-parser 0.12.0, websockets 17.2, Pillow 12.3.0, war3structs @ `171c912` (2020-02-09).
- Изменения сверены с официальными патчноутами 3.0.0 и 3.0.1 (ссылки внизу).
- В репозитории ничего не исправлялось. Добавлены только этот отчёт и `tools/probe_observer_api.py`.

## Что такое Forsaken Kingdom с точки зрения оверлея

| Изменение | Важно для оверлея? |
|---|---|
| Новый нейтральный герой таверны **Forsaken Paladin** (`Npal`) | **Да** — новые ID героя и способностей, новые иконки |
| Новый графический режим **Definitive Edition** (DE), Classic HD удалён | **Да** — третий набор иконок |
| Новая UI-тема Forsaken, HUD Forsaken (выбирается для игрока в World Editor) | Опционально (визуальная тема) |
| Две новые кампании, RPG-системы (экипировка, таланты, расширенный инвентарь) | Только для кампаний и кастомок |
| Лимит выделения юнитов 12 → 24 | Нет |
| Удалены LAN- и оффлайн-режим (остались в Classic Client) | Нет |
| Новой играбельной расы **нет** | — |

Данные Forsaken Paladin в игре:

- `unitskin.txt`: `[Npal] Art=ReplaceableTextures\CommandButtons\BTNForsakenPaladin.blp`, `heroAbilSkinList=AHcr,ANcp,AHpa,AHcl`
- Способности: `AHcr` Consecration, `ANcp` Righteous Fury, `AHpa` Sacred Aura (`PASBTNSacredAura`), `AHcl` Cleansing Fire
- `neutralunitfunc.txt`: добавлен в `[ntav] Sellunits` и `[HERO] DependencyOr`
- `unitdata.slk`: race = `creeps` (обычный нейтральный герой)

Значения расы в `unitdata.slk`: creeps, human, other, undead, orc, nightelf, critters, naga, demon, commoner — новых нет. Перечисление `race` в war3structs менять не нужно.

---

## P0 — блокеры

### 1. Сервер не запускается на актуальных зависимостях (проверено)

`requirements.txt` не закрепляет версии. Сейчас ставится websockets 17, и запуск падает:

```
File "war3observer/server.py", line 31, in serve
  start_server = websockets.serve(self.connect_client, ...)
RuntimeError: no running event loop
```

Причины:
- `asyncio.get_event_loop().run_until_complete(...)`: это устаревший шаблон, а новый `websockets.serve` требует уже запущенного event loop.
- Обработчик `connect_client(self, websocket, path)`: в новом API websockets обработчик получает только соединение.

Что делать: перейти на `asyncio.run()` и `async with websockets.serve(...)`, убрать `path`, закрепить версии в `requirements.txt` (включая war3structs по конкретному коммиту).

Это не связано с FK, но без исправления ничего не работает.

### 2. Работает ли observer API в 3.0, пока не проверено

- Строки `War3StatsObserverSharedMemory` в `Warcraft III.exe` и `war3_loader.dll` нет ни в ASCII, ни в UTF-16. Это **ничего не доказывает**: секция `.text` зашифрована (энтропия 8.00), строки могут собираться во время работы. В импортах есть `CreateFileMappingA` и `MapViewOfFile`.
- Найденные `W3.Net.Client.StatsHeroes`, `StatsItems` и т.п. — это protobuf-сообщения для сервера Blizzard, а не shared memory.
- **Проблема в коде:** [game.py](../war3observer/game.py) открывает память через `mmap.mmap(-1, size, "War3StatsObserverSharedMemory")`. На Windows это `CreateFileMapping`, который **молча создаёт пустую область**, если игра её не создала. Если API удалён или переименован, сервер бесконечно покажет `is_in_game=False` без единой ошибки. Кроме того, сервер сам пишет `refresh_rate` в эту область при старте.
- Разметка структур (`ObserverGame`, `ObserverPlayer`) взята из war3structs 2020 года (1.32). Поле `version` в заголовке (смещение 0) никогда не читается и не проверяется.

**Что сделать первым делом:** запустить пробник во время реплея или наблюдения за игрой:

```
python -I tools/probe_observer_api.py
```

Нужны `construct` и war3structs:
`python -m venv .venv && .venv\Scripts\pip install construct lark-parser git+https://github.com/sides/war3structs.git`.

Что делает скрипт:
- открывает область через `OpenFileMappingW`, то есть ничего не создаёт;
- выводит размер области, `version` и `refresh_rate`;
- при необходимости записывает `refresh_rate=2000`;
- сравнивает размер с ожидаемым `ObserverFile.sizeof()`;
- разбирает игру, игроков, героев, способности и предметы.

Как читать результат:
- `NOT FOUND` при запущенной игре в реплее — API удалён или переименован, дальше нужен реверс.
- Область найдена, но `players` разбираются как мусор, или размер меньше ожидаемого — разметка изменилась, нужно обновлять структуры в war3structs.
- Всё разбирается нормально — можно идти дальше по списку.

Независимо от результата: заменить `mmap(-1, ...)` на `OpenFileMapping` (или проверять, что область создала игра) и выдавать понятную ошибку «API недоступен» вместо пустого состояния.

### 3. `tools/extract_icons.py` падает на данных 3.0 (проверено)

**a) Новая синтаксическая ошибка в данных игры.** `configparser.ParsingError` на `units\unitskin.txt`, строка 24201:

```
portrait:hdunits\creeps\RazorManeChief\RazorManeChief_portrait
```

Не хватает `=`. Исправляется заменой `portrait:hdunits` → `portrait:hd=units`, по аналогии с уже существующими хаками для `Stuffed Penguin` и `MishaLvl1`. Лучше сделать парсер терпимым к таким ошибкам, чтобы каждый патч не ломал скрипт.

Дубликаты секций (17 в `abilityskin.txt`, `[Ubal]` в `unitskin.txt`) проходят благодаря `strict=False`.

**b) Отсутствующие файлы иконок.** После обхода пункта (a), если обернуть каждое чтение в try/except:

| | Не найдено | Записано |
|---|---|---|
| SD | 337 | 2424 |
| HD | 518 | 2600 |

- Без try/except скрипт падает на первой же отсутствующей иконке. Обработку ошибок нужно делать по каждому файлу.
- Почти все отсутствующие — предметы и способности кампаний FK.
- **Важное для мили:** у `Npal`, `AHcr`, `ANcp`, `AHpa`, `AHcl` **нет иконок в `war3.w3mod:_hd.w3mod:`**. Они есть только в SD (`war3.w3mod:`) и в новом `war3.w3mod:_de.w3mod:`.

Иконки старых героев и предметов (`Hamg`, `Udea`, `Ofar`, `Emoo`, `Nbrn`, `Npbm`, `bspd`, `ckng` …) есть во всех трёх местах.

---

## P1 — что нужно именно под Forsaken Kingdom

### 4. Поддержка Definitive Edition

- В `*skin.txt` появились ключи `Art:de` (360 штук) вместе с `Art:hd` и `Art:sd`. Есть и `file:de`, `portrait:de`, `modelScale:de` и т.п.
- Файлы лежат в `war3.w3mod:_de.w3mod:` (например, `replaceabletextures\commandbuttons\btnheroarchmage.dds`, 43832 байта).
- DE — **отдельный третий набор иконок**: MD5 у SD, HD и DE различаются (`btnheroarchmage`, `btnfootman`, `btndragonhawk`, `btnpriest`, `btnherodeathknight`). Визуально DE — перерисованные классические иконки в высоком разрешении, HD — иконки Reforged.
- Иногда у DE другой исходный арт, например `[hdhw] Art:de=BTNDragonHawk.blp`, тогда как `Art:hd=BTNDragonHawkRiderV1.blp`.

Что сделать:
- `extract_icons.py`: третий проход, `Art:de` → `Art` → источник `skinnableID`, чтение из `_de.w3mod` с откатом на SD, вывод в `icons/de/` (128px, как HD).
- Клиент: виды `de-1v1-overview`, `de-teams-overview` и т.п., `iconRoot: 'icons/de/'`. Решить, какая тема UI-ассетов им подходит (camo или camohd).
- Для HD-набора: если HD-иконки нет (как у Paladin), брать DE, иначе SD. Сейчас в этом случае скрипт берёт SD-путь и ищет его в `_hd.w3mod`, где файла нет.

### 5. Forsaken Paladin в клиенте

- Способности `AHcr`, `ANcp`, `AHpa`, `AHcl` проходят фильтр `^A[HOEUN]` в [Hero.js](../client/common/components/Hero.js) — тут всё в порядке.
- На HD-видах иконки героя и способностей будут битыми до исправления пункта 4.
- Рекомендация: заменить фильтр (регулярка плюс чёрный список ID) на поле `is_hero_ability`, которое уже есть в `ObserverPlayerHeroAbility`. Новые способности предметов с префиксами AH/AN тогда не попадут в список способностей героя. Сначала проверить через пробник, что поле заполняется корректно.

### 6. Нет запасной иконки для неизвестных ID

[Icon.js](../client/common/components/Icon.js) просто строит `${iconRoot}${id}.jpg` без `onerror`. Любой новый или отсутствующий ID — битая картинка.

Что сделать: `onerror` → запасная иконка (SD-версия или нейтральная заглушка).

Контекст: в установленной 3.0.0 у 327 предметов кампании FK (ID на `e…`, многие класса `Equipment`) стоит `pickRandom=1`. В патчноутах 3.0.1 сказано, что это исправляют (`pickRandom=0`). Выпадают ли они на практике в мили, не проверялось.

---

## P2 — менее срочное

7. **Тема Forsaken для панелей ресурсов.** В игре появились тема UI Forsaken и HUD Forsaken. В клиенте фоны панелей есть только для human/orc/nightelf/undead (`camo*/assets/ui/*-resource-panel.png`), `hudType` берётся из `players[0].race`. Можно добавить `hudType: "forsaken"` с ассетами из игры. По желанию.
8. **Баг: 24-й слот не проверяется.** В [game.py](../war3observer/game.py) `_find_players` перебирает `range(0, 23)`, то есть 23 слота. Комментарий говорит о 24, а `ObserverFile` в war3structs описывает 28 слотов.
9. **Сборка клиента (не запускалась, известная несовместимость).** Установлены Node v24.14.0 и npm 11.17.0. `node-sass ^4.11` не собирается на современном Node (нет готовых бинарников, нужен Python 2 и node-gyp). `webpack ^4` на Node ≥17 падает с `ERR_OSSL_EVP_UNSUPPORTED` (md4). Нужна миграция на `sass` (dart-sass) и webpack 5, либо как минимум `NODE_OPTIONS=--openssl-legacy-provider`. `tools/build.sh` рассчитан на cygwin и pyinstaller — проверить на Python 3.14.
10. **Расширенный инвентарь и экипировка.** В структуре API инвентарь ограничен 6 слотами (`Padded(6 * ...)`). Слоты экипировки и сумки из FK (natives `UnitExtendedInventorySize`, `UnitItemInEquipmentSlot`, …) через observer API, скорее всего, не видны. Это важно только для кастомок и кампаний.
11. **Патч 3.0.1.** Вышел 8 октября и был откачен, повторный релиз объявлен на 19 октября. Меняются баланс Paladin и клавиша вызова F→Y, у предметов FK — `pickRandom=0`. Новых ID не видно, но после установки нужно заново прогнать `extract_icons.py` и пробник.

## Что менять не нужно

- Перечисление рас и лимит игроков (24).
- Фильтр способностей для Paladin (проходит).
- Формула опыта героя в `getHeroLevelProgress`: изменений в мили не заявлено, но глубоко не проверялось.

## Предлагаемый порядок работ

1. Запустить `tools/probe_observer_api.py` в реплее на 3.0 и понять, жив ли API и совпадает ли разметка.
2. P0.1: перевести сервер на современные asyncio и websockets, закрепить зависимости.
3. P0.2: `OpenFileMapping` вместо `mmap(-1, …)`, проверка `version`, понятная ошибка; исправление `range(0, 23)`.
4. P0.3 и P1.4: устойчивый `extract_icons.py` (ошибка в данных, try/except по файлам, набор DE, откат HD → DE → SD).
5. P1.5–6: виды `de-*`, запасная иконка в `Icon.js`, фильтр через `is_hero_ability`.
6. P2: тема Forsaken, тулчейн клиента.

## Источники

- [Blizzard — Forsaken Kingdom Deep Dive Recap](https://news.blizzard.com/en-us/article/24298590/warcraft-iii-reforged-forsaken-kingdom-deep-dive-recap)
- [Blizzard Forums — Forsaken Kingdom Patch Notes](https://us.forums.blizzard.com/en/warcraft3/t/warcraft-iii-reforged-forsaken-kingdom-patch-notes/38400)
- [Liquipedia — Patch 3.0.1](https://liquipedia.net/warcraft/Patch_3.0.1)
- [Wikipedia — Warcraft III Reforged: Forsaken Kingdom](https://en.wikipedia.org/wiki/Warcraft_III_Reforged:_Forsaken_Kingdom)
- [Icy Veins — перенос 3.0.1](https://icy-veins.com/blizzard/news/blizzard-delays-warcraft-3s-visual-overhaul-after-backlash-over-campaign-progress)
- [Blizzard Forums — Patch 3.0.0 suggestions](https://us.forums.blizzard.com/en/warcraft3/t/patch-300-suggestions/37928)
- [war3structs](https://github.com/sides/war3structs) — описание структур observer API (`war3structs/observer.py`)
