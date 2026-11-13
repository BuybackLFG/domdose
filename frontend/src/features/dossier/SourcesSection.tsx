/**
 * Источники досье (раздел F2, DD-23).
 *
 * Здесь только то, что пришло в `sources`: имя, ссылка, дата получения.
 * Ссылки внешние, поэтому `target="_blank"` обязателен вместе с
 * `rel="noopener noreferrer"` — иначе новая вкладка получает доступ к
 * `window.opener`.
 */
import { useId } from 'react'

import { formatDate } from '../../lib/format'
import { sourceHost } from './factGroups'
import type { Source } from '../../types'

export function SourcesSection({ sources }: { sources: Source[] }) {
  const headingId = useId()

  if (sources.length === 0) return null

  return (
    <section aria-labelledby={headingId} className="space-y-2 border-t border-slate-800 pt-4">
      <h2 id={headingId} className="text-sm font-semibold text-slate-300">
        Источники
      </h2>
      <ul className="space-y-2 text-sm">
        {sources.map((source) => (
          <li key={source.url} className="space-y-0.5">
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="break-words text-slate-200 underline underline-offset-4 hover:text-emerald-300"
            >
              {source.name}
            </a>
            <p className="break-all text-xs text-slate-500">
              {sourceHost(source.url)}
              <span className="mx-1.5 text-slate-600">·</span>
              <time dateTime={source.retrieved_at}>{formatDate(source.retrieved_at)}</time>
            </p>
          </li>
        ))}
      </ul>
    </section>
  )
}
