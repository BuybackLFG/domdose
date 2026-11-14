/**
 * Индекс дома и пять компонент с весами (раздел F2, DD-23).
 *
 * Числа не прячем в цвет: `score` и вес написаны текстом, полоска — только
 * подкрепление. `index === null` — валидное досье без скоринга, поэтому
 * честно пишем «не посчитан», а не рисуем ноль: ноль — это оценка, а не
 * отсутствие оценки.
 */
// Карточки оценок и выделение минимума адаптированы из FarpostMVP
// module/frontend (d6e938452ce5d23d22a63bd46ea0183ba141cff7),
// frontend/src/features/dossier/CategoryScores.tsx и WeakestCategory.tsx.
import { formatCoverage, formatDate, formatWeight } from '../../lib/format'
import { summarizeComponents, weakestComponents } from './componentsSummary'
import type { HouseIndex } from '../../types'

function ComponentRow({
  label,
  score,
  scorePct,
  weightLabel,
  explanation,
}: {
  label: string
  score: number
  scorePct: number
  weightLabel: string
  explanation: string
}) {
  return (
    <li className="space-y-2 rounded-xl border border-slate-800 bg-slate-950/40 p-3 sm:p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        <span className="text-xs text-slate-400">
          <span className="font-mono text-slate-200">{score}</span> из 100
          <span className="mx-1.5 text-slate-600">·</span>
          вес <span className="font-mono">{weightLabel}</span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800" aria-hidden="true">
        <div className="h-full rounded-full bg-emerald-500/80" style={{ width: `${scorePct}%` }} />
      </div>
      <p className="text-xs leading-relaxed text-slate-400">{explanation}</p>
    </li>
  )
}

export function IndexPanel({ index }: { index: HouseIndex | null }) {
  if (!index) {
    return (
      <section
        aria-labelledby="dossier-index-title"
        className="space-y-2 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-6"
      >
        <h2 id="dossier-index-title" className="text-sm font-semibold text-slate-300">
          Индекс дома
        </h2>
        <p className="text-sm text-slate-400">
          Индекс пока не посчитан — данных для оценки не хватает. Досье без индекса
          валидно: факты и источники ниже всё равно проверяемы.
        </p>
      </section>
    )
  }

  const { rows, totalWeight } = summarizeComponents(index.components)
  const weakest = weakestComponents(rows)

  return (
    <section
      aria-labelledby="dossier-index-title"
      className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-4"
    >
      <h2 id="dossier-index-title" className="text-sm font-semibold text-slate-300">
        Индекс дома
      </h2>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="font-mono text-4xl leading-none text-emerald-300">{index.total}</p>
        <p className="text-sm text-slate-400">из 100 по открытым данным</p>
      </div>

      {weakest.length > 0 && (
        <aside aria-labelledby="weakest-components-title" className="rounded-xl border border-amber-800/50 bg-amber-950/20 p-4">
          <h3 id="weakest-components-title" className="text-sm font-semibold text-amber-200">
            {weakest.length === 1 ? 'Самая низкая оценка' : 'Самые низкие оценки'}
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-200">
            {weakest.map((row) => `${row.label} — ${row.score} из 100`).join('; ')}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">
            Среди компонентов индекса по доступным данным.
          </p>
        </aside>
      )}

      <ul className="grid gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <ComponentRow
            key={row.key}
            label={row.label}
            score={row.score}
            scorePct={row.scorePct}
            weightLabel={formatWeight(row.weight)}
            explanation={row.explanation}
          />
        ))}
      </ul>

      <p className="border-t border-slate-800 pt-3 text-xs text-slate-400">
        Покрытие данных: <span className="font-mono text-slate-200">{formatCoverage(index.coverage)}</span>
        <span className="text-slate-600"> · </span>
        сумма весов <span className="font-mono">{formatWeight(totalWeight)}</span>
      </p>

      {index.coverage_note !== null && index.coverage_note !== undefined && (
        <p className="text-xs text-amber-200/90">{index.coverage_note}</p>
      )}

      <p className="text-xs text-slate-500">Посчитан {formatDate(index.computed_at)}</p>
    </section>
  )
}
