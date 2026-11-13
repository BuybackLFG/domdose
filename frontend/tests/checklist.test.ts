/**
 * Тесты локального состояния чек-листа DD-25.
 *
 * Запуск: `node --test frontend/tests/` — Node 26, нативный type-stripping.
 * `localStorage` в Node нет, поэтому проверяются чистые функции, принимающие
 * строку или объект: сам storage остаётся тонкой обёрткой.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { computeProgress } from '../src/features/checklist/progress.ts'
import {
  STORAGE_PREFIX,
  addCustomQuestion,
  apiQuestions,
  emptyChecklist,
  mergeRows,
  normalizeQuestion,
  parseChecklist,
  serializeChecklist,
  storageKey,
  toggleChecked,
} from '../src/features/checklist/storage.ts'
import type { ChecklistItem } from '../src/types/index.ts'

const item = (id: string, question: string): ChecklistItem => ({
  id,
  question,
  reason: `причина ${id}`,
  source_event_ids: [`event-${id}`],
})

test('storageKey: ключ строится по house_id и дома не пересекаются', () => {
  assert.equal(storageKey('svetlanskaya-37'), `${STORAGE_PREFIX}svetlanskaya-37`)
  assert.equal(storageKey('leonova-25'), 'domdose:checklist:leonova-25')
  assert.notEqual(storageKey('svetlanskaya-37'), storageKey('leonova-25'))
  // Похожие id — разные ключи: разделитель не склеивает соседние дома.
  assert.notEqual(storageKey('dom-1'), storageKey('dom-12'))
})

test('parseChecklist: битый JSON, мусор и чужой формат дают пустое состояние', () => {
  for (const raw of ['{не json', '', '   ', 'null', '42', '"строка"', '[]']) {
    assert.deepEqual(parseChecklist(raw), emptyChecklist(), `вход: ${JSON.stringify(raw)}`)
  }
  assert.deepEqual(parseChecklist(null), emptyChecklist())
  assert.deepEqual(parseChecklist(undefined), emptyChecklist())
})

test('parseChecklist: чужие поля игнорируются, отметки и свои вопросы читаются', () => {
  const state = parseChecklist(
    JSON.stringify({
      checked: ['q-1', 7, '', 'q-1'],
      custom: [
        { id: 'c-1', question: '  Когда меняли стояки?  ' },
        { id: 'c-2' },
        { question: 'Без id' },
        'мусор',
      ],
      version: 99,
      owner: 'кто-то',
    }),
  )
  assert.deepEqual(state, {
    checked: ['q-1'],
    custom: [{ id: 'c-1', question: 'Когда меняли стояки?' }],
  })
})

test('serializeChecklist и parseChecklist — обратимая пара', () => {
  const state = {
    checked: ['q-2'],
    custom: [{ id: 'custom-1', question: 'Есть ли домофон?' }],
  }
  assert.deepEqual(parseChecklist(serializeChecklist(state)), state)
})

test('normalizeQuestion: регистр, ё и лишние пробелы не делают вопрос новым', () => {
  assert.equal(normalizeQuestion('  Когда   меняли СТОЯКИ? '), 'когда меняли стояки?')
  assert.equal(normalizeQuestion('Льва  Толстого'), normalizeQuestion('льва толстого'))
  assert.equal(normalizeQuestion('Ёлка'), normalizeQuestion('елка'))
})

test('addCustomQuestion: пустой и пробельный вопрос не добавляется', () => {
  const state = emptyChecklist()
  assert.deepEqual(addCustomQuestion(state, '', []), { ok: false, error: 'empty' })
  assert.deepEqual(addCustomQuestion(state, '    ', []), { ok: false, error: 'empty' })
  assert.deepEqual(addCustomQuestion(state, '\n\t ', []), { ok: false, error: 'empty' })
})

test('addCustomQuestion: дубль из API и своих вопросов отклоняется', () => {
  const api = [item('q-1', 'Как часто отключают горячую воду?')]
  const state = emptyChecklist()

  assert.deepEqual(
    addCustomQuestion(state, '  как ЧАСТО отключают  горячую воду? ', api.map((i) => i.question)),
    { ok: false, error: 'duplicate' },
  )

  const added = addCustomQuestion(state, 'Есть ли домофон?', [])
  assert.ok(added.ok)
  assert.deepEqual(
    addCustomQuestion(added.state, 'есть ли ДОМОФОН?', []),
    { ok: false, error: 'duplicate' },
  )
})

test('addCustomQuestion: добавляет нормализованный по краям, но исходный текст вопроса', () => {
  const result = addCustomQuestion(emptyChecklist(), '  Есть ли во дворе ПАРКОВКА?  ', [])
  assert.ok(result.ok)
  assert.equal(result.question, 'Есть ли во дворе ПАРКОВКА?')
  assert.equal(result.state.custom.length, 1)
  assert.equal(result.state.custom[0]?.question, 'Есть ли во дворе ПАРКОВКА?')
  assert.equal(
    normalizeQuestion(result.state.custom[0]?.question ?? ''),
    'есть ли во дворе парковка?',
  )
})

test('apiQuestions: дубли по тексту схлопываются, id из API сохраняются', () => {
  const items = [
    item('q-1', 'Как часто отключают горячую воду?'),
    item('q-2', 'как часто  ОТКЛЮЧАЮТ горячую воду?'),
    item('q-3', 'Кто обслуживает лифт?'),
  ]
  const unique = apiQuestions(items)
  assert.deepEqual(
    unique.map((entry) => entry.id),
    ['q-1', 'q-3'],
  )
  assert.deepEqual(unique[0]?.source_event_ids, ['event-q-1'])
})

test('computeProgress: 0/5, 3/5 и 5/5', () => {
  const ids = ['q-1', 'q-2', 'q-3', 'q-4', 'q-5']
  assert.deepEqual(computeProgress(ids, []), { checked: 0, total: 5, percent: 0 })
  assert.deepEqual(computeProgress(ids, ['q-1', 'q-3', 'q-5']), {
    checked: 3,
    total: 5,
    percent: 60,
  })
  assert.deepEqual(computeProgress(ids, ids), { checked: 5, total: 5, percent: 100 })
})

test('computeProgress: свои вопросы входят в M, пустой список — 0/0', () => {
  // Два вопроса из API и один свой: отмечен один API и свой.
  assert.deepEqual(computeProgress(['q-1', 'q-2', 'custom-1'], ['q-2', 'custom-1']), {
    checked: 2,
    total: 3,
    percent: 67,
  })
  assert.deepEqual(computeProgress([], []), { checked: 0, total: 0, percent: 0 })
})

test('computeProgress: отметки исчезнувших вопросов не раздувают счётчик', () => {
  // Вопрос удалили из API, а галочка осталась в localStorage.
  assert.deepEqual(computeProgress(['q-1', 'q-2'], ['q-1', 'q-2', 'q-9', 'q-9']), {
    checked: 2,
    total: 2,
    percent: 100,
  })
})

test('toggleChecked: снимает и ставит отметку, не теряя свои вопросы', () => {
  const state = {
    checked: ['q-1'],
    custom: [{ id: 'custom-1', question: 'Есть ли домофон?' }],
  }
  const off = toggleChecked(state, 'q-1')
  assert.deepEqual(off.checked, [])
  assert.deepEqual(off.custom, state.custom)

  const on = toggleChecked(off, 'q-1')
  assert.deepEqual(on.checked, ['q-1'])
})

test('parseChecklist: сохранённый мусор не мешает отметить вопросы заново', () => {
  const state = parseChecklist('{ broken')
  assert.deepEqual(state, emptyChecklist())
  assert.deepEqual(toggleChecked(state, 'q-1').checked, ['q-1'])
})

test('mergeRows: вопросы API идут первыми, свои добавляются после', () => {
  const rows = mergeRows(
    [item('q-1', 'Кто обслуживает лифт?')],
    [{ id: 'custom-1', question: 'Есть ли домофон?' }],
  )
  assert.deepEqual(
    rows.map((row) => [row.id, row.custom]),
    [
      ['q-1', false],
      ['custom-1', true],
    ],
  )
  assert.equal(rows[0]?.reason, 'причина q-1')
  assert.deepEqual(rows[0]?.sourceEventIds, ['event-q-1'])
  assert.equal(rows[1]?.reason, null, 'у своего вопроса причины нет')
})

test('mergeRows: своя копия вопроса, который теперь пришёл из API, не дублируется', () => {
  // Классический случай: пользователь добавил вопрос вручную, а после
  // обновления данных такой же вопрос пришёл с сервера.
  const rows = mergeRows(
    [item('q-1', 'Как часто отключают горячую воду?')],
    [{ id: 'custom-1', question: '  как ЧАСТО отключают горячую воду? ' }],
  )
  assert.equal(rows.length, 1)
  assert.equal(rows[0]?.id, 'q-1', 'остаётся версия API: у неё есть причина и события')
  assert.equal(rows[0]?.custom, false)
})

test('mergeRows: пустые вопросы отбрасываются с обеих сторон', () => {
  const rows = mergeRows(
    [item('q-1', '   ')],
    [
      { id: 'custom-1', question: '  ' },
      { id: 'custom-2', question: 'Нормальный вопрос' },
    ],
  )
  assert.deepEqual(
    rows.map((row) => row.id),
    ['custom-2'],
  )
})

test('mergeRows: исходный текст вопроса показывается без изменений', () => {
  const question = 'Когда меняли СТОЯКИ в подъезде?'
  const rows = mergeRows([], [{ id: 'custom-1', question: `  ${question}  ` }])
  assert.equal(rows[0]?.question, question)
})
