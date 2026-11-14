import { vi } from 'vitest';
import type {
  CategoryDetail,
  HouseDetailResponse,
  HouseEvent,
  HouseId,
  HouseListResponse,
  UtilityCategory,
} from '../features/dossier/types';

/** Искусственные fixtures страницы досье; реальных адресов и событий нет. */
export const SCOPE = { kind: 'pilot', house_count: 20, average_basis: 'pilot_only' } as const;
export const WINDOW = {
  start: '2026-10-14T00:00:00+10:00',
  end: '2026-11-13T00:00:00+10:00',
} as const;

export function houseAddress(number: number): string {
  return `Владивосток, Тестовая ${Math.ceil(number / 2)} улица, дом ${number}`;
}

export function houseId(number: number): HouseId {
  return `house_${String(number).padStart(6, '0')}`;
}

/** Каталог для vi.mock pilotHouses: 20 искусственных домов. */
export function fakeGeoCatalog() {
  return Array.from({ length: 20 }, (_, index) => {
    const number = index + 1;
    return {
      house_id: houseId(number),
      address: houseAddress(number),
      district: 'Ленинский',
      lat: 43.1 + number / 1000,
      lon: 131.9 + number / 1000,
      coordinate_source: 'osm_building_way_centroid',
      osm_way_id: 1000 + number,
    };
  });
}

export function makeList(): HouseListResponse {
  return {
    scope: SCOPE,
    window: WINDOW,
    houses: Array.from({ length: 20 }, (_, index) => ({
      house_id: houseId(index + 1),
      address: houseAddress(index + 1),
      overall_score: 0.8,
    })),
  };
}

export function makeCategory(score: number): CategoryDetail {
  return {
    metrics: { frequency: 0, hours: 0, longest: 0 },
    penalties: { frequency: 0, hours: 0, longest: 0 },
    score,
  };
}

export function makeDetail(
  number: number,
  overrides: Partial<HouseDetailResponse> = {},
): HouseDetailResponse {
  return {
    scope: SCOPE,
    window: WINDOW,
    house_id: houseId(number),
    address: houseAddress(number),
    overall_score: 0.8,
    categories: {
      hot_water: makeCategory(0.91),
      cold_water: makeCategory(0.82),
      electricity: makeCategory(0.73),
      heating: makeCategory(0.64),
    },
    weakest: 'heating',
    events: [],
    ...overrides,
  };
}

/**
 * 13 искусственных событий дома, отсортированных от новых к старым:
 * электричество 6, отопление 4, холодная вода 3, горячая вода 0.
 */
export const EVENT_CATEGORY_SEQUENCE: readonly UtilityCategory[] = [
  'electricity', 'heating', 'electricity', 'cold_water', 'electricity',
  'heating', 'electricity', 'cold_water', 'electricity', 'heating',
  'electricity', 'cold_water', 'heating',
];

export function makeEvents(number: number): HouseEvent[] {
  return EVENT_CATEGORY_SEQUENCE.map((category, index) => {
    const start = new Date(Date.parse('2026-11-12T09:00:00+10:00') - index * 2 * 86_400_000);
    const end = new Date(start.getTime() + (index + 1) * 3_600_000);
    return {
      house_id: houseId(number),
      category,
      started_at: start.toISOString(),
      ended_at: end.toISOString(),
      kind: index % 3 === 0 ? 'planned' : 'emergency',
      is_mass: index % 4 === 1,
      is_natural_disaster: index % 5 === 2,
      source_url: `https://source.test/house/${number}/event/${index}`,
    };
  });
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

export function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

export type FetchHandler = (url: string, init?: RequestInit) => Promise<Response>;

export function installFetch(handler: FetchHandler) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => (
    handler(requestUrl(input), init)
  ));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** Обработчик /api: список и detail через фабрику по номеру дома. */
export function apiHandler(detailFor: (number: number) => HouseDetailResponse): FetchHandler {
  return (url) => {
    if (url.endsWith('/api/houses')) return Promise.resolve(jsonResponse(makeList()));
    const match = url.match(/\/api\/houses\/house_(\d{6})$/);
    if (match) return Promise.resolve(jsonResponse(detailFor(Number(match[1]))));
    return Promise.resolve(jsonResponse({ error: { code: 'not_found', message: 'not found' } }, 404));
  };
}
