/**
 * Группировка фактов по `FactType` — без React.
 *
 * Факты приходят одним плоским списком, а читателю нужны разделы. Порядок
 * групп берём по первому появлению в ответе API: backend уже упорядочил факты
 * осмысленно, и навязывать свой порядок значило бы терять эту информацию.
 * `legal` — такая же группа, как остальные, и не должна пропадать.
 */
import type { Fact, FactType } from '../../types'

export const FACT_TYPE_LABELS: Record<FactType, string> = {
  building: 'Дом и конструктив',
  communications: 'Коммуникации',
  nature: 'Природа и экология',
  transport: 'Транспорт',
  safety: 'Безопасность',
  legal: 'Юридический статус',
}

export interface FactGroup {
  type: FactType
  /** Человеческий заголовок группы; неизвестный тип показываем как есть. */
  title: string
  facts: Fact[]
}

/** Пустой вход → пустой массив: секция без фактов не рисуется вовсе. */
export function groupFacts(facts: readonly Fact[]): FactGroup[] {
  const groups = new Map<FactType, Fact[]>()

  for (const fact of facts) {
    const bucket = groups.get(fact.type)
    if (bucket) {
      bucket.push(fact)
    } else {
      groups.set(fact.type, [fact])
    }
  }

  return [...groups].map(([type, grouped]) => ({
    type,
    title: FACT_TYPE_LABELS[type] ?? type,
    facts: grouped,
  }))
}

/**
 * Короткая подпись ссылки на источник: хост без `www.`.
 *
 * Полный URL в тексте ссылки ломает вёрстку на 375 px, а «источник» подряд
 * десять раз бесполезен для скринридера. Если URL битый — отдаём его как есть,
 * ссылку всё равно рисуем по исходному `source_url`.
 */
export function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
