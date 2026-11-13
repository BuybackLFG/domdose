// ФИКСТУРЫ ДЛЯ РАЗРАБОТКИ, НЕ РЕАЛЬНЫЕ ДАННЫЕ.
//
// Пока backend отвечает 501 (B2 не реализован), экран досье разрабатывается
// против этих записей. Собрано из реальных данных репозитория:
//   - адреса, районы, год, этажность, материал — `data/shortlist.md` (DD-6);
//   - события — `data/official/*.json` (DD-8, ДГК и ВПЭС);
//   - индекс и события с префиксом `mock-` — синтетические: они нужны, чтобы
//     UI показывал все ветки (пять компонент, бейджи ai/resident), и в демо их
//     показывать нельзя.
//
// Включается флагом: `VITE_USE_MOCKS=true npm run dev`.
import type {
  ChecklistItem,
  Component,
  ComponentKey,
  Dossier,
  Event,
  Fact,
  House,
  HouseIndex,
} from '../types'
import { MOCK_SUMMARIES } from './houses'

const RETRIEVED_AT = '2026-11-13'
const RETRIEVED_TS = '2026-11-13T10:00:00+10:00'
const DISCLAIMER = 'аналитика по открытым данным, не гарантия'
/** Перечень избирательных участков: по нему сверены районы в шорт-листе. */
const DISTRICT_SOURCE = 'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf'

/** Что шорт-лист говорит о доме. Пустое поле — «нет данных», а не ноль. */
interface Passport {
  year?: number
  floors?: number
  material?: string
  urls: string[]
}

const PASSPORT: Record<string, Passport> = {
  'svetlanskaya-37': { year: 1918,
    urls: [
      'https://openaddress.ru/houses/8dcfbf63-f4b5-4ed5-b37b-1ac91cd5b9c1',
    ] },
  'fokina-8': { year: 1920,
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-admirala-fokina-1743921/8-55c21b5c/',
    ] },
  'bestuzheva-46': { year: 1946, floors: 2,
    urls: [
      'https://2gis.ru/vladivostok/geo/3519072864050169',
    ] },
  'svetlanskaya-155': { year: 1972,
    urls: [
      'https://openaddress.ru/houses/cf4ffc95-deda-4a00-be95-c21b74a9aa7b',
      'https://www.vl.ru/off/management-company/51.html',
    ] },
  'svetlanskaya-173': { year: 1969, floors: 7,
    urls: [
      'https://openaddress.ru/houses/b23f73c0-a1b6-4745-8d52-212f47cc1823',
    ] },
  'svetlanskaya-143': {
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-svetlanskaya-1a1b9f1/143-56906cda/',
      'https://t.me/primvodokanal/1640',
    ] },
  'russkaya-65a': {
    urls: [
      'https://openaddress.ru/houses/3e85cf0a-5b92-486b-bde4-8db99bb5b8fc',
    ] },
  'tukhachevskogo-44': { floors: 9,
    urls: [
      'https://mkdbase.ru/mkd/25-primorskij/g-vladivostok/ul-tuhachevskogo/690089-kraj-primorskij-g-vladivostok-ul-tuhachevskogo-d-44/',
    ] },
  'shilkinskaya-11': {
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-shilkinskaya-a3b5f08/11-156c4dcd/',
      'https://xn--11-6kc5aalbfu4b6due.xn--p1ai/prochee/kapital.rem/%D0%97%D0%B0%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%BD%D0%B8%D0%B5_100_%20%D0%A8%D0%B8%D0%BB%D0%BA%D0%B8%D0%BD%D1%81%D0%BA%D0%B0%D1%8F%2011.pdf',
    ] },
  'shoshina-17a': { floors: 9,
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-shoshina-6b1dcf6/17a-07d05289/',
      'https://www.vl.ru/off/management-company/63.html',
    ] },
  'shoshina-25a': {
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-shoshina-6b1dcf6/25a-70241905/',
    ] },
  'volkhovskaya-27': { year: 1986, floors: 9,
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-volhovskaya-d4456af/27-e1dfe038/',
    ] },
  'nevskaya-33': { floors: 10, material: 'панель',
    urls: [
      'https://prawdom.ru/dom.php?hm=nevska_33',
      'https://www.vl.ru/off/b/story/8577',
    ] },
  'sochinskaya-17': { floors: 17,
    urls: [
      'https://masterstroydv.ru/project/zhk-milya',
      'https://patrokl.info/faq/sochinskaya/sochinskaya17/',
    ] },
  'basargina-2': { year: 1939, floors: 2,
    urls: [
      'https://dompassport.ru/dom/vladivostok/basargina-2/',
    ] },
  'basargina-6b-1': { year: 2021, floors: 25,
    urls: [
      'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf',
    ] },
  'basargina-6b-2': { floors: 25,
    urls: [
      'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf',
    ] },
  'basargina-15': {
    urls: [
      'https://patrokl.info/faq/basargina/basargina15/',
    ] },
  'basargina-32': {
    urls: [
      'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf',
    ] },
  'basargina-42v': {
    urls: [
      'https://patrokl.info/faq/basargina/basargina42v/',
    ] },
  'basargina-46': { year: 2012,
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-basargina-24bfe1c/46-82e88080/',
    ] },
  'mozhayskaya-20': {
    urls: [
      'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf',
    ] },
  'mozhayskaya-22': { floors: 10, material: 'панель',
    urls: [
      'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf',
    ] },
  'mozhayskaya-24': { material: 'панель',
    urls: [
      'https://gazetav.ru/wp-content/uploads/2024/01/30.01.2024.pdf',
    ] },
  'sipyagina-28': { year: 1973, floors: 5, material: 'кирпич',
    urls: [
      'https://domscanner.ru/houses/primorskiy-kray/vladivostok/ul-sipyagina-dd2ba34/28-074ca213/',
    ] },
  'krygina-42a': { year: 2006, floors: 10, material: 'панель',
    urls: [
      'https://2gis.ru/vladivostok/geo/3519072864070890',
    ] },
  'krygina-80': {
    urls: [
      'https://mkdbase.ru/mkd/25-primorskij/g-vladivostok/ul-krygina/690065-kraj-primorskij-g-vladivostok-ul-krygina-d-80/',
    ] },
  'leonova-25': { year: 1952, floors: 3, material: 'кирпич',
    urls: [
      'https://2gis.ru/vladivostok/geo/3519072864051279',
    ] },
  'leonova-70': {
    urls: [
      'https://openaddress.ru/houses/f8c881b7-871b-4ebb-88a5-c8d16148222d',
    ] },
}

/** Официальные события: перенесены из `data/official` без изменений. */
const OFFICIAL_EVENTS: Event[] = [
  { id: "dgk-vladivostok-2026-2026-08-10-shilkinskaya-11", house_id: "shilkinskaya-11", type: "hot_water", date: "2026-08-10", severity: 1, title: "Ограничение горячего водоснабжения на Шилкинской, 11", summary: "ДГК указала для дома период ограничения горячей воды из-за ремонта теплосетей с 10 августа 2026 года, 14:15, до 13 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/vtoroy-etap-gidravlicheskikh-ispytaniy-prodlyen-dlya-nekotorykh-potrebiteley-vo-vladivostoke-adresa/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-svetlanskaya-155", house_id: "svetlanskaya-155", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения на Светланской, 155", summary: "ДГК указала для дома период ограничения горячей воды из-за ремонта теплосетей с 6 августа 2026 года, 00:00, до 14 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/vtoroy-etap-gidravlicheskikh-ispytaniy-prodlyen-dlya-nekotorykh-potrebiteley-vo-vladivostoke-adresa/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-29-shilkinskaya-11", house_id: "shilkinskaya-11", type: "hot_water", date: "2026-09-29", severity: 1, title: "Ограничение горячего водоснабжения на Шилкинской, 11", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 29 сентября 2026 года, 00:00, до 2 октября, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/primorskie-teplovye-seti-prodolzhayut-podgotovku-teplotrass-k-zime-adresa/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-svetlanskaya-143", house_id: "svetlanskaya-143", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Светланская, 143", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 14 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/vtoroy-etap-gidravlicheskikh-ispytaniy-prodlyen-dlya-nekotorykh-potrebiteley-vo-vladivostoke-adresa/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-svetlanskaya-173", house_id: "svetlanskaya-173", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Светланская, 173", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 14 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/vtoroy-etap-gidravlicheskikh-ispytaniy-prodlyen-dlya-nekotorykh-potrebiteley-vo-vladivostoke-adresa/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-basargina-6b-1", house_id: "basargina-6b-1", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Басаргина, 6Б корп. 1", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 31 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-basargina-6b-2", house_id: "basargina-6b-2", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Басаргина, 6Б корп. 2", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 31 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-mozhayskaya-20", house_id: "mozhayskaya-20", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Можайская, 20", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 31 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-mozhayskaya-22", house_id: "mozhayskaya-22", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Можайская, 22", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 31 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-mozhayskaya-24", house_id: "mozhayskaya-24", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Можайская, 24", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 31 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-08-06-sochinskaya-17", house_id: "sochinskaya-17", type: "hot_water", date: "2026-08-06", severity: 1, title: "Ограничение горячего водоснабжения — Сочинская, 17", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 6 августа 2026 года, 00:00, до 31 августа, 20:00 по местному времени.", source_url: "https://dvgk.ru/press/news/novosti-strany/teploseti-vladivostoka-gotovyat-k-zime-adresa-55346/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-05-basargina-6b-1", house_id: "basargina-6b-1", type: "hot_water", date: "2026-09-05", severity: 1, title: "Ограничение горячего водоснабжения — Басаргина, 6Б корп. 1", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 5 сентября 2026 года, 10:38, до 18 сентября, 17:00 по местному времени.", source_url: "https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-05-basargina-6b-2", house_id: "basargina-6b-2", type: "hot_water", date: "2026-09-05", severity: 1, title: "Ограничение горячего водоснабжения — Басаргина, 6Б корп. 2", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 5 сентября 2026 года, 10:38, до 18 сентября, 17:00 по местному времени.", source_url: "https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-05-mozhayskaya-20", house_id: "mozhayskaya-20", type: "hot_water", date: "2026-09-05", severity: 1, title: "Ограничение горячего водоснабжения — Можайская, 20", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 5 сентября 2026 года, 10:38, до 18 сентября, 17:00 по местному времени.", source_url: "https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-05-sochinskaya-17", house_id: "sochinskaya-17", type: "hot_water", date: "2026-09-05", severity: 1, title: "Ограничение горячего водоснабжения — Сочинская, 17", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 5 сентября 2026 года, 10:38, до 18 сентября, 17:00 по местному времени.", source_url: "https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-05-mozhayskaya-22", house_id: "mozhayskaya-22", type: "hot_water", date: "2026-09-05", severity: 1, title: "Ограничение горячего водоснабжения — Можайская, 22", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 5 сентября 2026 года, 10:38, до 18 сентября, 17:00 по местному времени.", source_url: "https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-05-mozhayskaya-24", house_id: "mozhayskaya-24", type: "hot_water", date: "2026-09-05", severity: 1, title: "Ограничение горячего водоснабжения — Можайская, 24", summary: "На время ремонта теплосетей ДГК указала ограничение горячей воды с 5 сентября 2026 года, 10:38, до 18 сентября, 17:00 по местному времени.", source_url: "https://www.dvgk.ru/press/news/teploseti-vladivostoka-prokhodyat-podgotovku-k-zime-55779/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-05-26-krygina-42a", house_id: "krygina-42a", type: "hot_water", date: "2026-05-26", severity: 1, title: "Ограничение горячего водоснабжения на Крыгина, 42А", summary: "ДГК сообщила об ограничении с 26 мая, 00:00, до 2 июня, 00:00, и о непрерывном продолжении ограничения до 26 августа по опубликованному на тот момент плану работ.", source_url: "https://www.dvgk.ru/press/news/novosti-strany/raboty-na-teplovykh-setyakh-provodyat-vo-vladivostoke-energetiki-adresa-51957/", confidence: 1, kind: 'official' },
  { id: "dgk-vladivostok-2026-2026-09-07-russkaya-65a", house_id: "russkaya-65a", type: "hot_water", date: "2026-09-07", severity: 1, title: "Уведомление об ограничении ГВС на Русской, 65А", summary: "ДГК включила дом в перечень адресов третьего этапа гидравлических испытаний с 7 по 14 сентября. Часы ограничения в адресном перечне не указаны.", source_url: "https://www.dvgk.ru/press/news/tretiy-etap-letne-osennikh-gidravlicheskikh-ispytaniy-nachalsya-vo-vladivostoke-adresa-/", confidence: 1, kind: 'official' },
  { id: "vpes-vladivostok-2026-2026-06-08-svetlanskaya-155", house_id: "svetlanskaya-155", type: "power", date: "2026-06-08", severity: 1, title: "Плановое отключение электричества на Светланской, 155", summary: "По данным АО «ВПЭС» в адресной карточке VL.ru, отключение было запланировано на 8 июня с 09:00 до 17:00 по местному времени.", source_url: "https://www.vl.ru/off/blackout/164594.html", confidence: 1, kind: 'official' },
  { id: "vpes-vladivostok-2026-2026-06-10-svetlanskaya-155", house_id: "svetlanskaya-155", type: "power", date: "2026-06-10", severity: 1, title: "Плановое отключение электричества на Светланской, 155", summary: "По данным АО «ВПЭС» в адресной карточке VL.ru, отключение было запланировано на 10 июня с 09:00 до 17:00 по местному времени.", source_url: "https://www.vl.ru/off/blackout/164701.html", confidence: 1, kind: 'official' },
  { id: "vpes-vladivostok-2026-2026-06-11-svetlanskaya-155", house_id: "svetlanskaya-155", type: "power", date: "2026-06-11", severity: 1, title: "Плановое отключение электричества на Светланской, 155", summary: "По данным АО «ВПЭС» в адресной карточке VL.ru, отключение было запланировано на 11 июня с 09:00 до 17:00 по местному времени.", source_url: "https://www.vl.ru/off/blackout/164723.html", confidence: 1, kind: 'official' },
  { id: "vpes-vladivostok-2026-2026-07-01-shilkinskaya-11", house_id: "shilkinskaya-11", type: "power", date: "2026-07-01", severity: 1, title: "Плановое отключение электричества на Шилкинской, 11", summary: "По данным АО «ВПЭС» в адресной карточке VL.ru, отключение было запланировано на 1 июля с 09:00 до 17:00 по местному времени.", source_url: "https://www.vl.ru/off/blackout/165276.html", confidence: 1, kind: 'official' },
  { id: "vpes-vladivostok-2026-2026-07-31-krygina-80", house_id: "krygina-80", type: "power", date: "2026-07-31", severity: 1, title: "Плановое отключение электричества на Крыгина, 80", summary: "По данным АО «ВПЭС» в адресной карточке VL.ru, отключение было запланировано на 31 июля с 09:00 до 17:00 по местному времени.", source_url: "https://www.vl.ru/off/blackout/166262.html", confidence: 1, kind: 'official' },
]

/**
 * Синтетика только для бейджей `ai`/`resident`: настоящих таких событий в
 * seed ещё нет (`POST /api/reports` — задача W1). `confidence` ниже 0.8 —
 * по контракту такие события не идут в индекс.
 */
const SYNTHETIC_EVENTS: Event[] = [
  {
    id: 'mock-ai-svetlanskaya-37',
    house_id: 'svetlanskaya-37',
    type: 'caprepair',
    date: '2026-09-02',
    severity: 2,
    title: 'Жильцы обсуждают сроки капремонта фасада',
    summary: 'Сводка сообщений из открытых чатов района. Официальным источником не подтверждено.',
    source_url: 'https://t.me/vladivostok_chat/0',
    confidence: 0.4,
    kind: 'ai',
  },
  {
    id: 'mock-resident-svetlanskaya-37',
    house_id: 'svetlanskaya-37',
    type: 'elevator',
    date: '2026-10-14',
    severity: 2,
    title: 'Лифт во втором подъезде стоял три дня',
    summary: 'Сообщение жильца через форму обратной связи. Проверяется вручную.',
    source_url: 'https://t.me/vladivostok_chat/1',
    confidence: 0.3,
    kind: 'resident',
  },
  {
    id: 'mock-ai-svetlanskaya-155',
    house_id: 'svetlanskaya-155',
    type: 'transport',
    date: '2026-07-20',
    severity: 1,
    title: 'Обсуждение изменения маршрута автобуса у дома',
    summary: 'Сводка сообщений из открытых чатов. Требует проверки.',
    source_url: 'https://t.me/vladivostok_chat/2',
    confidence: 0.35,
    kind: 'ai',
  },
  {
    id: 'mock-resident-basargina-15',
    house_id: 'basargina-15',
    type: 'flood',
    date: '2026-06-30',
    severity: 3,
    title: 'Подтопление парковки после ливня',
    summary: 'Сообщение жильца о подтоплении. Официального подтверждения нет.',
    source_url: 'https://t.me/vladivostok_chat/3',
    confidence: 0.3,
    kind: 'resident',
  },
]

/** Веса и подписи компонент — те же, что в поиске: одна синтетика на весь UI. */
const COMPONENTS: Array<[ComponentKey, string, number, number]> = [
  ['communications', 'Коммуникации', 0.26, 4],
  ['nature', 'Природа', 0.16, -3],
  ['building', 'Дом', 0.24, 6],
  ['transport', 'Транспорт', 0.2, -6],
  ['safety', 'Безопасность', 0.14, 2],
]

function clamp(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)))
}

function buildIndex(value: number, events: Event[]): HouseIndex {
  const components: Component[] = COMPONENTS.map(([key, label, weight, offset]) => ({
    key,
    label,
    score: clamp(value + offset),
    weight,
    explanation: `Синтетическая оценка по открытым данным, не из API: ${label.toLowerCase()}.`,
    source_urls: events
      .filter((event) => event.type === key)
      .slice(0, 2)
      .map((event) => event.source_url),
  }))
  const hasEvents = events.length > 0
  return {
    total: clamp(value),
    components,
    coverage: hasEvents ? 0.8 : 0.5,
    coverage_note: hasEvents ? null : 'подтверждённых событий по дому нет',
    computed_at: RETRIEVED_TS,
  }
}

function buildHouse(id: string, address: string, district: string): House {
  const passport = PASSPORT[id] ?? { urls: [DISTRICT_SOURCE] }
  return {
    id,
    address,
    district,
    lat: null,
    lon: null,
    year: passport.year ?? null,
    floors: passport.floors ?? null,
    material: passport.material ?? null,
    wear_pct: null,
    uk: null,
    avariy: false,
    caprepair: false,
    developer: null,
    source_urls: passport.urls,
    retrieved_at: RETRIEVED_TS,
  }
}

function buildFacts(id: string, district: string): Fact[] {
  const passport = PASSPORT[id] ?? { urls: [DISTRICT_SOURCE] }
  const mainSource = passport.urls[0] ?? DISTRICT_SOURCE
  const facts: Fact[] = []
  if (passport.year !== undefined) {
    facts.push({
      id: `${id}-year`,
      type: 'building',
      label: 'Год постройки',
      value: String(passport.year),
      source_url: mainSource,
      retrieved_at: RETRIEVED_AT,
      confidence: 1,
    })
  }
  if (passport.floors !== undefined) {
    facts.push({
      id: `${id}-floors`,
      type: 'building',
      label: 'Этажность',
      value: String(passport.floors),
      source_url: mainSource,
      retrieved_at: RETRIEVED_AT,
      confidence: 1,
    })
  }
  if (passport.material !== undefined) {
    facts.push({
      id: `${id}-material`,
      type: 'building',
      label: 'Материал стен',
      value: passport.material,
      source_url: mainSource,
      retrieved_at: RETRIEVED_AT,
      confidence: 1,
    })
  }
  facts.push({
    id: `${id}-district`,
    type: 'legal',
    label: 'Административный район',
    value: district,
    source_url: DISTRICT_SOURCE,
    retrieved_at: RETRIEVED_AT,
    confidence: 1,
  })
  return facts
}

/** Вопрос выводится из конкретного события — как требует контракт `ChecklistItem`. */
const QUESTIONS: Partial<Record<Event['type'], string>> = {
  hot_water: 'Как часто в доме отключают горячую воду и на сколько дней?',
  power: 'Бывают ли в доме плановые отключения электричества и предупреждают ли о них?',
  accident: 'Что за авария была в доме и устранили ли её последствия?',
  flood: 'Что делают с подтоплением и куда обращались жильцы?',
  elevator: 'Как часто ломается лифт и кто его обслуживает?',
  caprepair: 'Когда по плану капремонт фасада и платили ли жильцы взносы?',
  transport: 'Меняется ли маршрут транспорта у дома и как это влияет на дорогу?',
}

function buildChecklist(id: string, events: Event[]): ChecklistItem[] {
  const items: ChecklistItem[] = []
  for (const event of events) {
    const question = QUESTIONS[event.type]
    if (!question) continue
    if (items.some((item) => item.question === question)) continue
    items.push({
      id: `${id}-q-${items.length + 1}`,
      question,
      reason: `${event.date}: ${event.title}`,
      source_event_ids: [event.id],
    })
  }
  return items
}

function buildDossier(summary: (typeof MOCK_SUMMARIES)[number]): Dossier {
  const { id, address, district } = summary
  const events = [...OFFICIAL_EVENTS, ...SYNTHETIC_EVENTS]
    .filter((event) => event.house_id === id)
    .sort((a, b) => b.date.localeCompare(a.date))
  const house = buildHouse(id, address, district)
  house.caprepair = events.some((event) => event.type === 'caprepair')
  return {
    house,
    index: buildIndex(summary.index ?? 50, events),
    facts: buildFacts(id, district),
    events,
    checklist: buildChecklist(id, events),
    sources: [
      { name: 'Перечень избирательных участков Владивостока', url: DISTRICT_SOURCE, retrieved_at: RETRIEVED_AT },
      ...house.source_urls
        .filter((url) => url !== DISTRICT_SOURCE)
        .map((url, position) => ({
          name: `Паспорт дома, источник ${position + 1}`,
          url,
          retrieved_at: RETRIEVED_AT,
        })),
    ],
    disclaimer: DISCLAIMER,
  }
}

export const MOCK_DOSSIERS: Dossier[] = MOCK_SUMMARIES.map(buildDossier)

/** Задержка, чтобы в dev были видны состояния загрузки. */
const LATENCY_MS = 320

function wait(ms: number, signal: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('aborted', 'AbortError'))
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    function onAbort(): void {
      clearTimeout(timer)
      reject(new DOMException('aborted', 'AbortError'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

/** `null` для неизвестного id: клиент превратит это в 404 `house not found`. */
export async function mockHouseDossier(
  id: string,
  signal: AbortSignal | null = null,
): Promise<Dossier | null> {
  await wait(LATENCY_MS, signal)
  return MOCK_DOSSIERS.find((dossier) => dossier.house.id === id) ?? null
}
