/**
 * Тесты чистых функций поиска. Запуск: `node --test frontend/tests/`.
 *
 * Запускаются встроенным в Node раннером (`node --test`) с нативным
 * type-stripping, поэтому новых зависимостей в package.json не нужно.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { findMatch, normalizeQuery } from '../src/lib/normalize.ts'
import { matchHouseId, ROUTES } from '../src/lib/routes.ts'
import { enterIndex, nextIndex } from '../src/features/search/selection.ts'

test('normalizeQuery: трим, регистр, ё→е, схлопывание пробелов', () => {
  assert.equal(normalizeQuery('  Светланская  '), 'светланская')
  assert.equal(normalizeQuery('ПЕРВОРЕЧЕНСКИЙ'), 'первореченский')
  assert.equal(normalizeQuery('Льва  Толстого'), 'льва толстого')
  assert.equal(normalizeQuery('ёлка'), 'елка')
  assert.equal(normalizeQuery('Ёлка'), 'елка')
  assert.equal(normalizeQuery(''), '')
  assert.equal(normalizeQuery('   '), '')
})

test('normalizeQuery: уже нормализованный запрос не меняется', () => {
  const once = normalizeQuery('  Первая   речка ')
  assert.equal(normalizeQuery(once), once)
})

test('findMatch: находит по подстроке и отдаёт смещение в исходной строке', () => {
  assert.deepEqual(findMatch('Светланская, 37', 'светланская'), { start: 0, end: 11 })
  assert.deepEqual(findMatch('Светланская, 37', '37'), { start: 13, end: 15 })
  assert.deepEqual(findMatch('Светланская, 37', 'ланск'), { start: 4, end: 9 })
})

test('findMatch: ё в тексте находится запросом с е и наоборот', () => {
  // «ё» и «е» — один символ, поэтому смещения совпадают с исходной строкой.
  assert.deepEqual(findMatch('Льва Толстого, 1', 'льва толстого'), { start: 0, end: 13 })
  assert.deepEqual(findMatch('Ул. Ёлочная, 5', 'елочная'), { start: 4, end: 11 })
  assert.deepEqual(findMatch('Ул. Елочная, 5', 'ёлочная'), { start: 4, end: 11 })
})

test('findMatch: нет совпадения и пустой запрос дают null', () => {
  assert.equal(findMatch('Светланская, 37', 'русская'), null)
  assert.equal(findMatch('Светланская, 37', ''), null)
  assert.equal(findMatch('Светланская, 37', '   '), null)
})

test('findMatch: подсветка не выходит за границы строки', () => {
  const text = 'Невская, 33'
  const match = findMatch(text, '33')
  assert.ok(match)
  assert.equal(text.slice(match.start, match.end), '33')
  assert.equal(text.slice(0, match.start) + text.slice(match.end), 'Невская, ')
})

test('matchHouseId: разбирает свой и только свой маршрут', () => {
  assert.equal(matchHouseId('/house/svetlanskaya-37'), 'svetlanskaya-37')
  assert.equal(matchHouseId('/house/svetlanskaya-37/'), 'svetlanskaya-37')
  assert.equal(matchHouseId('/house/basargina-6b-1'), 'basargina-6b-1')
  assert.equal(matchHouseId('/house/a%20b'), 'a b')

  assert.equal(matchHouseId('/'), null)
  assert.equal(matchHouseId('/house'), null)
  assert.equal(matchHouseId('/house/'), null)
  assert.equal(matchHouseId('/houses/x'), null)
  assert.equal(matchHouseId('/house/x/y'), null)
  assert.equal(matchHouseId('/house/%E0%A4%A'), null)
})

test('ROUTES.house экранирует id и разбирается обратно', () => {
  const href = ROUTES.house('a b/c')
  assert.equal(href, '/house/a%20b%2Fc')
  assert.equal(matchHouseId(href), 'a b/c')
  assert.equal(ROUTES.search, '/')
})

test('nextIndex: первый шаг вниз выбирает первый вариант, вверх — последний', () => {
  assert.equal(nextIndex(3, -1, 1), 0)
  assert.equal(nextIndex(3, -1, -1), 2)
  assert.equal(nextIndex(3, 0, 1), 1)
  assert.equal(nextIndex(3, 2, 1), 0, 'вниз с последнего уходит на первый')
  assert.equal(nextIndex(3, 0, -1), 2, 'вверх с первого уходит на последний')
})

test('nextIndex: пустой список всегда -1', () => {
  assert.equal(nextIndex(0, -1, 1), -1)
  assert.equal(nextIndex(0, 0, 1), -1)
  assert.equal(nextIndex(0, 5, -1), -1)
})

test('enterIndex: выбранный вариант важнее первого', () => {
  assert.equal(enterIndex(3, 1, 'светланская'), 1)
})

test('enterIndex: без выбора открывается первый вариант при непустом запросе', () => {
  assert.equal(enterIndex(3, -1, 'светланская'), 0)
  assert.equal(enterIndex(3, -1, '  '), -1, 'пустой запрос не открывает каталог')
  assert.equal(enterIndex(0, -1, 'светланская'), -1, 'нечего открывать')
})

test('enterIndex: устаревший индекс не открывает чужой дом', () => {
  assert.equal(enterIndex(2, 7, 'светланская'), 0)
})
