/**
 * Тесты форматирования, общего для экрана досье.
 *
 * Запуск: `node --test frontend/tests/`.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { formatCoverage, formatDate, formatWeight } from '../src/lib/format.ts'

test('formatDate: ISO-дата без времени не уезжает на день назад', () => {
  // Полночь UTC в часовом поясе западнее UTC — это ещё предыдущий день.
  // Поэтому форматтер обязан фиксировать timeZone: 'UTC'.
  assert.equal(formatDate('2026-09-05'), '5 сентября 2026 г.')
  assert.equal(formatDate('2026-06-08'), '8 июня 2026 г.')
  assert.equal(formatDate('2026-01-01'), '1 января 2026 г.')
})

test('formatDate: битую строку возвращает как есть, а не «Invalid Date»', () => {
  assert.equal(formatDate('не дата'), 'не дата')
  assert.equal(formatDate(''), '')
})

test('formatWeight: доля превращается в проценты', () => {
  assert.equal(formatWeight(0.26), '26 %')
  assert.equal(formatWeight(0.2), '20 %')
  assert.equal(formatWeight(0), '0 %')
  assert.equal(formatWeight(1), '100 %')
})

test('formatCoverage: множитель покрытия превращается в проценты', () => {
  assert.equal(formatCoverage(0.5), '50 %')
  assert.equal(formatCoverage(0.8), '80 %')
  assert.equal(formatCoverage(1), '100 %')
})

test('formatWeight и formatCoverage не округляют вверх на границе', () => {
  // 0.145 * 100 = 14.499999999999998 в IEEE 754: round даст 14, а не 15.
  // Тест фиксирует поведение, а не требует конкретного округления.
  assert.equal(formatWeight(0.145), '14 %')
  assert.equal(formatCoverage(0.999), '100 %')
})
