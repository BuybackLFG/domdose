# Передача сессии: фундамент вычислительной библиотеки

Исторический снимок на 13 ноября 2026 года. Раздел «Реальный датасет» и допуск 1e-9 в нём описывают состояние до решения владельца о допуске 0.005 h; актуальное состояние — `LIBRARY.md` и durable-журнал сессии.

Состояние на 13 ноября 2026 года, Asia/Vladivostok (+10). Файл создан по прямому запросу владельца. Durable-журнал исходной сессии остаётся первичным источником точных событий.

## Стадия и границы

Реализованы только настройки процесса, явное логирование и контракты датасета 1.0. Утверждённый пакет рейтинга ещё НЕ реализован: подготовлены его спецификация и независимые синтетические тесты. FastAPI — смежный стек и будущий тонкий адаптер, не зависимость ядра. API/БД/UI и существующее приложение этим срезом не изменены.

Владелец утвердил Python, приближённый метод максимума и расчётные правила в [SPEC.md](<SPEC.md>). Авторизация на публикацию настоящего датасета в публичную Git-ветку дана отдельно прямым указанием «датасет тоже»; среда, кэши и настройки DSH не публикуются.

## Где находится работа

- Основной локальный каталог: `C:\Progg\Development\ДомДосье`. Его ветка master была без коммитов; здесь разработаны и проверены пакеты. Не выдавать этот каталог за checkout актуального main.
- Публикационный Git-worktree: `.local/publication`, ветка `dd-19-rating-foundation`, база `origin/main` = `6066b5f0ebab7d1f4dd651caf082f52d7d4a62a0`. Существующие backend/frontend сохранены.
- Origin: https://github.com/BuybackLFG/domdose.git (public).
- Первый запушенный срез: `00d762ce2297b9ba9662ceb22624c48467dd76e8`.
- Уточнение документации о публикации датасета: `86cdf0a` (запушено).
- Этот файл, маркер типов и последующая гигиена тестов публикуются follow-up-коммитом. Его HEAD проверять `git -C .local/publication log -1`, не угадывать хеш по этому документу.
- PR не создавался, main не менялась, force-push/amend не применялись.

Для следующей сессии предпочтительно открыть публикационный worktree: он имеет историю приложения и действующий AGENTS.md. Учесть, что его окружение Python пока не установлено отдельно; проверка копии делалась локальным Python основного каталога с PYTHONPATH на worktree.

## Реализованные интерфейсы

- [core/config.py](<core/config.py>): Settings(BaseSettings), frozen, только log_level и log_file; kwargs > environment > UTF-8 dotenv > defaults. get_settings кэширует первый успешный экземпляр. SettingsRefused хранит класс/поле/код/число внеполевых ошибок без значений и исходной цепочки.
- [core/logging.py](<core/logging.py>): setup_logging/get_logger, отдельный namespace domdose; handlers только при явном вызове, повторная настройка не дублирует свои handlers. Root logger и глобальная фабрика записей не изменяются.
- [contract/dataset.py](<contract/dataset.py>): read_dataset(Mapping | str | bytes) -> Dataset; schema-first Draft 2020-12 с format checker, затем DTO и semantic validation. dataset_schema возвращает свежую копию.
- [contract/models.py](<contract/models.py>): frozen Pydantic v2 модели и tuple-коллекции, required nullable поля, extra forbid. Null не превращается в ноль. Целые JSON float в integer-полях допустимы по исходной схеме, bool — нет.
- [contract/errors.py](<contract/errors.py>): ContractIssue(code,path), ContractRefused(issues); неизвестные ключи заменяются безопасным $extra.
- [contract/dataset.schema.json](<contract/dataset.schema.json>): механическая копия исходной схемы; SHA256 `fb49d6b9d9388dc8d60fdd316f9e38b36cd565226c69fcdca598c7f6a06d6e9a`.

Проверяются ID/ссылки/дубли, обязательный источник события, период/+10:00, порядок концов, конечные неотрицательные длительности/числа, city total > 0 если известен, affected <= total, actual/planned/unknown basis. Квоты выборки и достоверность источников валидатор не удостоверяет.

Dataset сам по себе не входит в read_dataset: будущий rating при получении DTO обязан повторно проверить `model_dump(mode="json", by_alias=True)`, а не обходить semantics через готовый объект. Обычный model_dump с Python date и внутренними aliases не является JSON-входом.

## Утверждённый рейтинг, который предстоит реализовать

Метод `rating_observed_exposure_proxy_v1`; вход CalculationRequest(target_house_ids,end_exclusive,policy_version). Никаких скрытых now, окружения, файлов, логов или сети в ядре.

- W=[end-30 days,end); пересечение событий, частота один раз, часы/максимум обрезаны.
- Отопление пересекается с сезоном; вне сезона not_applicable, неизвестный сезон unavailable; без экстраполяции и автоматической переклассификации.
- w emergency=1/planned=.4/unknown unavailable. MVP mass=scope district/city, multiplier .5 один раз при mass OR force_majeure.
- Дом F=Σw,H=Σw*d,M=max(w*d).
- Город B_F=Σn*w/N,B_H=Σn*w*d/N, N — весь городской фонд, включая нулевые дома.
- Только maximum baseline приближённый: Q_M=Σn*w*d/Σn, средняя weighted длительность house-event exposure. Это НЕ среднее per-house maximum, не включает нулевые дома, знак ошибки не гарантирован.
- Штраф piecewise linear в log2 r через (1,0),(2,.33),(4,.67),(8,1). Ratio0/0=None, penalty0; positive/0 unavailable/inconsistent.
- Rcategory=1-(.4pF+.4pH+.2pM). Веса electricity .30/cold .25/heating .25/hot .20, central-only, перенормировка только неприменимых, cap=mincategory+.25. Missing eligible score или unknown service => total None.
- Null duration оставляет частоту, но не часы/максимум; неизвестное пересечение блокирует и частоту. Range/street => unavailable, не отсутствие событий.
- Report всегда observed/approximate, не certified. Source spans — декларации дат, не доказательство покрытия. Полные поля/коды и ordering описаны в SPEC и frozen тестах.

## Тесты и доказательства

Исходный прогон до реализации записан в durable-журнале: collected15/2 collection errors missing core/contract; architecture+instrument subset3failed12passed. Это red отсутствующей реализации, НЕ воспроизведение математического дефекта. Git-коммит для этого red не создавался.

После реализации исполнитель, главная сессия и независимый reviewer подтвердили 148 passed по одному и тому же foundation-набору. Rating instrument — 15 passed. Финальный прогон главной после нейтрального форматирования: **163 passed in 1.16s**, `ruff check core contract tests scripts/inspect_dataset.py` — All checks passed.

```powershell
$env:TEMP = Join-Path (Get-Location) '.local/tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_dataset.py tests/test_config_logging.py tests/test_architecture.py tests/test_instrument.py tests/test_rating_instrument.py --basetemp=.local/tmp/fresh-run -q
.\.venv\Scripts\python.exe -m ruff check core contract tests scripts/inspect_dataset.py
```

Существующий basetemp повторно не использовать без проверки: отдельные confined дети оставили недоступные временные каталоги. Не включать tmp-каталоги в Git; добавлять исходники явно.

Rating rules/contract: 45+37=82 synthetic cases, пока collection error `No module named rating`. Calibration15 — test-only doubles, НЕ production mutation coverage. Полный pytest всего дерева НЕ зелёный. Не удалять/skip pending тесты ради зелёного результата.

Нейтральная гигиена 11 файлов доказана AST-equivalence except import order; raw исходная JSON schema в тестовом literal неизменна. После гигиены сторонний confined-прогон дал125passed23setup PermissionErrors, а главная в full access повторила163passed. Это разница окружения, не ослабление asserts.

Независимое review config/contract: APPROVED, production blockers none. Reviewer подтвердил safe errors, frozen structures, отсутствие import I/O, strict real-data отказ. Остаточные сторожа для отдельного следующего тестового среза: duplicate JSON keys/nonfinite tokens, format-only datetime, exact tolerance boundary, logging destination switch, failed cache, contract import side effects. Эти пути вручную проверены, но текущие148 не все держат регрессию. Environment case-insensitive: lowercase env имена также принимаются; не обещать case-sensitive uppercase-only.

Полная проверка приложения `bash ./scripts/check.sh` попыталась запуститься в worktree, но завершилась до выполнения: WSL execvpe(/bin/bash) No such file. Backend/frontend/types/manual smoke не проверены этим срезом. Не переводить задачи в Done, не создавать PR с заявлением full-green. Root pyproject и корневые tests пока не включены в существующую backend/frontend CI: отдельный интеграционный шаг с владельцем.

## Локальная среда

Python3.12.14, Pydantic2.14.3, pydantic-settings2.16.2,jsonschema4.26,pytest9.2,ruff0.17.5. [requirements-dev.lock](<requirements-dev.lock>) — фиксированные проверенные версии constraints, не hash lock. [LIBRARY.md](<LIBRARY.md>) содержит bootstrap/check-команды.

Все зависимости `.venv`, TEMP/TMP/TMPDIR `.local/tmp`, PIP_CACHE_DIR `.local/pip-cache`. [scripts/env.ps1](<scripts/env.ps1>) unsigned и блокируется системной execution policy: не менять machine policy, использовать assignments inline. [scripts/check-library.ps1](<scripts/check-library.ps1>) — только foundation+calibration, не весь рейтинг и не app check.sh.

Sandbox workspace-write блокировал pip даже в локальных temp. Штатная диагностика Windows permissions: NOT_THIS_CLASS, changes0, nextAction stop; после явного перехода владельцем в danger-full-access установка завершилась. На момент передачи full access, prompts disabled. Никаких ручных ACL/owner правок не делали.

## Реальный датасет

Публикация по прямому разрешению: [data/datasets/communal-outages-2026.json](<data/datasets/communal-outages-2026.json>). Основной исходник был передан из внешнего временного каталога; опубликованная копия сохраняет весь журнал. После уточнения сезона SHA256 `896ddc646df2c7cc9341640e4cfdb2bafc07285acbc12200ef8baa6609ddfbe9` до возможной Git-конверсии переводов строк; Git blob bytes при необходимости проверить отдельно.

2682events,20houses,1source,74days,214exact sample links. Schema violations0. Owner сообщил heating_season_start2026-10-12 для основной части города; внесено в meta с явной оговоркой provenance/не каждый дом. Старый inspection snapshot до этого уточнения имел season null, не использовать его как актуальный факт.

Фактический read_dataset после изменения сезона: **1496 issues, все DURATION-MISMATCH и уникальные duration_hours paths**, других кодов нет. Источник округлил длительности до0.01h; расхождение max12sec против строгого tolerance1e-9h. Контракт не ослаблять без нового решения владельца. Варианты на обсуждение: разрешённая точность0.005h либо авторитет endpoints с явной политикой обработки rounded stored values; пока ничего из этого не утверждено.

N total и районные числа null; unknown kind1083/2682; unknown service16/20houses; passports/control отсутствуют. Поэтому полный score недоступен даже после решения duration. Не подставлять len(houses), не склеивать подозрительные эпизоды автоматически и не считать unknown emergency.

Числа адресов расходятся с n в1062 событиях; n0=199. Проверка не вводит n>=len(addresses). 71 tight timestamp group/360events — возможные related/duplicate episodes, НЕ доказанные дубли. 27 card numbers внутри заявленного перебора не объяснены без сетевой проверки; это неопределённость, НЕ подтверждённые потерянные отключения. 74/74дня с событиями не доказывают полноту покрытия. Source published_at100%null. Объёмный [scripts/inspect_dataset.py](<scripts/inspect_dataset.py>) диагностирует локально, не исправляет данные и не обращается к сети.

## Linear

По разрешению владельца опубликован нейтральный [контракт](https://linear.app/sotraiir/document/kontrakt-python-biblioteki-kommunalnogo-rejtinga-v1-6b081b6502ec), document ID8771fbfc-c813-4b8c-8132-3f2b8a855de7. Названия/пути других проектов в тело не вносились.

DD-19: чистая библиотека и synthetic tests отделены от real candidate integration; снят blockerDD-12, DD-18/21dependencies сохранены; In Progress. DD-12: raw schema/semantic gate отделён от последующего scoring smoke, квоты/паспорта не менялись; In Progress. DD-13: только explanatory comment, Done сохранился; DD-18 не редактировали. После push комментарии добавлены и перечитаны: DD-19 comment `9d447be8-222f-4fa0-b1ce-f0ea1fc4e794`, DD-12 comment `d17125b7-081f-4cbd-a07b-a2ced42334e7`. Оба содержат ссылку на ветку и полный commit00d762c, отсутствие PR и ограничения проверок. Все объединённые AC остались unchecked, оба статуса In Progress. Более поздний локальный прогон163passed ещё не отражён в этих комментариях.

Не менять tolerance, не закрывать комбинированные AC config+ratingDTO до реализации всех частей. DD-19 real smoke/три golden и app checks не выполнены, DD-12semantic gate не пройден.

## DSH и модели

Desktop профиль перепривязан к bundle текущего проекта; владелец явно решил оставить общий desktop, несмотря на влияние на другие workspaces. Playwright только u-frontend; его фактическая работа after full Host restart ещё не проверена. Linear connection/read проверены ранее.

В desktop/cordis.patch.yml added allowedModels gpt-tunnel/gpt-6.1-sol. Medium у модели уже объявлен. Текущая session durable policy остаётся старой: GPT delegation станет доступна в НОВОЙ top-level session, не в новых детях этой старой сессии. Не обходить allowlist. Исполнители и последние reviewer/tester работали deepseek-account/deepseek-flash, effort max. Для сложных новых ролей владелец хочет GptTunnel GPT6.1Sol medium; проверить list_subagent_models в новой сессии перед запуском.

## Следующий атомарный шаг

1. Открыть worktree/new top-level session и проверить goal/revision; resume по просьбе владельца, не начинать с чистого листа.
2. Проверить актуальный Git HEAD и Linear comments; этот checkpoint не означает завершение всей durable цели.
3. Реализовать rating public API по SPEC/frozen82 cases, исполнителем DeepSeekFlash max. Сначала не ослаблять неизвестные/n/null/season; DTODataset revalidation обязателен.
4. Повторить82rules+contract,15calibration и148foundation без сужения населения; сохранить domain failures и исправить механизм. Независимое review до сдачи.
5. Отдельно получить решение владельца по округлению durations/N/service truth/source data quality, а не подгонять синтетическую мерку под настоящий файл.
6. Согласовать backend integration/CI check.sh и FastAPI adapter отдельным срезом. До этого никаких Done/full-green.
