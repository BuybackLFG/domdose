/**
 * Нормализация поискового запроса и поиск совпадения для подсветки.
 *
 * Чистые функции без DOM и React: их поведение зафиксировано тестами в
 * `frontend/tests/`, потому что именно здесь легко разъехаться с backend.
 */

/**
 * Приведение запроса к сравнимому виду. Правила должны совпадать с B1 на
 * backend: иначе «Ёлка» найдётся в списке, но уедет в сеть другим запросом.
 */
export function normalizeQuery(value: string): string {
  return value.trim().toLowerCase().replaceAll('ё', 'е').replaceAll(/\s+/g, ' ')
}

const YO = /ё/gi

/**
 * Смещение совпадения в **исходной** строке.
 *
 * Замена «ё → е» идёт 1:1 по символам, поэтому индексы нормализованной строки
 * совпадают с исходной и `slice` не разъезжается.
 */
export function findMatch(
  haystack: string,
  needle: string,
): { start: number; end: number } | null {
  const normalizedNeedle = normalizeQuery(needle)
  if (normalizedNeedle === '') return null
  const index = haystack.toLowerCase().replaceAll(YO, 'е').indexOf(normalizedNeedle)
  if (index < 0) return null
  return { start: index, end: index + normalizedNeedle.length }
}
