/** Подсветка совпадения с запросом. Логика поиска совпадения — в `lib/normalize.ts`. */
import type { ReactNode } from 'react'

import { findMatch } from '../../lib/normalize'

export function Highlight({ text, query }: { text: string; query: string }): ReactNode {
  const match = findMatch(text, query)
  if (!match) return text
  return (
    <>
      {text.slice(0, match.start)}
      <mark className="rounded bg-amber-300/25 px-0.5 text-amber-100">
        {text.slice(match.start, match.end)}
      </mark>
      {text.slice(match.end)}
    </>
  )
}
