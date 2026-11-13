# Уведомления ДГК по Владивостоку

В [снимке](dgk-vladivostok-2026.json) 17 записей об ограничениях горячего
водоснабжения. Публикации сверены 13 ноября 2026 года по времени Владивостока
(UTC+10). Поле `date` содержит местную дату начала. Время окончания в
`summary` — заявленный срок. Фактическое восстановление подачи воды публикации
не подтверждают. `severity: 1` — оценка ДомДосье для планового уведомления о
ремонте.

- Августовские окна на Шилкинской и Светланской подтверждаются обеими публикациями.
  [Публикация от 11 августа](https://dvgk.ru/press/news/primorskie-teplovye-seti-provodyat-raboty-na-teplotrassakh-v-khode-podgotovki-k-ozp-vo-vladivostoke--54727/),
  [публикация от 12 августа](https://dvgk.ru/press/news/vtoroy-etap-gidravlicheskikh-ispytaniy-prodlyen-dlya-nekotorykh-potrebiteley-vo-vladivostoke-adresa/).
- Для Сочинской, 17, Можайской, 20, 22 и 24, и обоих корпусов Басаргина, 6Б
  в снимке по одной записи на августовское окно с продлённым сроком до 31 августа.
  На тех же адресах опубликовано отдельное окно с 5 по 18 сентября. В объявлениях
  ДГК корпуса Басаргина обозначены как `6б/1` и `6б/2`.
  [Продление августовских работ](https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/),
  [сентябрьское окно](https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/).
- Период с 29 сентября по 2 октября указан в отдельном
  [уведомлении ДГК от 30 сентября](https://dvgk.ru/press/news/primorskie-teplovye-seti-prodolzhayut-podgotovku-teplotrass-k-zime-adresa/).

## Проверка офлайн

Сохраните во временной папке `dgk-demo-houses.json` с тестовыми идентификаторами.

```json
[
  {"id": "demo-shilkinskaya-11", "address": "Шилкинская, 11"},
  {"id": "demo-svetlanskaya-143", "address": "Светланская, 143"},
  {"id": "demo-svetlanskaya-155", "address": "Светланская, 155"},
  {"id": "demo-svetlanskaya-173", "address": "Светланская, 173"},
  {"id": "demo-basargina-6b-1", "address": "Басаргина, 6Б корп. 1"},
  {"id": "demo-basargina-6b-2", "address": "Басаргина, 6Б корп. 2"},
  {"id": "demo-mozhayskaya-20", "address": "Можайская, 20"},
  {"id": "demo-mozhayskaya-22", "address": "Можайская, 22"},
  {"id": "demo-mozhayskaya-24", "address": "Можайская, 24"},
  {"id": "demo-sochinskaya-17", "address": "Сочинская, 17"}
]
```

Из каталога `backend` запустите команду, подставив путь к временной папке.
Импорт создаст в ней `dgk-demo-events.json` с 17 событиями для 10 домов.

```sh
uv run python -m app.ingest.official ../data/official/dgk-vladivostok-2026.json "/path/to/temp/dgk-demo-events.json" --houses "/path/to/temp/dgk-demo-houses.json"
```

Для импорта с каноническим каталогом передайте в `--houses` JSON-массив домов
с уникальными `id` и полем `address`. Укажите `district`, если район известен.
Если район пропущен или равен `null`, событие сохраняется без района.
При необходимости приведите адреса в копии снимка к формату каталога после
ручной сверки. Импорт сравнивает строки
целиком, учитывая эквивалентность регистра, пробелов и «ё»/«е». Префиксы
города и улицы, номер и корпус учитываются при сравнении. При отсутствии
совпадения, неоднозначном адресе или повторяющемся `id` импорт завершится
ошибкой и сохранит прежний выход. Явно указанные `house_id` и `district`
должны подтверждаться каталогом. Если район явно указан только в снимке,
импорт также завершится ошибкой.
Для записей с `house_id` или `district` без `address` каталог необязателен.
