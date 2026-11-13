import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DossierPage } from '../features/dossier/DossierPage';
import type {
  HouseDetailResponse,
  HouseEvent,
  HouseListResponse,
  HouseSummary,
} from '../features/dossier/types';

vi.mock('../features/dossier/HouseMap', () => ({
  HouseMap: () => <div data-testid="house-map" />,
}));

vi.mock('../features/dossier/pilotHouses', () => ({
  PILOT_HOUSES: Array.from({ length: 20 }, (_, index) => {
    const number = index + 1;
    return {
      house_id: `house_${String(number).padStart(6, '0')}`,
      address: `Владивосток, Тестовая ${Math.ceil(number / 2)} улица, дом ${number}`,
      district: 'Ленинский',
      lat: 43.1 + number / 1000,
      lon: 131.9 + number / 1000,
      coordinate_source: 'osm_building_way_centroid',
      osm_way_id: 1000 + number,
    };
  }),
}));

const SCOPE = { kind: 'pilot', house_count: 20, average_basis: 'pilot_only' } as const;
const WINDOW = {
  start: '2026-10-14T00:00:00+10:00',
  end: '2026-11-13T00:00:00+10:00',
} as const;

function houseAddress(number: number): string {
  return `Владивосток, Тестовая ${Math.ceil(number / 2)} улица, дом ${number}`;
}

function houseId(number: number): HouseSummary['house_id'] {
  return `house_${String(number).padStart(6, '0')}`;
}

function makeHouse(number: number): HouseSummary {
  return { house_id: houseId(number), address: houseAddress(number), overall_score: 0.8 };
}

function makeList(): HouseListResponse {
  return {
    scope: SCOPE,
    window: WINDOW,
    houses: Array.from({ length: 20 }, (_, index) => makeHouse(index + 1)),
  };
}

function makeCategory(score: number) {
  return {
    metrics: { frequency: 0, hours: 0, longest: 0 },
    penalties: { frequency: 0, hours: 0, longest: 0 },
    score,
  };
}

function makeEvent(overrides: Partial<HouseEvent> = {}): HouseEvent {
  return {
    house_id: houseId(1),
    category: 'electricity',
    started_at: '2026-10-14T10:00:00+10:00',
    ended_at: '2026-10-14T12:00:00+10:00',
    kind: 'emergency',
    is_mass: false,
    is_natural_disaster: false,
    source_url: 'https://source.test/event/1',
    ...overrides,
  };
}

function makeDetail(
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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

type FetchHandler = (url: string, init?: RequestInit) => Promise<Response>;

function installFetch(handler: FetchHandler) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => (
    handler(requestUrl(input), init)
  ));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function successfulHandler(url: string): Promise<Response> {
  if (url.endsWith('/api/houses')) return Promise.resolve(jsonResponse(makeList()));
  const match = url.match(/\/api\/houses\/(house_(\d{6}))$/);
  if (match) return Promise.resolve(jsonResponse(makeDetail(Number(match[2]))));
  return Promise.resolve(jsonResponse({ error: { code: 'not_found', message: 'not found' } }, 404));
}

async function renderLoadedPage() {
  const fetchMock = installFetch((url) => successfulHandler(url));
  render(<DossierPage />);
  expect(await screen.findByRole('heading', { name: houseAddress(1) })).toBeInTheDocument();
  expect(await screen.findByText(/В использованном источнике нет зафиксированных отключений/i))
    .toBeInTheDocument();
  return fetchMock;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('загрузка списка и detail', () => {
  it('показывает list loading и не подменяет его нулевым рейтингом', () => {
    const pending = deferred<Response>();
    installFetch(() => pending.promise);
    render(<DossierPage />);
    expect(screen.getAllByText(/Загру(жаем|зка)/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Общий рейтинг:\s*0/i)).not.toBeInTheDocument();
  });

  it('различает list network error и предлагает повторить запрос', async () => {
    installFetch(() => Promise.reject(new TypeError('Failed to fetch')));
    render(<DossierPage />);
    expect(await screen.findByText(/Не удалось связаться с сервером/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Повторить/i })).toBeInTheDocument();
  });

  it('показывает list no-data для dataset_unavailable, а не network error', async () => {
    installFetch(() => Promise.resolve(jsonResponse({
      error: { code: 'dataset_unavailable', message: 'dataset unavailable' },
    }, 503)));
    render(<DossierPage />);
    expect(await screen.findByText(/Исходные данные недоступны/i)).toBeInTheDocument();
    expect(screen.getByText(/Рейтинг не рассчитан/i)).toBeInTheDocument();
    expect(screen.queryByText(/Не удалось связаться с сервером/i)).not.toBeInTheDocument();
  });

  it('показывает detail loading рядом с новым адресом без прежнего досье', async () => {
    const detail = deferred<Response>();
    installFetch((url) => (
      url.endsWith('/api/houses')
        ? Promise.resolve(jsonResponse(makeList()))
        : detail.promise
    ));
    render(<DossierPage />);
    expect(await screen.findByRole('heading', { name: houseAddress(1) })).toBeInTheDocument();
    expect(screen.getByText(/Загружаем досье/i)).toBeInTheDocument();
  });

  it('показывает detail network error', async () => {
    installFetch((url) => (
      url.endsWith('/api/houses')
        ? Promise.resolve(jsonResponse(makeList()))
        : Promise.reject(new TypeError('Failed to fetch'))
    ));
    render(<DossierPage />);
    expect(await screen.findByText(/Не удалось загрузить досье/i)).toBeInTheDocument();
  });

  it('показывает detail no-data и не рисует численный рейтинг', async () => {
    installFetch((url) => (
      url.endsWith('/api/houses')
        ? Promise.resolve(jsonResponse(makeList()))
        : Promise.resolve(jsonResponse({
          error: { code: 'dataset_unavailable', message: 'dataset unavailable' },
        }, 503))
    ));
    render(<DossierPage />);
    expect(await screen.findByText(/Исходные данные недоступны/i)).toBeInTheDocument();
    expect(screen.getByText(/Рейтинг не рассчитан/i)).toBeInTheDocument();
    expect(screen.queryByText(/Общий рейтинг:\s*0/i)).not.toBeInTheDocument();
  });
});

describe('выбор дома и устаревшие ответы', () => {
  it('отменяет A при A→B и игнорирует даже поздно разрешённый ответ A', async () => {
    const a = deferred<Response>();
    const b = deferred<Response>();
    const signals = new Map<number, AbortSignal | undefined>();
    installFetch((url, init) => {
      if (url.endsWith('/api/houses')) return Promise.resolve(jsonResponse(makeList()));
      if (url.endsWith(`/api/houses/${houseId(1)}`)) {
        signals.set(1, init?.signal ?? undefined);
        return a.promise;
      }
      if (url.endsWith(`/api/houses/${houseId(2)}`)) {
        signals.set(2, init?.signal ?? undefined);
        return b.promise;
      }
      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });

    render(<DossierPage />);
    expect(await screen.findByRole('heading', { name: houseAddress(1) })).toBeInTheDocument();
    await waitFor(() => expect(signals.has(1)).toBe(true));

    fireEvent.click(screen.getByRole('button', { name: new RegExp(houseAddress(2)) }));
    await waitFor(() => expect(signals.has(2)).toBe(true));
    expect(signals.get(1)?.aborted).toBe(true);

    await act(async () => {
      b.resolve(jsonResponse(makeDetail(2)));
      await b.promise;
    });
    expect(await screen.findByRole('heading', { name: houseAddress(2) })).toBeInTheDocument();

    await act(async () => {
      a.resolve(jsonResponse(makeDetail(1)));
      await a.promise;
    });
    expect(screen.getByRole('heading', { name: houseAddress(2) })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: houseAddress(1) })).not.toBeInTheDocument();
  });
});

describe('поиск и combobox', () => {
  it('показывает not-covered и сохраняет текущее досье', async () => {
    await renderLoadedPage();
    const input = screen.getByRole('combobox', { name: /адрес/i });
    fireEvent.change(input, { target: { value: 'Несуществующая 999' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(await screen.findByText(/не входит/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: houseAddress(1) })).toBeInTheDocument();
  });

  it('не делает fetch для URL объявления', async () => {
    const fetchMock = await renderLoadedPage();
    const input = screen.getByRole('combobox', { name: /адрес/i });
    fireEvent.change(input, { target: { value: 'https://example.test/listing/42' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(await screen.findByText(/не открываются и не проверяются онлайн/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [request] of fetchMock.mock.calls) {
      expect(requestUrl(request)).not.toContain('example.test');
    }
  });

  it('выбирает второй из двух результатов стрелкой и Enter', async () => {
    await renderLoadedPage();
    const input = screen.getByRole('combobox', { name: /адрес/i });
    fireEvent.change(input, { target: { value: 'Тестовая 10' } });

    const options = await screen.findAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent(houseAddress(19));
    expect(options[1]).toHaveTextContent(houseAddress(20));

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(await screen.findByRole('heading', { name: houseAddress(20) })).toBeInTheDocument();
  });
});

describe('события и weakest', () => {
  it('показывает честное no-events при доступных исходных данных', async () => {
    await renderLoadedPage();
    expect(screen.getByText(/не доказывает их отсутствие/i)).toBeInTheDocument();
  });

  it('показывает события строго в порядке ответа API и ended_at null как продолжающееся', async () => {
    const olderOngoing = makeEvent({
      category: 'electricity',
      started_at: '2026-10-14T10:00:00+10:00',
      ended_at: null,
      source_url: 'https://source.test/event/older',
    });
    const newer = makeEvent({
      category: 'heating',
      started_at: '2026-11-01T10:00:00+10:00',
      ended_at: '2026-11-01T12:00:00+10:00',
      source_url: 'https://source.test/event/newer',
    });
    const middle = makeEvent({
      category: 'cold_water',
      started_at: '2026-10-20T10:00:00+10:00',
      ended_at: '2026-10-20T12:00:00+10:00',
      source_url: 'https://source.test/event/middle',
    });
    // Порядок намеренно не монотонен по started_at: любая сортировка во frontend его меняет.
    installFetch((url) => (
      url.endsWith('/api/houses')
        ? Promise.resolve(jsonResponse(makeList()))
        : Promise.resolve(jsonResponse(makeDetail(1, { events: [olderOngoing, newer, middle] })))
    ));
    render(<DossierPage />);

    const eventList = await screen.findByRole('list', { name: /События дома/i });
    const items = within(eventList).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('Электричество');
    expect(items[0]).toHaveTextContent('Продолжается');
    expect(items[1]).toHaveTextContent('Отопление');
    expect(items[1]).not.toHaveTextContent('Продолжается');
    expect(items[2]).toHaveTextContent('Холодная вода');
  });

  it('берёт weakest из DTO и не вычисляет минимум категории самостоятельно', async () => {
    installFetch((url) => (
      url.endsWith('/api/houses')
        ? Promise.resolve(jsonResponse(makeList()))
        : Promise.resolve(jsonResponse(makeDetail(1, { weakest: 'cold_water' })))
    ));
    render(<DossierPage />);

    const heading = await screen.findByRole('heading', { name: /Худшая категория/i });
    const section = heading.closest('section');
    if (!section) throw new Error('WeakestCategory должен быть semantic section');
    expect(section).toHaveTextContent('Холодная вода');
    expect(section).not.toHaveTextContent('Отопление');
  });
});
