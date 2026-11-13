# Подготовка offline-подложки карты

Скрипты этого каталога один раз готовят локальное изображение карты пилотной зоны
Владивостока для Leaflet `L.imageOverlay` и его manifest. Приложение во время работы
карту не скачивает и к внешним tile- и геосервисам не обращается: оно использует только
готовые файлы `frontend/public/maps/vladivostok-pilot.png` и
`frontend/public/maps/vladivostok-pilot.manifest.json` (URL `/maps/vladivostok-pilot.png`).

* `extract_region.py` — извлекает из локальной PBF-выгрузки OSM слои рендера
  (coastline, водоёмы, зелень, здания, дороги, реки, железные дороги, подписи мест и бухт)
  в промежуточный `region.json`;
* `render_map.py` — рисует PNG и пишет manifest с bounds, проекцией, источником, лицензией
  и командами воспроизведения.

Промежуточный `map-preparation/region.json`, PBF-файлы и корневой `output/` в Git не
попадают (`.gitignore`). Перенос готовых файлов в `frontend/public/maps/` — отдельный шаг
после проверки результата.

## Источник и лицензия

* Данные: OpenStreetMap, региональная выгрузка Дальневосточного федерального округа
  (по имени файла — выгрузка Geofabrik `far-eastern-fed-district-<YYMMDD>.osm.pbf`).
  Точное имя файла, его sha256 и размер записываются в manifest в поле `source`;
  путь к файлу на машине подготовки не сохраняется.
* Лицензия данных: Open Database License 1.0 (`ODbL-1.0`,
  https://opendatacommons.org/licenses/odbl/1-0/). Изображение — производная работа
  по данным OSM.
* Attribution, обязательная при показе карты: `© OpenStreetMap contributors`.
  Значение берётся из поля `attribution` manifest.

## Рамка, проекция и размеры

* Bbox извлечения (WGS84, `west south east north`): `131.848 43.0835 132.0715 43.2954`.
  Он должен с запасом покрывать рамку рендера; иначе `render_map.py` завершится ошибкой.
* Рамка рендера: крайние координаты 20 домов из
  `frontend/src/features/dossier/pilotHouses.ts` плюс 1500 м EPSG:3857 с каждой стороны.
* Проекция: EPSG:3857 (сферический Web Mercator, R = 6378137 м) — штатная CRS Leaflet,
  поэтому `imageOverlay` линейно растягивает изображение между углами bounds без искажений.
* Ширина — 2048 px; высота — `round(2048 * projectedHeight / projectedWidth)`. Чтобы пиксель
  был квадратным в проекции, рамка по y симметрично подгоняется к целой высоте (менее
  0,5 px). Фактические `bounds` (WGS84 полной точности), `projected_bounds` (метры
  EPSG:3857), `height` и `image_sha256` — только в manifest.

Ограничения проекции:

* метры EPSG:3857 на широте Владивостока длиннее наземных примерно в `1/cos(широты)` раз;
  наземный масштаб пикселя указан в `render_notes.ground_meters_per_pixel_at_center`;
* изображение одного масштаба: при приближении в Leaflet детали не добавляются, растр
  увеличивается;
* bounds в WGS84 и `projected_bounds` взаимно согласованы формулами сферического
  Mercator; другая CRS или эллипсоидальная проекция сместит точки.

## Воспроизведение

Из корня репозитория, Python 3.13, отдельное окружение подготовки карты (каталог
`.venv` игнорируется Git). Плейсхолдеры: `<PBF>` — путь к PBF-выгрузке, `<FONT_REGULAR>` и
`<FONT_BOLD>` — TTF-шрифты с кириллицей.

```powershell
py -3.13 -m venv map-preparation\.venv
map-preparation\.venv\Scripts\python.exe -m pip install -r requirements-map.txt
$env:PYTHONPATH = (Get-Location).Path
map-preparation\.venv\Scripts\python.exe map-preparation\extract_region.py <PBF> 131.848 43.0835 132.0715 43.2954 map-preparation\region.json
map-preparation\.venv\Scripts\python.exe map-preparation\render_map.py map-preparation\region.json frontend\src\features\dossier\pilotHouses.ts <PBF> output\maps\vladivostok-pilot.png output\maps\vladivostok-pilot.manifest.json --font <FONT_REGULAR> --font-bold <FONT_BOLD>
```

`PYTHONPATH` с корнем репозитория обязателен: скрипты импортируют `core.logging`
(только stdlib, дополнительных пакетов в окружение карты не требуется). Каталог
`map-preparation` не является Python-пакетом (дефис в имени), поэтому запуск через
`-m` невозможен, а правка `sys.path` внутри скриптов не используется. Без переменной
запуск завершается `ModuleNotFoundError: No module named 'core'`. Поле `commands`
manifest эту переменную не перечисляет.

Каталог `output\maps` нужно создать заранее. Без `--font` / `--font-bold` используются
`arial.ttf` и `arialbd.ttf` из `C:\Windows\Fonts`; при отсутствии файла скрипт
завершается с понятной ошибкой. Шрифты в репозиторий не входят: имя файла и sha256
каждого записаны в `tools.fonts` manifest. Побайтно тот же PNG получается только при тех
же PBF, версиях из `requirements-map.txt` и шрифтах с теми же sha256; manifest не содержит
времени запуска и абсолютных путей.

`pip install` требует сети только на этапе подготовки; извлечение и рендер работают
локально.

## Журнал

Оба скрипта пишут маркированные события через `core/logging.py` (сервис `map`) в
файл `logs\map\execution.log` от корня репозитория (каталог `logs/` вне Git) и
дублируют их в stdout. Путь, уровень и дублирование меняются переменными
`DOMDOSSE_LOG_FILE_PATH`, `DOMDOSSE_LOG_LEVEL` и `DOMDOSSE_LOG_STDOUT`. В событиях только
имена файлов, bbox, счётчики, размеры и sha256, без абсолютных путей.

| Маркер | Когда | Основные поля |
|---|---|---|
| `MAP_EXTRACT_STARTED` | начало извлечения | `pbf_name`, `bbox`, `margin_deg` |
| `MAP_EXTRACT_NODES_COMPLETED` | конец прохода по нодам | `nodes_kept`, `labels` |
| `MAP_EXTRACT_COMPLETED` | `region.json` записан | `output_name`, счётчики слоёв |
| `MAP_EXTRACT_FAILED` | отказ извлечения | `reason`: `invalid_arguments`, `pbf_not_found`, `pbf_read_failed`, `output_write_failed` |
| `MAP_RENDER_STARTED` | начало рендера | `region_name`, `houses_name`, `pbf_name` |
| `MAP_RENDER_COMPLETED` | PNG и manifest записаны | `width`, `height`, `image_sha256`, `manifest_sha256`, `bounds`, `coastline`, `drawn` |
| `MAP_RENDER_FAILED` | отказ рендера | `reason`: `invalid_arguments`, `font_not_found`, `pbf_not_found`, `region_read_failed`, `houses_read_failed`, `invalid_house_catalog`, `frame_outside_region`, `output_write_failed`, `render_failed` |

После события отказа скрипт завершается ненулевым кодом: ошибка разбора аргументов
`render_map.py` — кодом 2 argparse, прочие ожидаемые отказы — кодом 1 с текстом причины
в stderr. Причины `pbf_read_failed`, `output_write_failed` извлечения и `render_failed`
рендера пробрасывают исходное исключение с traceback; событие содержит `error_type`.

## Известные приближения

Полный список — в поле `known_approximations` manifest. Главное:

* учитываются только OSM way; мультиполигоны (relations) зданий, водоёмов, лесов и парков
  не отрисованы, поэтому часть лесных массивов выглядит пустой сушей;
* суша и вода определяются направлением coastline (по соглашению OSM суша слева от линии),
  грани без береговой линии считаются сушей, если в них нет точки бухты;
* дороги нарисованы картографической шириной по классу, а не в масштабе; подписей улиц не
  больше одной на имя и только без пересечений;
* координаты домов в каталоге приближённы (центроид здания OSM или данные владельца).
