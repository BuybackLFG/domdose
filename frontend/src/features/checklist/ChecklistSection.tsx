/**
 * Чек-лист вопросов продавцу.
 *
 * Раздел F4 (DD-25). Заглушка: чекбоксы, прогресс, localStorage, свои вопросы
 * и сброс — задача DD-25.
 */
import type { ChecklistItem } from '../../types'

export function ChecklistSection({
  houseId,
  items,
}: {
  houseId: string
  items: ChecklistItem[]
}) {
  if (items.length === 0) return null
  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-slate-300">Вопросы продавцу</h2>
      <ul className="space-y-1 text-sm text-slate-400">
        {items.map((item) => (
          <li key={item.id} data-house-id={houseId}>
            {item.question}
          </li>
        ))}
      </ul>
    </section>
  )
}
