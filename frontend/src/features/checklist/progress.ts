/**
 * Прогресс чек-листа: сколько отмечено из скольких.
 *
 * Отдельный модуль без React, потому что это единственная арифметика экрана и
 * её хочется проверять в тестах без рендера. Свои вопросы входят в общий
 * счёт наравне с вопросами из API.
 */

export interface Progress {
  /** Отмечено видимых вопросов. */
  checked: number
  /** Всего видимых вопросов: API + свои. */
  total: number
  /** Заполненность в процентах, 0…100. Для ширины полосы. */
  percent: number
}

/**
 * `ids` — все видимые вопросы (API после дедупликации + свои).
 *
 * Отметки, которых нет среди видимых, игнорируются: вопрос мог исчезнуть из
 * API, а галочка остаться в localStorage. Иначе прогресс мог бы показать
 * «7 из 5».
 */
export function computeProgress(
  ids: readonly string[],
  checked: readonly string[],
): Progress {
  const total = ids.length
  if (total === 0) return { checked: 0, total: 0, percent: 0 }

  const visible = new Set(ids)
  const done = checked.filter((id) => visible.has(id)).length
  const unique = new Set(checked).size
  const count = Math.min(done, unique, total)
  return { checked: count, total, percent: Math.round((count / total) * 100) }
}

/** `<progress>` и `role="progressbar"` принимают только целые. */
export function progressNow(progress: Progress): number {
  return progress.checked
}

export function progressMax(progress: Progress): number {
  return progress.total
}
