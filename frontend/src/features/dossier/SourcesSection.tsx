/**
 * Источники досье и дисклеймер.
 *
 * Раздел F2 (DD-23). Заглушка.
 */
import type { Source } from '../../types'

export function SourcesSection({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null
  return (
    <section className="space-y-2 border-t border-slate-800 pt-4">
      <h2 className="text-sm font-semibold text-slate-300">Источники</h2>
      <ul className="space-y-1 text-sm text-slate-400">
        {sources.map((source) => (
          <li key={source.url}>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-4 hover:text-slate-200"
            >
              {source.name}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
