/**
 * Подготовка компонент индекса к показу — без React.
 *
 * Зачем отдельный модуль: порядок компонент задаёт контракт, а веса должны
 * выглядеть одинаково независимо от того, в каком порядке их прислал backend.
 * Логику, которую жалко потерять, проверяем в `tests/dossier.test.ts`.
 *
 * Здесь нет ни одного рантайм-импорта (только типы): тесты гоняются нативным
 * `node --test` с type-stripping, а он не умеет разрешать импорты без
 * расширения. Поэтому `weight` отдаётся сырой долей (`0.26`), а подпись
 * `'26 %'` делает компонент через общий `lib/format.ts` — модуль не должен
 * округлять вес сам, иначе проценты посчитаются в двух местах.
 */
import type { Component } from '../../types'

/** Порядок пяти компонент из контракта (`ComponentKey`). Незнакомые ключи — в конце. */
const COMPONENT_ORDER: readonly string[] = [
  'communications',
  'nature',
  'building',
  'transport',
  'safety',
]

export interface ComponentRow {
  key: string
  label: string
  /** Оценка 0–100 как есть: число в тексте, а не только цвет полоски. */
  score: number
  /** Ширина полоски в процентах, зажатая в 0–100 (защита от кривых данных). */
  scorePct: number
  /** Доля в индексе, как в контракте: `0.26`, а не `26`. */
  weight: number
  explanation: string
}

export interface ComponentsSummary {
  /** Компоненты в порядке контракта, а не в порядке ответа API. */
  rows: ComponentRow[]
  /** Сумма весов сырыми долями: 1 у корректного индекса. */
  totalWeight: number
}

function rank(key: string): number {
  const position = COMPONENT_ORDER.indexOf(key)
  return position === -1 ? COMPONENT_ORDER.length : position
}

function clampScore(score: number): number {
  return Math.min(100, Math.max(0, score))
}

export function summarizeComponents(components: readonly Component[]): ComponentsSummary {
  const rows: ComponentRow[] = components.map((component) => ({
    key: component.key,
    label: component.label,
    score: component.score,
    scorePct: clampScore(component.score),
    weight: component.weight,
    explanation: component.explanation,
  }))

  // Сортировка до суммирования: сумма float зависит от порядка слагаемых,
  // поэтому один набор компонент обязан давать одну и ту же `totalWeight`.
  rows.sort((left, right) => rank(left.key) - rank(right.key))

  return { rows, totalWeight: rows.reduce((sum, row) => sum + row.weight, 0) }
}

/** Все компоненты с минимальной достоверной оценкой; равные оценки не скрываем. */
export function weakestComponents(rows: readonly ComponentRow[]): ComponentRow[] {
  const valid = rows.filter((row) => Number.isFinite(row.score) && row.score >= 0 && row.score <= 100)
  if (valid.length === 0) return []
  const minimum = Math.min(...valid.map((row) => row.score))
  return valid.filter((row) => row.score === minimum)
}
