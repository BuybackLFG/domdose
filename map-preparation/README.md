# Подготовка offline-подложки карты

Скрипты этого каталога один раз готовят локальные изображения карты пилотной зоны
Владивостока для Leaflet `L.imageOverlay` и их общий manifest. Приложение во время работы
карту не скачивает и к внешним tile- и геосервисам не обращается: оно использует только
готовые файлы из `frontend/public/maps/`:

* `vladivostok-pilot.png` — обзорный уровень (URL `/maps/vladivostok-pilot.png`);
* `vladivostok-pilot-detail.png` — детальный уровень того же кадра
  (URL `/maps/vladivostok-pilot-detail.png`);
* `vladivostok-pilot.manifest.json` — bounds, размеры, sha256, зумы переключения,
  источник, лицензия и команды воспроизведения.

Скрипты:

* `extract_region.py` — один проход `osmium.FileProcessor` по локальной PBF-выгрузке OSM
  с индексом локаций нод и сборкой площадей: линии (coastline, дороги, водотоки, железные
  дороги) из way; площади (здания, леса, кустарник, луга, парки, спортплощадки, кладбища,
  пески, скалы, болота, водоёмы, landuse, районы `admin_level=9`, острова) из замкнутых way
  и мультиполигонов с внутренними кольцами; подписи мест и бухт из нод. Результат —
  промежуточный `region.json` (формат 2);
* `render_map.py` — строит рамку, рисует оба уровня, квантует PNG в палитру и пишет manifest.

Промежуточный `map-preparation/region.json`, PBF-файлы и корневой `output/` в Git не
попадают (`.gitignore`). Перенос готовых файлов в `frontend/public/maps/` — отдельный шаг
после проверки результата.

## Источник и лицензия

* Данные: OpenStreetMap, региональная выгрузка Дальневосточного федерального округа
  (по имени файла — выгрузка Geofabrik `far-eastern-fed-district-<YYMMDD>.osm.pbf`).
  Точное имя файла, его sha256 и размер записываются в manifest в поле `source`;
  путь к файлу на машине подготовки не сохраняется.
* Лицензия данных: Open Database License 1.0 (`ODbL-1.0`,
  https://opendatacommons.org/licenses/odbl/1-0/). Изображения — производная работа
  по данным OSM.
* Attribution, обязательная при показе карты: `© OpenStreetMap contributors`.
  Значение берётся из поля `attribution` manifest.

## Рамка, проекция, уровни и зумы

* Рамка: охват 20 домов из `frontend/src/features/dossier/pilotHouses.ts` в EPSG:3857 плюс
  1500 м с каждой стороны, затем симметрично расширенный вокруг центра до соотношения
  ширина:высота ровно 2:1 (под широкий контейнер карты).
* Bbox извлечения (WGS84, `west south east north`): `131.63 43.05 132.29 43.33`. Он должен
  с запасом покрывать рамку; иначе `render_map.py` завершится отказом `frame_outside_region`.
* Проекция: EPSG:3857 (сферический Web Mercator, R = 6378137 м) — штатная CRS Leaflet,
  поэтому `imageOverlay` линейно растягивает изображение между углами bounds без искажений.
* Уровни одного кадра (одинаковые bounds):

  | Уровень | Размер | Назначение |
  |---|---|---|
  | обзорный | 2048×1024 | весь кадр на экране шириной примерно 960–1900 px: районы, бухты, места, магистрали, главные улицы; застройка — лёгкая текстура |
  | детальный | 6144×3072 | приближение: подписи улиц по кривой, здания с контуром, второстепенные дороги и дорожки |

* Зумы: `z = log2(156543.03392 · cos(φ_center) / наземные_метры_на_пиксель)`, что равно
  `log2(156543.03392 / метры_EPSG:3857_на_пиксель)`. `detail.min_zoom` — первый целый зум,
  на котором обзорный уровень растянут более чем в 1,3 раза; `max_zoom` — целая часть
  `(зум детального уровня + 1)`. Значения и дробные зумы уровней — в manifest
  (`detail.min_zoom`, `max_zoom`, `render_notes.levels`).
* Фактические `bounds` (WGS84 полной точности), `projected_bounds` (метры EPSG:3857),
  размеры и `image_sha256` обоих уровней — только в manifest.

Ограничения проекции:

* метры EPSG:3857 на широте Владивостока длиннее наземных примерно в `1/cos(широты)` раз;
  наземный масштаб пикселя указан в `render_notes.levels.*.ground_meters_per_pixel_at_center`;
* растры фиксированного масштаба: между целыми зумами Leaflet масштабирует изображение;
* bounds в WGS84 и `projected_bounds` взаимно согласованы формулами сферического
  Mercator; другая CRS или эллипсоидальная проекция сместит точки.

## Рендер

* Суша и вода — по направлению coastline (соглашение OSM: суша слева); грань без
  береговой линии считается водой, только если в ней есть точка бухты.
* Порядок слоёв: суша, растительность и landuse (крупные площади первыми), повторная
  заливка моря, водоёмы, водотоки, здания, железные дороги, дороги, подписи.
* Подписи: районы (в части района с наибольшим числом зданий), острова, бухты, места,
  затем улицы по классу дороги. Улицы подписываются по кривой: way одного имени
  сцепляются в штрихи с наименьшим поворотом, глифы ставятся по касательной; подписи
  не пересекаются.
* Суперсэмплинг 2× и сглаживание при уменьшении; затем палитра 256 цветов без дизеринга:
  фиксированные цвета заливок и median cut, каждый цвет — в ближайший цвет палитры, так
  что цвета заливок сохраняются точно. Каждый PNG не больше 8 000 000 байт, иначе отказ
  `png_too_large`.
* Перед рисованием проверяется, что все 20 домов внутри рамки и на суше (не в море и не в
  водоёме); иначе отказ `house_outside_frame` или `house_in_water`.

## Воспроизведение

Из корня репозитория, Python 3.13, отдельное окружение подготовки карты (каталог
`.venv` игнорируется Git). Плейсхолдеры: `<PBF>` — путь к PBF-выгрузке, `<FONT_REGULAR>` и
`<FONT_BOLD>` — TTF-шрифты с кириллицей.

```powershell
py -3.13 -m venv map-preparation\.venv
map-preparation\.venv\Scripts\python.exe -m pip install -r requirements-map.txt
$env:PYTHONPATH = (Get-Location).Path
map-preparation\.venv\Scripts\python.exe map-preparation\extract_region.py <PBF> 131.63 43.05 132.29 43.33 map-preparation\region.json
map-preparation\.venv\Scripts\python.exe map-preparation\render_map.py map-preparation\region.json frontend\src\features\dossier\pilotHouses.ts <PBF> output\maps\vladivostok-pilot.png output\maps\vladivostok-pilot-detail.png output\maps\vladivostok-pilot.manifest.json --font <FONT_REGULAR> --font-bold <FONT_BOLD>
```

`PYTHONPATH` с корнем репозитория обязателен: скрипты импортируют `core.logging`
(только stdlib, дополнительных пакетов в окружение карты не требуется). Каталог
`map-preparation` не является Python-пакетом (дефис в имени), поэтому запуск через
`-m` невозможен, а правка `sys.path` внутри скриптов не используется. Без переменной
запуск завершается `ModuleNotFoundError: No module named 'core'`. Шаг с переменной
перечислен и в поле `commands` manifest.

Извлечение держит индекс локаций всех нод выгрузки в памяти (`flex_mem`) и собирает
мультиполигоны, поэтому требует запаса оперативной памяти порядка гигабайт; фактические
время и размер индекса пишутся в событие `MAP_EXTRACT_COMPLETED`.

Каталог `output\maps` нужно создать заранее. Без `--font` / `--font-bold` используются
`arial.ttf` и `arialbd.ttf` из `C:\Windows\Fonts`; при отсутствии файла скрипт
завершается с понятной ошибкой. Шрифты в репозиторий не входят: имя файла и sha256
каждого записаны в `tools.fonts` manifest. Побайтно те же PNG получаются только при тех
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
| `MAP_EXTRACT_STARTED` | начало извлечения | `pbf_name`, `bbox`, `margin_deg`, `location_storage` |
| `MAP_EXTRACT_COMPLETED` | `region.json` записан | `output_name`, `elapsed_s`, `location_index_bytes`, `invalid_locations`, счётчики линий, `areas` по слоям, `labels` |
| `MAP_EXTRACT_FAILED` | отказ извлечения | `reason`: `invalid_arguments`, `pbf_not_found`, `pbf_read_failed`, `output_write_failed` |
| `MAP_RENDER_STARTED` | начало рендера | `region_name`, `houses_name`, `pbf_name` |
| `MAP_RENDER_LEVEL_COMPLETED` | PNG уровня записан | `level`, `png_name`, `width`, `height`, `png_bytes`, `image_sha256`, `drawn` |
| `MAP_RENDER_COMPLETED` | оба PNG и manifest записаны | `manifest_sha256`, `image_sha256`, `detail_image_sha256`, `bounds`, `zooms`, `coastline`, `houses_on_land` |
| `MAP_RENDER_FAILED` | отказ рендера | `reason`: `invalid_arguments`, `font_not_found`, `pbf_not_found`, `region_read_failed`, `region_format_unsupported`, `houses_read_failed`, `invalid_house_catalog`, `frame_outside_region`, `zoom_levels_invalid`, `house_outside_frame`, `house_in_water`, `png_too_large`, `output_write_failed`, `render_failed` |

После события отказа скрипт завершается ненулевым кодом: ошибка разбора аргументов
`render_map.py` — кодом 2 argparse, прочие ожидаемые отказы — кодом 1 с текстом причины
в stderr. Причины `pbf_read_failed`, `output_write_failed` извлечения и `render_failed`
рендера пробрасывают исходное исключение с traceback; событие содержит `error_type`.

## Известные приближения

Полный список — в поле `known_approximations` manifest. Главное:

* мультиполигоны, члены которых обрезаны границей региональной выгрузки, не собираются;
* море повторно заливается поверх растительности по coastline, поэтому отмели и объекты за
  линией берега не видны;
* растительность и landuse обобщены до нескольких цветовых классов;
* дороги нарисованы картографической шириной по классу, а не в масштабе; часть имён улиц
  не подписана, потому что подписи не пересекаются;
* координаты домов в каталоге приближённы (центроид здания OSM или данные владельца).
