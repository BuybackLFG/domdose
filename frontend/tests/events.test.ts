/**
 * Тесты ленты событий дома: сортировка, подписи, честность источника.
 *
 * Запуск: `node --test frontend/tests/` (нативный type-stripping Node).
 * Проверяется чистый модуль `features/events/timeline.ts`: компонент рисует
 * ровно то, что вернул `buildTimeline`, поэтому этих тестов достаточно.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildTimeline,
  confidencePercent,
  dateValue,
  eventTypeLabel,
  kindView,
  severityView,
  sortEvents,
  sourceHost,
} from '../src/features/events/timeline.ts'
import type { Event, EventType } from '../src/types/index.ts'

function makeEvent(overrides: Partial<Event> & { id: string; date: string }): Event {
  return {
    type: 'power',
    severity: 1,
    title: `Событие ${overrides.id}`,
    source_url: 'https://example.com/news',
    confidence: 1,
    kind: 'official',
    ...overrides,
  }
}

const ALL_TYPES: EventType[] = [
  'hot_water',
  'accident',
  'power',
  'flood',
  'landslide',
  'typhoon',
  'ice',
  'elevator',
  'caprepair',
  'developer',
  'transport',
]

test('сортировка по убыванию даты, при равных датах — стабильно по id', () => {
  const events = [
    makeEvent({ id: 'b-old', date: '2026-01-10' }),
    makeEvent({ id: 'z-new', date: '2026-09-05' }),
    makeEvent({ id: 'm-mid', date: '2026-05-01' }),
    makeEvent({ id: 'a-tie', date: '2026-05-01' }),
  ]

  const sorted = sortEvents(events)
  assert.deepEqual(
    sorted.map((event) => event.id),
    ['z-new', 'a-tie', 'm-mid', 'b-old'],
  )
})

test('порядок не зависит от порядка входа и от перестановок', () => {
  const a = makeEvent({ id: 'a', date: '2026-03-01' })
  const b = makeEvent({ id: 'b', date: '2026-03-01' })
  const c = makeEvent({ id: 'c', date: '2026-06-01' })

  const one = sortEvents([a, b, c]).map((event) => event.id)
  const two = sortEvents([c, b, a]).map((event) => event.id)
  const three = sortEvents([b, a, c]).map((event) => event.id)

  assert.deepEqual(one, ['c', 'a', 'b'])
  assert.deepEqual(two, one, 'реверс входа не меняет порядок равных дат')
  assert.deepEqual(three, one)
})

test('битая дата уезжает в конец и не ломает список', () => {
  const events = [
    makeEvent({ id: 'broken', date: 'не дата' }),
    makeEvent({ id: 'valid', date: '2026-04-01' }),
    makeEvent({ id: 'empty', date: '' }),
    makeEvent({ id: 'impossible', date: '2026-02-31' }),
  ]

  const items = buildTimeline(events)
  assert.equal(items.length, 4, 'ни одно событие не потеряно')
  assert.equal(items[0]?.id, 'valid', 'валидная дата идёт первой')
  assert.deepEqual(
    items.slice(1).map((item) => item.id),
    ['broken', 'empty', 'impossible'],
    'битые даты в конце, между собой упорядочены по id',
  )
  assert.equal(items[1]?.dateValid, false)
  assert.equal(items[0]?.dateValid, true)

  // formatDate вернёт исходную строку — компонент не упадёт на «Invalid Date».
  assert.equal(items[3]?.date, '2026-02-31')
})

test('dateValue не принимает несуществующие даты и даты не по шаблону', () => {
  assert.equal(dateValue('2026-09-05'), Date.UTC(2026, 8, 5))
  assert.equal(dateValue('2026-02-31'), null, '31 февраля не существует')
  assert.equal(dateValue('2026-13-01'), null)
  assert.equal(dateValue('05.09.2026'), null)
  assert.equal(dateValue(''), null)
  assert.equal(dateValue(null), null)
})

test('пустой массив даёт пустой таймлайн (компонент покажет пустое состояние)', () => {
  assert.deepEqual(buildTimeline([]), [])
  assert.deepEqual(buildTimeline(null), [])
  assert.deepEqual(buildTimeline(undefined), [])
})

test('подпись серьёзности читается без цвета', () => {
  assert.deepEqual(severityView(1), { level: 1, label: 'низкая', scale: '1 из 3' })
  assert.deepEqual(severityView(2), { level: 2, label: 'средняя', scale: '2 из 3' })
  assert.deepEqual(severityView(3), { level: 3, label: 'критичная', scale: '3 из 3' })

  // Вне контракта: не выдаём себя за «критичную».
  assert.equal(severityView(0).label, 'не указана')
  assert.equal(severityView(9).label, 'не указана')
  assert.equal(severityView(null).label, 'не указана')
  assert.equal(severityView(Number.NaN).label, 'не указана')
})

test('тип события подписан по-русски для всех 11 значений', () => {
  const labels = ALL_TYPES.map((type) => eventTypeLabel(type))
  assert.equal(new Set(labels).size, ALL_TYPES.length, 'подписи не повторяются')
  for (const label of labels) {
    assert.equal(typeof label, 'string')
    assert.ok(label.length > 0)
    assert.match(label, /[а-яё]/i, `подпись «${label}» должна быть русской`)
  }
  assert.equal(eventTypeLabel('hot_water'), 'горячая вода')
  assert.equal(eventTypeLabel('caprepair'), 'капремонт')
  assert.equal(eventTypeLabel('transport'), 'транспорт')
})

test('неизвестный или отсутствующий тип не роняет рендер', () => {
  // Такого значения нет в контракте, но данные приходят из ingest.
  assert.equal(eventTypeLabel('sunrise' as string), 'другое (sunrise)')
  assert.equal(eventTypeLabel(null), 'тип не указан')
  assert.equal(eventTypeLabel(undefined), 'тип не указан')
})

test('kind даёт различимые подписи для всех трёх значений', () => {
  const official = kindView('official')
  const ai = kindView('ai')
  const resident = kindView('resident')

  assert.equal(official.label, 'официальный источник')
  assert.equal(ai.label, 'сводка ИИ')
  assert.equal(resident.label, 'сообщение жильца')

  const labels = [official.label, ai.label, resident.label]
  assert.equal(new Set(labels).size, 3, 'подписи различимы текстом, а не только цветом')
  assert.equal(new Set([official.tone, ai.tone, resident.tone]).size, 3)

  assert.equal(official.note, null, 'официальный источник не нужно оговаривать')
  assert.equal(ai.note, 'не подтверждено официально')
  assert.equal(resident.note, 'не проверено')

  assert.equal(kindView(undefined).tone, 'unknown')
})

test('низкая уверенность показывается числом только у неофициальных событий', () => {
  assert.equal(confidencePercent('ai', 0.4), 40)
  assert.equal(confidencePercent('resident', 0.3), 30)
  assert.equal(confidencePercent('ai', 0.79), 79)
  assert.equal(confidencePercent('ai', 0.8), null, 'порог 0.8 — уже не «низкая»')
  assert.equal(confidencePercent('official', 0.5), null, 'у официального источника не бывает')
  assert.equal(confidencePercent('ai', null), null)
})

test('район показывается только у районного события', () => {
  const items = buildTimeline([
    makeEvent({ id: 'house', date: '2026-05-01', house_id: 's-37', district: 'Ленинский' }),
    makeEvent({ id: 'district', date: '2026-04-01', house_id: null, district: 'Ленинский' }),
  ])

  assert.equal(items[0]?.district, null, 'у события дома район не дублируем')
  assert.equal(items[1]?.district, 'Ленинский')
})

test('summary показывается, если он есть, и null, если его нет', () => {
  const items = buildTimeline([
    makeEvent({ id: 'with', date: '2026-05-01', summary: 'Подробности' }),
    makeEvent({ id: 'without', date: '2026-04-01' }),
  ])

  assert.equal(items[0]?.summary, 'Подробности')
  assert.equal(items[1]?.summary, null)
})

test('sourceHost отдаёт читаемый домен и переживает битый URL', () => {
  assert.equal(sourceHost('https://www.vl.ru/off/blackout/164594.html'), 'vl.ru')
  assert.equal(sourceHost('https://dvgk.ru/press/news/x/'), 'dvgk.ru')
  assert.equal(sourceHost(''), '')
  assert.equal(sourceHost(null), '')
  assert.equal(sourceHost('не url'), '')
})


test('новые типы событий получают понятные подписи', () => {
  assert.equal(eventTypeLabel('cold_water'), 'холодная вода')
  assert.equal(eventTypeLabel('heat'), 'отопление')
  assert.equal(eventTypeLabel('wind'), 'ветер')
})
