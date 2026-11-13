/**
 * Тесты чистой логики раздела досье (DD-23). Запуск: `node --test frontend/tests/`.
 *
 * React-компоненты здесь не рендерятся: без jsdom и Testing Library проверять
 * разметку дороже, чем полезно. Вместо этого тестами закрыта логика, которую
 * легко сломать молча, — порядок компонент, сумма весов, группировка фактов.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { summarizeComponents, weakestComponents } from '../src/features/dossier/componentsSummary.ts'
import { groupFacts, sourceHost } from '../src/features/dossier/factGroups.ts'
import { formatWeight } from '../src/lib/format.ts'
import type { Component, Fact } from '../src/types'

function component(key: string, label: string, score: number, weight: number): Component {
  return {
    key: key as Component['key'],
    label,
    score,
    weight,
    explanation: `Пояснение: ${label}`,
  }
}

function fact(id: string, type: Fact['type'], label: string): Fact {
  return {
    id,
    type,
    label,
    value: `${label}-значение`,
    source_url: `https://example.org/${id}`,
    retrieved_at: '2026-11-13',
    confidence: 1,
  }
}

const FIVE: Component[] = [
  component('communications', 'Коммуникации', 74, 0.26),
  component('nature', 'Природа', 47, 0.16),
  component('building', 'Дом', 56, 0.24),
  component('transport', 'Транспорт', 44, 0.2),
  component('safety', 'Безопасность', 52, 0.14),
]

test('summarizeComponents: сумма весов и подписи не зависят от порядка входа', () => {
  const straight = summarizeComponents(FIVE)
  const reversed = summarizeComponents([...FIVE].reverse())
  const shuffled = summarizeComponents([FIVE[2]!, FIVE[0]!, FIVE[4]!, FIVE[1]!, FIVE[3]!])

  assert.equal(straight.rows.length, 5)
  assert.equal(straight.totalWeight, reversed.totalWeight)
  assert.equal(straight.totalWeight, shuffled.totalWeight)
  assert.equal(formatWeight(straight.totalWeight), formatWeight(shuffled.totalWeight))

  // Порядок строк задаёт контракт, а не ответ API: перестановка не должна
  // менять экран, иначе два дома покажут компоненты в разном порядке.
  const keys = straight.rows.map((row) => row.key)
  assert.deepEqual(keys, reversed.rows.map((row) => row.key))
  assert.deepEqual(keys, ['communications', 'nature', 'building', 'transport', 'safety'])
  assert.deepEqual(
    straight.rows.map((row) => row.label),
    reversed.rows.map((row) => row.label),
  )
})

test('summarizeComponents: weight остаётся долей и форматируется общим хелпером', () => {
  const summary = summarizeComponents(FIVE)
  // Модуль не округляет вес сам — иначе проценты считались бы в двух местах.
  assert.equal(summary.rows[0]?.weight, 0.26)
  assert.equal(formatWeight(summary.rows[0]!.weight), '26 %')
  assert.equal(formatWeight(summary.totalWeight), '100 %')

  const skewed = summarizeComponents([component('building', 'Дом', 150, 0.24)])
  assert.equal(skewed.rows[0]?.score, 150, 'score показываем как есть: это данные API')
  assert.equal(skewed.rows[0]?.scorePct, 100, 'полоска не вылезает за 100 %')

  const negative = summarizeComponents([component('building', 'Дом', -20, 0.24)])
  assert.equal(negative.rows[0]?.scorePct, 0)
})

test('groupFacts: сохраняет порядок групп и фактов и не теряет legal', () => {
  const facts = [
    fact('f1', 'building', 'Год постройки'),
    fact('f2', 'building', 'Этажность'),
    fact('f3', 'legal', 'Административный район'),
    fact('f4', 'transport', 'Ближайшая остановка'),
  ]
  const groups = groupFacts(facts)

  assert.deepEqual(
    groups.map((group) => group.type),
    ['building', 'legal', 'transport'],
    'группы идут в порядке первого появления, legal не выкидывается',
  )
  assert.deepEqual(
    groups[0]?.facts.map((item) => item.id),
    ['f1', 'f2'],
    'внутри группы порядок ответа API сохраняется',
  )
  assert.equal(groups[1]?.title, 'Юридический статус')
  assert.equal(
    groups.flatMap((group) => group.facts).length,
    facts.length,
    'ни один факт не потерян',
  )
})

test('groupFacts: пустой вход даёт пустую структуру, а не группу с заголовком', () => {
  assert.deepEqual(groupFacts([]), [])
})

test('sourceHost: отдаёт хост без www и не падает на битом URL', () => {
  assert.equal(sourceHost('https://www.vl.ru/off/management-company/51.html'), 'vl.ru')
  assert.equal(sourceHost('https://openaddress.ru/houses/abc'), 'openaddress.ru')
  assert.equal(sourceHost('не-url'), 'не-url')
})


test('weakestComponents: учитывает равные минимумы и отсутствие корректных оценок', () => {
  const rows = summarizeComponents(FIVE).rows
  assert.deepEqual(weakestComponents(rows).map((row) => row.key), ['transport'])
  const ties = summarizeComponents([component('nature', 'Природа', 44, 0.5), component('transport', 'Транспорт', 44, 0.5)]).rows
  assert.deepEqual(weakestComponents(ties).map((row) => row.key), ['nature', 'transport'])
  assert.deepEqual(weakestComponents([]), [])
  assert.deepEqual(weakestComponents(summarizeComponents([component('building', 'Дом', -1, 1)]).rows), [])
})
