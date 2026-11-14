/**
 * Форматирование для показа: только то, что нужно нескольким экранам сразу.
 *
 * Локаль фиксируется (`ru-RU`), а не берётся из браузера: демо должно
 * выглядеть одинаково и на машине жюри, и в CI.
 */
const LOCALE = 'ru-RU'

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
})

/**
 * `'2026-09-05'` → `'5 сентября 2026 г.'`.
 *
 * `timeZone: 'UTC'` обязателен: `new Date('2026-09-05')` — это полночь UTC, и
 * в часовом поясе западнее UTC дата уехала бы на день назад.
 */
export function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return dateFormatter.format(date)
}

/** `0.26` → `'26 %'`. Ноль знаков: веса в контракте — доли, а не точные проценты. */
export function formatWeight(weight: number): string {
  return `${Math.round(weight * 100)} %`
}

/** `0.5` → `'50 %'`. Для `coverage` — множителя покрытия источников. */
export function formatCoverage(coverage: number): string {
  return `${Math.round(coverage * 100)} %`
}
