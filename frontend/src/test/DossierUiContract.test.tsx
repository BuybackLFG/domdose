import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, describe, expect, it, vi } from 'vitest';
import { DossierPage } from '../features/dossier/DossierPage';
import type { HouseDetailResponse, UtilityCategory } from '../features/dossier/types';
import {
  apiHandler,
  deferred,
  houseAddress,
  installFetch,
  jsonResponse,
  makeCategory,
  makeDetail,
  makeEvents,
  makeList,
  type FetchHandler,
} from './dossierFixtures';
import {
  deepestElementsContaining,
  expectNoForbiddenFragments,
  hiddenFromSightReason,
  normalizeText,
} from './uiText';

// Браузер вне Владивостока: даты обязаны форматироваться в Asia/Vladivostok явно.
const timezone = vi.hoisted(() => {
  const previous = process.env.TZ;
  process.env.TZ = 'UTC';
  return { previous };
});

afterAll(() => {
  if (timezone.previous === undefined) delete process.env.TZ;
  else process.env.TZ = timezone.previous;
});

vi.mock('../features/dossier/HouseMap', () => ({
  HouseMap: () => <div data-testid="house-map" />,
}));

vi.mock('../features/dossier/pilotHouses', async (importOriginal) => {
  const { fakeGeoCatalog } = await import('./dossierFixtures');
  return {
    ...(await importOriginal<Record<string, unknown>>()),
    PILOT_HOUSES: fakeGeoCatalog(),
  };
});

const HEADER_NOTE = 'Приближённые данные по публичным объявлениям об отключениях. '
  + 'Дома сравниваются между собой, а не со всем Владивостоком.';
const PERIOD = '14 окт. 2026 г. – 13 нояб. 2026 г.';
const METRIC_EXPLANATIONS = [
  'Частота — сколько раз отключали за 30 дней. Аварийное отключение считается за 1, '
    + 'плановое — за 0,4; массовое или стихийное — вдвое меньше.',
  'Часы — суммарная длительность отключений за 30 дней с теми же весами.',
  'Максимум — наибольшая длительность одного отключения после умножения на его вес, в часах.',
  'Оценка категории: 100 — не хуже среднего по всем домам; чем сильнее дом превышает '
    + 'среднее, тем ниже оценка.',
];
const FILTER_LABELS = ['Все', 'Горячая вода', 'Холодная вода', 'Электричество', 'Отопление'];
const EMPTY_CATEGORY_TEXT = 'Нет событий этой категории за период.';
const NO_EVENTS = /нет зафиксированных отключений/i;

function renderWith(handler: FetchHandler) {
  const fetchMock = installFetch(handler);
  render(<DossierPage />);
  return fetchMock;
}

async function renderLoaded(detailFor: (number: number) => HouseDetailResponse) {
  const fetchMock = renderWith(apiHandler(detailFor));
  expect(await screen.findByRole('heading', { name: houseAddress(1) })).toBeInTheDocument();
  return fetchMock;
}

/** Единственный самый глубокий элемент с точным нормализованным текстом. */
function exactTextElement(root: Element, text: string): Element {
  const found = deepestElementsContaining(root, text);
  expect(found.map((element) => normalizeText(element.textContent ?? ''))).toEqual([
    normalizeText(text),
  ]);
  return found[0];
}

function expectSeen(element: Element) {
  expect(hiddenFromSightReason(element), normalizeText(element.textContent ?? '')).toBeNull();
  expect(element).toBeVisible();
}

function sectionOf(heading: HTMLElement): HTMLElement {
  const section = heading.closest('section');
  if (!section) throw new Error(`Нет section у заголовка «${heading.textContent}»`);
  return section;
}

function eventsSection(): HTMLElement {
  return sectionOf(screen.getByRole('heading', { name: /События дома/i }));
}

function categoriesSection(): HTMLElement {
  return sectionOf(screen.getByRole('heading', { name: /Оценки категорий/i }));
}

/** source_url показанных событий в порядке отображения. */
function shownEventUrls(): string[] {
  const list = screen.queryByRole('list', { name: /События дома/i });
  if (!list) return [];
  return within(list).queryAllByRole('listitem').map((item) => {
    const links = item.querySelectorAll('a[href]');
    if (links.length !== 1) throw new Error(`У события ${links.length} ссылок на источник`);
    return links[0].getAttribute('href') ?? '';
  });
}

function expectedUrls(number: number, category?: UtilityCategory): string[] {
  return makeEvents(number)
    .filter((event) => category === undefined || event.category === category)
    .map((event) => event.source_url);
}

function filterGroup(): HTMLElement {
  return within(eventsSection()).getByRole('group', { name: 'Фильтр событий' });
}

function chooseFilter(label: string) {
  fireEvent.click(within(filterGroup()).getByRole('button', { name: label }));
}

function showMoreButton(): HTMLElement | null {
  return within(eventsSection()).queryByRole('button', { name: 'Показать ещё' });
}

function clickShowMore() {
  const button = showMoreButton();
  if (!button) throw new Error('Нет кнопки «Показать ещё»');
  fireEvent.click(button);
}

function withEvents(number: number) {
  return makeDetail(number, { events: makeEvents(number) });
}

function allScores(score: number, overrides: Partial<Record<UtilityCategory, number>> = {}) {
  return {
    hot_water: makeCategory(overrides.hot_water ?? score),
    cold_water: makeCategory(overrides.cold_water ?? score),
    electricity: makeCategory(overrides.electricity ?? score),
    heating: makeCategory(overrides.heating ?? score),
  };
}

describe('шапка, список и поиск', () => {
  it('показывает заголовок и видимую честную пометку о приближённых данных', async () => {
    await renderLoaded((number) => makeDetail(number));

    const headings = screen.getAllByRole('heading', { level: 1 });
    expect(headings.map((heading) => normalizeText(heading.textContent ?? ''))).toEqual([
      'Коммунальная надёжность домов',
    ]);
    expectSeen(exactTextElement(document.body, HEADER_NOTE));
  });

  it('называет список «Дома» и считает адреса из ответа со склонением', async () => {
    await renderLoaded((number) => makeDetail(number));

    const heading = screen.getByRole('heading', { name: 'Дома' });
    const subtitle = exactTextElement(sectionOf(heading), '20 адресов, включая дома без отключений');
    expectSeen(subtitle);
  });

  it('даёт полю поиска имя «Найти адрес» без подсказки об ограничении поиска', async () => {
    await renderLoaded((number) => makeDetail(number));

    expect(screen.getByRole('combobox', { name: 'Найти адрес' })).toBeInTheDocument();
    expect(screen.queryByText(/Локальный поиск работает только/i)).not.toBeInTheDocument();
  });
});

describe('период в сводке дома', () => {
  it('показывает период датами Asia/Vladivostok без времени, скобок и пояса', async () => {
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone, 'годность замера: TZ=UTC').toBe('UTC');
    await renderLoaded((number) => makeDetail(number));
    await screen.findByText(NO_EVENTS);

    const summary = sectionOf(screen.getByRole('heading', { name: houseAddress(1) }));
    const periodElements = deepestElementsContaining(summary, PERIOD);
    expect(periodElements, `в сводке нет «${PERIOD}»`).toHaveLength(1);
    const periodText = normalizeText(periodElements[0].textContent ?? '');
    expect(periodText).not.toMatch(/[()[\]]/);
    expect(periodText).not.toMatch(/UTC|GMT|\+\d{1,2}|Asia/);
    expectSeen(periodElements[0]);
    expect(normalizeText(summary.textContent ?? '')).not.toMatch(/\d{1,2}:\d{2}/);
  });
});

describe('события дома: страницы и фильтр', () => {
  it('показывает первые 5 событий в порядке API и добавляет по 5 кнопкой', async () => {
    await renderLoaded(withEvents);
    await waitFor(() => expect(shownEventUrls()).toEqual(expectedUrls(1).slice(0, 5)));

    clickShowMore();
    expect(shownEventUrls()).toEqual(expectedUrls(1).slice(0, 10));

    clickShowMore();
    expect(shownEventUrls()).toEqual(expectedUrls(1));
    expect(showMoreButton()).toBeNull();
  });

  it('фильтрует по категории и отмечает выбранную кнопку aria-pressed', async () => {
    await renderLoaded(withEvents);
    await waitFor(() => expect(shownEventUrls()).toHaveLength(5));

    const buttons = within(filterGroup()).getAllByRole('button');
    expect(buttons.map((button) => normalizeText(button.textContent ?? '')).sort())
      .toEqual([...FILTER_LABELS].sort());
    expect(normalizeText(buttons[0].textContent ?? '')).toBe('Все');
    const pressed = () => within(filterGroup()).getAllByRole('button')
      .filter((button) => button.getAttribute('aria-pressed') === 'true')
      .map((button) => normalizeText(button.textContent ?? ''));
    expect(pressed()).toEqual(['Все']);

    chooseFilter('Отопление');
    expect(pressed()).toEqual(['Отопление']);
    expect(shownEventUrls()).toEqual(expectedUrls(1, 'heating'));
    expect(showMoreButton()).toBeNull();

    chooseFilter('Холодная вода');
    expect(pressed()).toEqual(['Холодная вода']);
    expect(shownEventUrls()).toEqual(expectedUrls(1, 'cold_water'));
  });

  it('листает внутри категории больше 5 событий', async () => {
    await renderLoaded(withEvents);
    await waitFor(() => expect(shownEventUrls()).toHaveLength(5));

    chooseFilter('Электричество');
    expect(shownEventUrls()).toEqual(expectedUrls(1, 'electricity').slice(0, 5));
    clickShowMore();
    expect(shownEventUrls()).toEqual(expectedUrls(1, 'electricity'));
    expect(showMoreButton()).toBeNull();
  });

  it('сбрасывает страницу к первым 5 при смене фильтра в обе стороны', async () => {
    await renderLoaded(withEvents);
    await waitFor(() => expect(shownEventUrls()).toHaveLength(5));

    clickShowMore();
    expect(shownEventUrls()).toHaveLength(10);
    chooseFilter('Электричество');
    expect(shownEventUrls()).toEqual(expectedUrls(1, 'electricity').slice(0, 5));
    expect(showMoreButton()).not.toBeNull();

    clickShowMore();
    expect(shownEventUrls()).toHaveLength(6);
    chooseFilter('Все');
    expect(shownEventUrls()).toEqual(expectedUrls(1).slice(0, 5));
  });

  it('сообщает об отсутствии событий выбранной категории', async () => {
    await renderLoaded(withEvents);
    await waitFor(() => expect(shownEventUrls()).toHaveLength(5));

    chooseFilter('Горячая вода');
    expect(shownEventUrls()).toEqual([]);
    expectSeen(exactTextElement(eventsSection(), EMPTY_CATEGORY_TEXT));
    expect(showMoreButton()).toBeNull();
    expect(within(eventsSection()).queryAllByText(/Нет исходных данных/i)).toHaveLength(0);
  });

  it('сбрасывает страницу к первым 5 при смене дома', async () => {
    await renderLoaded(withEvents);
    await waitFor(() => expect(shownEventUrls()).toHaveLength(5));
    clickShowMore();
    expect(shownEventUrls()).toHaveLength(10);

    fireEvent.click(screen.getByRole('button', { name: new RegExp(houseAddress(2)) }));
    expect(await screen.findByRole('heading', { name: houseAddress(2) })).toBeInTheDocument();
    await waitFor(() => expect(shownEventUrls()).toEqual(expectedUrls(2).slice(0, 5)));
  });

  it('отличает пустой список событий от отсутствия исходных данных', async () => {
    await renderLoaded((number) => makeDetail(number));
    await screen.findByText(NO_EVENTS);

    const section = eventsSection();
    expect(within(section).getByText(NO_EVENTS)).toBeInTheDocument();
    expect(within(section).queryAllByText(/Нет исходных данных/i)).toHaveLength(0);
    expect(shownEventUrls()).toEqual([]);
    expect(showMoreButton()).toBeNull();
  });
});

describe('оценки категорий', () => {
  it('объясняет метрики видимыми строками', async () => {
    await renderLoaded((number) => makeDetail(number));
    await screen.findByText(NO_EVENTS);

    const section = categoriesSection();
    for (const line of METRIC_EXPLANATIONS) {
      expectSeen(exactTextElement(section, line));
    }
  });

  it('пока досье грузится, показывает загрузку, а не «Нет исходных данных»', async () => {
    const pending = deferred<Response>();
    renderWith((url) => (
      url.endsWith('/api/houses') ? Promise.resolve(jsonResponse(makeList())) : pending.promise
    ));
    expect(await screen.findByRole('heading', { name: houseAddress(1) })).toBeInTheDocument();

    const section = categoriesSection();
    expect(within(section).queryAllByText(/Нет исходных данных/i)).toHaveLength(0);
    const busy = section.getAttribute('aria-busy') === 'true'
      || section.querySelector('[aria-busy="true"], [role="status"]') !== null;
    expect(busy, 'секция категорий без role="status" или aria-busy="true"').toBe(true);
  });
});

describe('худшая категория', () => {
  it('не показывает блок, если все четыре оценки равны 1', async () => {
    await renderLoaded((number) => makeDetail(number, {
      overall_score: 1,
      categories: allScores(1),
      weakest: 'hot_water',
    }));
    await screen.findByText(NO_EVENTS);

    expect(screen.queryByRole('heading', { name: /Худшая категория/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Худшая категория/i)).not.toBeInTheDocument();
  });

  it('показывает блок при одной оценке ниже 1 и берёт категорию из weakest', async () => {
    await renderLoaded((number) => makeDetail(number, {
      overall_score: 0.999,
      categories: allScores(1, { electricity: 0.999 }),
      weakest: 'electricity',
    }));

    const heading = await screen.findByRole('heading', { name: /Худшая категория/i });
    const section = sectionOf(heading);
    expect(section).toHaveTextContent('Электричество');
    for (const other of ['Горячая вода', 'Холодная вода', 'Отопление']) {
      expect(section).not.toHaveTextContent(other);
    }
  });

  it('не содержит пояснений про ограничение рейтинга и независимую оценку', async () => {
    await renderLoaded((number) => makeDetail(number));
    await screen.findByRole('heading', { name: /Худшая категория/i });

    const text = normalizeText(document.body.textContent ?? '');
    expect(text).not.toContain('Она участвует в ограничении общего рейтинга');
    expect(text).not.toContain('Это не отдельная независимая оценка');
  });
});

describe('запрещённые подстроки во всех состояниях страницы', () => {
  const listOk = (url: string) => url.endsWith('/api/houses');
  const never = () => new Promise<Response>(() => undefined);
  const scenes: { name: string; run: () => Promise<void> }[] = [
    {
      name: 'список загружается',
      run: async () => {
        renderWith(never);
      },
    },
    {
      name: 'сетевая ошибка списка',
      run: async () => {
        renderWith(() => Promise.reject(new TypeError('Failed to fetch')));
        await screen.findByRole('alert');
      },
    },
    {
      name: 'нет исходных данных списка',
      run: async () => {
        renderWith(() => Promise.resolve(jsonResponse({
          error: { code: 'dataset_unavailable', message: 'dataset unavailable' },
        }, 503)));
        await screen.findByRole('alert');
      },
    },
    {
      name: 'досье загружается',
      run: async () => {
        renderWith((url) => (listOk(url) ? Promise.resolve(jsonResponse(makeList())) : never()));
        await screen.findByRole('heading', { name: houseAddress(1) });
      },
    },
    {
      name: 'досье с событиями и раскрытой второй страницей',
      run: async () => {
        await renderLoaded(withEvents);
        await waitFor(() => expect(shownEventUrls()).toHaveLength(5));
        clickShowMore();
      },
    },
    {
      name: 'пустая категория в фильтре',
      run: async () => {
        await renderLoaded(withEvents);
        await waitFor(() => expect(shownEventUrls()).toHaveLength(5));
        chooseFilter('Горячая вода');
      },
    },
    {
      name: 'досье без событий',
      run: async () => {
        await renderLoaded((number) => makeDetail(number));
        await screen.findByText(NO_EVENTS);
      },
    },
    {
      name: 'все категории 100',
      run: async () => {
        await renderLoaded((number) => makeDetail(number, {
          overall_score: 1,
          categories: allScores(1),
        }));
        await screen.findByText(NO_EVENTS);
      },
    },
    {
      name: 'сетевая ошибка досье',
      run: async () => {
        renderWith((url) => (
          listOk(url)
            ? Promise.resolve(jsonResponse(makeList()))
            : Promise.reject(new TypeError('Failed to fetch'))
        ));
        await screen.findByRole('alert');
      },
    },
    {
      name: 'нет исходных данных досье',
      run: async () => {
        renderWith((url) => Promise.resolve(listOk(url)
          ? jsonResponse(makeList())
          : jsonResponse({ error: { code: 'dataset_unavailable', message: 'unavailable' } }, 503)));
        await screen.findByRole('alert');
      },
    },
    {
      name: 'дом не найден',
      run: async () => {
        renderWith((url) => Promise.resolve(listOk(url)
          ? jsonResponse(makeList())
          : jsonResponse({ error: { code: 'house_not_found', message: 'not found' } }, 404)));
        await screen.findByRole('alert');
      },
    },
    {
      name: 'поиск: открыт список вариантов',
      run: async () => {
        await renderLoaded((number) => makeDetail(number));
        fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Тестовая 10' } });
        await screen.findAllByRole('option');
      },
    },
    {
      name: 'поиск: адрес вне набора',
      run: async () => {
        await renderLoaded((number) => makeDetail(number));
        const input = screen.getByRole('combobox');
        fireEvent.change(input, { target: { value: 'Несуществующая 999' } });
        fireEvent.keyDown(input, { key: 'Enter' });
        await screen.findByText(/не входит/i);
      },
    },
    {
      name: 'поиск: ссылка на объявление',
      run: async () => {
        await renderLoaded((number) => makeDetail(number));
        const input = screen.getByRole('combobox');
        fireEvent.change(input, { target: { value: 'https://example.test/listing/42' } });
        fireEvent.keyDown(input, { key: 'Enter' });
        await screen.findByText(/не открываются и не проверяются онлайн/i);
      },
    },
  ];

  it.each(scenes)('$name', async ({ run }) => {
    await run();
    expectNoForbiddenFragments(document.body);
  });
});
