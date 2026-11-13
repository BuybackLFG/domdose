/**
 * Индекс дома и пять компонент с весами.
 *
 * Раздел F2 (DD-23). Заглушка: настоящая вёрстка, объяснения и дисклеймер —
 * в этой же задаче.
 */
import type { HouseIndex } from '../../types'

export function IndexPanel({ index }: { index: HouseIndex | null }) {
  if (!index) {
    return (
      <section className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-6 text-sm text-slate-400">
        Индекс ещё не посчитан: досье без индекса валидно.
      </section>
    )
  }
  return (
    <section className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-4">
      <h2 className="text-sm font-semibold text-slate-300">Индекс дома</h2>
      <p className="font-mono text-3xl text-emerald-300">{index.total}</p>
      <ul className="space-y-1 text-sm text-slate-400">
        {index.components.map((component) => (
          <li key={component.key}>
            {component.label}: {component.score}
          </li>
        ))}
      </ul>
    </section>
  )
}
