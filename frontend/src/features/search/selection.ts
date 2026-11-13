/**
 * Логика перемещения по вариантам в списке автокомплита.
 *
 * Отдельно от компонента, потому что именно здесь живут неочевидные правила:
 * переход по кругу, первый шаг вниз выбирает первый вариант, а не второй.
 */

/**
 * Новый активный индекс.
 *
 * @param count сколько вариантов в списке
 * @param current текущий индекс; `-1` означает «ничего не выбрано»
 * @param delta `+1` вниз, `-1` вверх
 */
export function nextIndex(count: number, current: number, delta: number): number {
  if (count <= 0) return -1
  if (current < 0) return delta > 0 ? 0 : count - 1
  return (current + delta + count) % count
}

/** Индекс варианта, который откроется по Enter; `-1`, если открывать нечего. */
export function enterIndex(count: number, current: number, query: string): number {
  if (current >= 0 && current < count) return current
  // Enter на пустом запросе не должен открывать первый дом каталога:
  // пользователь ещё ничего не искал.
  if (count > 0 && query.trim() !== '') return 0
  return -1
}
