/**
 * Факты о доме, сгруппированные по типу (раздел F2, DD-23).
 *
 * У каждого факта обязателен `source_url` — это требование эпика B: без
 * ссылки досье превращается в непроверяемые утверждения. Поэтому ссылка идёт
 * рядом со значением, а не отдельным разделом.
 *
 * Пустой список фактов не рисует секцию вообще: заголовок без содержимого
 * выглядит как сломанный блок, а не как «данных нет».
 */
import { useId } from 'react'

import { formatDate } from '../../lib/format'
import { groupFacts, sourceHost } from './factGroups'
import type { Fact } from '../../types'

function FactRow({ fact }: { fact: Fact }) {
  return (
    <li className="space-y-0.5 py-1.5">
      <p className="text-sm text-slate-200">
        <span className="text-slate-400">{fact.label}:</span> {fact.value}
      </p>
      <p className="text-xs text-slate-500">
        <a
          href={fact.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="break-all text-slate-300 underline underline-offset-4 hover:text-emerald-300"
        >
          {sourceHost(fact.source_url)}
        </a>
        <span className="mx-1.5 text-slate-600">·</span>
        <time dateTime={fact.retrieved_at}>{formatDate(fact.retrieved_at)}</time>
      </p>
    </li>
  )
}

export function FactsSection({ facts }: { facts: Fact[] }) {
  const groups = groupFacts(facts)
  const headingId = useId()

  if (groups.length === 0) return null

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <h2 id={headingId} className="text-sm font-semibold text-slate-300">
        Факты
      </h2>
      <div className="space-y-3">
        {groups.map((group) => (
          <section key={group.type} className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
            <h3 className="mb-1 text-xs font-semibold tracking-wide text-slate-400 uppercase">
              {group.title}
            </h3>
            <ul className="divide-y divide-slate-800/70">
              {group.facts.map((fact) => (
                <FactRow key={fact.id} fact={fact} />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </section>
  )
}
