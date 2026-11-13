// ФИКСТУРЫ ДЛЯ РАЗРАБОТКИ, НЕ РЕАЛЬНЫЕ ДАННЫЕ.
//
// Пока backend отвечает 501 (B1/B2 не реализованы), фронтенд разрабатывается
// против этих записей. Адреса и районы взяты из `data/shortlist.md` (DD-6),
// а `index` и компоненты — синтетические: они нужны только чтобы UI показывал
// все ветки, и в демо их показывать нельзя.
//
// Включается флагом: `VITE_USE_MOCKS=true npm run dev`.
import type { ComponentBrief, HouseList, HouseSummary } from '../types'
import { normalizeQuery } from '../lib/normalize'

/** [id, address, district, syntheticIndex] */
const BASE = [
  ['svetlanskaya-37', 'Светланская, 37', 'Ленинский', 74],
  ['fokina-8', 'Адмирала Фокина, 8', 'Фрунзенский', 61],
  ['bestuzheva-46', 'Бестужева, 46', 'Фрунзенский', 55],
  ['svetlanskaya-155', 'Светланская, 155', 'Ленинский', 68],
  ['svetlanskaya-173', 'Светланская, 173', 'Ленинский', 70],
  ['svetlanskaya-143', 'Светланская, 143', 'Ленинский', 52],
  ['russkaya-65a', 'Русская, 65А', 'Советский', 58],
  ['tukhachevskogo-44', 'Тухачевского, 44', 'Первореченский', 63],
  ['shilkinskaya-11', 'Шилкинская, 11', 'Ленинский', 49],
  ['shoshina-17a', 'Шошина, 17А', 'Первореченский', 54],
  ['shoshina-25a', 'Шошина, 25А', 'Первореченский', 57],
  ['volkhovskaya-27', 'Волховская, 27', 'Первореченский', 59],
  ['nevskaya-33', 'Невская, 33', 'Первореченский', 62],
  ['sochinskaya-17', 'Сочинская, 17', 'Первомайский', 81],
  ['basargina-2', 'Басаргина, 2', 'Первомайский', 47],
  ['basargina-6b-1', 'Басаргина, 6Б корп. 1', 'Первомайский', 84],
  ['basargina-6b-2', 'Басаргина, 6Б корп. 2', 'Первомайский', 83],
  ['basargina-15', 'Басаргина, 15', 'Первомайский', 76],
  ['basargina-32', 'Басаргина, 32', 'Первомайский', 79],
  ['basargina-42v', 'Басаргина, 42В', 'Первомайский', 77],
  ['basargina-46', 'Басаргина, 46', 'Первомайский', 66],
  ['mozhayskaya-20', 'Можайская, 20', 'Первомайский', 72],
  ['mozhayskaya-22', 'Можайская, 22', 'Первомайский', 73],
  ['mozhayskaya-24', 'Можайская, 24', 'Первомайский', 71],
  ['sipyagina-28', 'Сипягина, 28', 'Фрунзенский', 64],
  ['krygina-42a', 'Крыгина, 42А', 'Фрунзенский', 67],
  ['krygina-80', 'Крыгина, 80', 'Фрунзенский', 51],
  ['leonova-25', 'Леонова, 25', 'Фрунзенский', 45],
  ['leonova-70', 'Леонова, 70', 'Фрунзенский', 60],
] as const satisfies ReadonlyArray<readonly [string, string, string, number]>

const COMPONENTS = [
  ['communications', 'Коммуникации', 4],
  ['nature', 'Природа', -3],
  ['building', 'Дом', 6],
  ['transport', 'Транспорт', -6],
  ['safety', 'Безопасность', 2],
] as const satisfies ReadonlyArray<readonly [string, string, number]>

function clamp(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)))
}

function syntheticComponents(total: number): ComponentBrief[] {
  return COMPONENTS.map(([key, label, offset]) => ({ key, label, score: clamp(total + offset) }))
}

export const MOCK_SUMMARIES: HouseSummary[] = BASE.map(([id, address, district, index]) => ({
  id,
  address,
  district,
  index,
  components: syntheticComponents(index),
}))

/** Задержка, чтобы в dev были видны состояния загрузки и гонки ответов. */
const LATENCY_MS = 260

function wait(ms: number, signal: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('aborted', 'AbortError'))
      return
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    function onAbort(): void {
      clearTimeout(timer)
      reject(new DOMException('aborted', 'AbortError'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

export async function mockSearchHouses(
  query: string,
  signal: AbortSignal | null = null,
): Promise<HouseList> {
  await wait(LATENCY_MS, signal)
  const needle = normalizeQuery(query)
  const items = needle
    ? MOCK_SUMMARIES.filter(
        (house) =>
          normalizeQuery(house.address).includes(needle) ||
          normalizeQuery(house.district).includes(needle),
      )
    : MOCK_SUMMARIES
  return {
    items,
    total: items.length,
    query: needle,
    retrieved_at: '2026-11-13',
  }
}
