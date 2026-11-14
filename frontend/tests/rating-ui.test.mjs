import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const compiled = await build({
  entryPoints: ['src/features/dossier/RatingPanel.tsx'], bundle: true, write: false,
  platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime'],
})
const module = { exports: {} }
new Function('require', 'module', 'exports', compiled.outputFiles[0].text)(require, module, module.exports)
const { RatingPanel } = module.exports

const report = {
  window: { start: '2025-11-14T00:00:00+10:00', end_exclusive: '2026-11-14T00:00:00+10:00' },
  houses: [{ overall: null, categories: [
    { type: 'electricity', score: null, reason: 'BASELINE_UNAVAILABLE', metrics: { maximum: 3.5 } },
    { type: 'heating', score: null, reason: 'UNKNOWN_SERVICE', metrics: { maximum: null } },
  ] }],
  source_spans: [{ type: 'electricity', intervals: [{ start: '2026-09-01', end: '2026-11-13' }], gaps: [{ start: '2025-11-14', end: '2026-08-31' }], unknown_source_ids: ['unknown'] }],
  limitations: ['Источник один'],
}

test('неполный отчёт показывает причину, окно, покрытие и ограничения без выдуманной оценки', () => {
  const html = renderToStaticMarkup(React.createElement(RatingPanel, { rating: report }))
  assert.match(html, /Общая оценка недоступна/)
  assert.match(html, /Нет данных для сравнения со средним по городу/)
  assert.match(html, /Нет подтверждённых данных об услуге/)
  assert.match(html, /14 ноября 2025/)
  assert.match(html, /14 ноября 2026/)
  assert.match(html, /Пробелы:/)
  assert.match(html, /покрытие неизвестно/)
  assert.match(html, /Источник один/)
  assert.match(html, /Наибольшая взвешенная продолжительность: 3,5 ч/)
  assert.doesNotMatch(html, /0 из 100/)
})

test('доступная приблизительная оценка не называется точной', () => {
  const html = renderToStaticMarkup(React.createElement(RatingPanel, { rating: { ...report, houses: [{ overall: 0.73, categories: [] }] } }))
  assert.match(html, /Приблизительная оценка: 73 из 100/)
})
