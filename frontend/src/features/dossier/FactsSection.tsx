/**
 * Факты о доме со ссылкой на источник у каждого.
 *
 * Раздел F2 (DD-23). Заглушка.
 */
import type { Fact } from '../../types'

export function FactsSection({ facts }: { facts: Fact[] }) {
  if (facts.length === 0) return null
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-300">Факты</h2>
      <ul className="space-y-1 text-sm text-slate-400">
        {facts.map((fact) => (
          <li key={fact.id}>
            {fact.label}: {fact.value}
          </li>
        ))}
      </ul>
    </section>
  )
}
