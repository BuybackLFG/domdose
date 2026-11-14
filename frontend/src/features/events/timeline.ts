/**
 * Чистая логика ленты событий (DD-24, F3): подписи, сортировка, модели показа.
 *
 * Здесь нет React и DOM — только данные. Поэтому именно этот модуль
 * тестируется в `frontend/tests/events.test.ts`, а компонент остаётся тонким.
 *
 * Контракт не гарантирует порядок событий и не гарантирует валидность `date`
 * (на входе может оказаться что угодно, потому что данные приходят из ingest).
 * Поэтому сортируем сами, а битые даты не роняют список, а уезжают в конец.
 */
import type { Event, EventKind, EventType } from '../../types'

/* ── Тип события ─────────────────────────────────────────────────────────── */

/**
 * Русские подписи значений `EventType`. `Record` вместо `Map`
 * намеренно: если контракт добавит тип, TypeScript потребует дополнить
 * таблицу, и мы не забудем подпись.
 */
const EVENT_TYPE_LABELS: Record<EventType, string> = {
  hot_water: 'горячая вода',
  cold_water: 'холодная вода',
  heat: 'отопление',
  accident: 'авария',
  power: 'электричество',
  flood: 'подтопление',
  landslide: 'оползень',
  typhoon: 'тайфун',
  wind: 'ветер',
  ice: 'гололёд',
  elevator: 'лифт',
  caprepair: 'капремонт',
  developer: 'застройщик',
  transport: 'транспорт',
}

export function isEventType(value: string): value is EventType {
  return Object.hasOwn(EVENT_TYPE_LABELS, value)
}

/** Подпись типа. Неизвестное значение показываем как есть, но не падаем. */
export function eventTypeLabel(type: string | null | undefined): string {
  if (!type) return 'тип не указан'
  if (isEventType(type)) return EVENT_TYPE_LABELS[type]
  return `другое (${type})`
}

/* ── Серьёзность ─────────────────────────────────────────────────────────── */

export interface SeverityView {
  /** 1–3 из контракта; 0 — значение вне диапазона. */
  level: number
  /** «низкая» / «средняя» / «критичная» — читается без цвета. */
  label: string
  /** «1 из 3» — шкала рядом с подписью, тоже текстом. */
  scale: string
}

const SEVERITY_LABELS: Record<number, string> = {
  1: 'низкая',
  2: 'средняя',
  3: 'критичная',
}

export function severityView(severity: number | null | undefined): SeverityView {
  const level = typeof severity === 'number' && Number.isInteger(severity) ? severity : 0
  if (level >= 1 && level <= 3) {
    return { level, label: SEVERITY_LABELS[level] ?? 'неизвестно', scale: `${level} из 3` }
  }
  // Значение вне контракта: честно говорим, что не знаем, вместо «критичная».
  return { level: 0, label: 'не указана', scale: '—' }
}

/* ── Источник события ────────────────────────────────────────────────────── */

export type KindTone = 'official' | 'ai' | 'resident' | 'unknown'

export interface KindView {
  /** Различимая текстовая метка — не только цвет. */
  label: string
  /** Короткая честная пометка о непроверенности, если она нужна. */
  note: string | null
  /** Тон для оформления; смысл несёт `label`, а не цвет. */
  tone: KindTone
}

export function kindView(kind: string | null | undefined): KindView {
  switch (kind) {
    case 'official':
      return { label: 'официальный источник', note: null, tone: 'official' }
    case 'ai':
      return { label: 'сводка ИИ', note: 'не подтверждено официально', tone: 'ai' }
    case 'resident':
      return { label: 'сообщение жильца', note: 'не проверено', tone: 'resident' }
    default:
      return { label: 'источник не указан', note: null, tone: 'unknown' }
  }
}

/** Порог контракта: ниже него `ai`-событие не идёт в индекс. */
export const CONFIDENCE_THRESHOLD = 0.8

/**
 * Уверенность числом — только для не-официальных событий и только когда она
 * ниже порога. Официальный источник проверять незачем, а высокую уверенность
 * не показываем, чтобы не создавать ложного ощущения точности.
 */
export function confidencePercent(
  kind: EventKind | string | null | undefined,
  confidence: number | null | undefined,
): number | null {
  if (kind === 'official') return null
  if (typeof confidence !== 'number' || Number.isNaN(confidence)) return null
  if (confidence >= CONFIDENCE_THRESHOLD) return null
  return Math.round(confidence * 100)
}

/* ── Сортировка ──────────────────────────────────────────────────────────── */

/**
 * `'2026-09-05'` → миллисекунды UTC, `null` если дата битая.
 *
 * `Date.parse('2026-02-31')` не NaN: движок молча переносит на 3 марта.
 * Поэтому сверяем компоненты обратно — иначе несуществующая дата попала бы
 * в середину списка.
 */
export function dateValue(iso: string | null | undefined): number | null {
  if (!iso) return null
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso.trim())
  if (!match) return null

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null

  const time = Date.UTC(year, month - 1, day)
  const date = new Date(time)
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null
  }
  return time
}

function compareIds(a: { id: string }, b: { id: string }): number {
  if (a.id === b.id) return 0
  return a.id < b.id ? -1 : 1
}

/**
 * Сортировка по убыванию даты, битые даты — в конец.
 *
 * При равных датах порядок задаёт `id`: `Array#sort` стабилен, но стабильность
 * сохраняет *входной* порядок, а он у API не гарантирован. Явный tie-break
 * по `id` делает результат одинаковым при любом порядке входа, и список
 * не «прыгает» между рендерами.
 */
export function sortEvents<T extends { id: string; date: string }>(events: readonly T[]): T[] {
  return [...events].sort((a, b) => {
    const dateA = dateValue(a.date)
    const dateB = dateValue(b.date)

    if (dateA === null && dateB === null) return compareIds(a, b)
    if (dateA === null) return 1
    if (dateB === null) return -1
    if (dateA !== dateB) return dateB - dateA
    return compareIds(a, b)
  })
}

/* ── Модель показа ───────────────────────────────────────────────────────── */

export interface TimelineItem {
  id: string
  title: string
  summary: string | null
  /** Исходная ISO-дата — для `formatDate` и атрибута `datetime`. */
  date: string
  /** Дата распознана: только тогда её можно ставить в `datetime`. */
  dateValid: boolean
  /** Район — только у районных событий (`house_id == null`). */
  district: string | null
  typeLabel: string
  severity: SeverityView
  kind: KindView
  /** Уверенность числом, если она низкая и неофициальная. */
  confidencePercent: number | null
  sourceUrl: string
  /** Короткий хост для подписи ссылки; пустая строка, если URL битый. */
  sourceHost: string
}

/** Хост без `www.` — чтобы ссылка читалась как «Источник: vl.ru». */
export function sourceHost(url: string | null | undefined): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

/** Отсортированный и подготовленный к показу таймлайн. */
export function buildTimeline(events: readonly Event[] | null | undefined): TimelineItem[] {
  if (!events || events.length === 0) return []

  return sortEvents(events).map((event) => ({
    id: event.id,
    title: event.title,
    summary: event.summary ?? null,
    date: event.date,
    dateValid: dateValue(event.date) !== null,
    // Районное событие не привязано к дому — тогда район и есть его адрес.
    district: event.house_id ? null : (event.district ?? null),
    typeLabel: eventTypeLabel(event.type),
    severity: severityView(event.severity),
    kind: kindView(event.kind),
    confidencePercent: confidencePercent(event.kind, event.confidence),
    sourceUrl: event.source_url,
    sourceHost: sourceHost(event.source_url),
  }))
}
