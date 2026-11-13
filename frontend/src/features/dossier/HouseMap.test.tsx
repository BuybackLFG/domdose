import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DossierPage } from './DossierPage';
import { PILOT_HOUSES } from './pilotHouses';
import type { HouseDetailResponse, HouseId, HouseListResponse } from './types';

const SCOPE = { kind: 'pilot', house_count: 20, average_basis: 'pilot_only' } as const;
const WINDOW = {
  start: '2026-01-01T00:00:00+10:00',
  end: '2026-01-31T00:00:00+10:00',
} as const;
const MAP_IMAGE_SUFFIX = '/maps/vladivostok-pilot.png';

function makeList(): HouseListResponse {
  return {
    scope: SCOPE,
    window: WINDOW,
    houses: PILOT_HOUSES.map((house, index) => ({
      house_id: house.house_id,
      address: house.address,
      overall_score: (index % 5) / 4,
    })),
  };
}

function makeCategory(score: number) {
  return {
    metrics: { frequency: 0, hours: 0, longest: 0 },
    penalties: { frequency: 0, hours: 0, longest: 0 },
    score,
  };
}

function makeDetail(houseId: HouseId): HouseDetailResponse {
  const house = PILOT_HOUSES.find((candidate) => candidate.house_id === houseId);
  if (!house) throw new Error(`Unexpected house: ${houseId}`);
  return {
    scope: SCOPE,
    window: WINDOW,
    house_id: house.house_id,
    address: house.address,
    overall_score: 0.5,
    categories: {
      hot_water: makeCategory(0.9),
      cold_water: makeCategory(0.8),
      electricity: makeCategory(0.7),
      heating: makeCategory(0.6),
    },
    weakest: 'heating',
    events: [],
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function installFetch() {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url.endsWith('/api/houses')) return Promise.resolve(jsonResponse(makeList()));
    const match = url.match(/\/api\/houses\/(house_\d{6})$/);
    if (match) return Promise.resolve(jsonResponse(makeDetail(match[1] as HouseId)));
    return Promise.reject(new Error(`Unexpected URL: ${url}`));
  }));
}

/** Ссылки src/href/srcset/style url() на http(s)-хост вне текущего origin. */
function externalReferences(root: ParentNode): string[] {
  const values: string[] = [];
  const isExternal = (raw: string) => {
    const url = new URL(raw, window.location.href);
    return (url.protocol === 'http:' || url.protocol === 'https:')
      && url.host !== window.location.host;
  };
  for (const element of root.querySelectorAll('[src], [href], [srcset], [style]')) {
    for (const name of ['src', 'href']) {
      const value = element.getAttribute(name);
      if (value !== null && isExternal(value)) values.push(value);
    }
    for (const candidate of (element.getAttribute('srcset') ?? '').split(',')) {
      const value = candidate.trim().split(/\s+/)[0];
      if (value && isExternal(value)) values.push(value);
    }
    for (const match of (element.getAttribute('style') ?? '').matchAll(/url\(\s*['"]?([^'")]+)/g)) {
      if (isExternal(match[1])) values.push(match[1]);
    }
  }
  return values;
}

describe('offline-карта основного экрана', () => {
  it('рисует 20 markers поверх одного локального imageOverlay без внешних ресурсов', async () => {
    installFetch();
    const { container } = render(<DossierPage />);
    expect(await screen.findByRole('heading', { name: PILOT_HOUSES[0].address }))
      .toBeInTheDocument();

    await waitFor(() => {
      expect(container.querySelectorAll('.leaflet-container .house-marker')).toHaveLength(20);
    });

    const maps = container.querySelectorAll('.leaflet-container');
    expect(maps).toHaveLength(1);
    const map = maps[0];
    expect(document.querySelectorAll('.house-marker')).toHaveLength(20);

    const overlays = map.querySelectorAll('img.leaflet-image-layer');
    expect(overlays).toHaveLength(1);
    expect(overlays[0].getAttribute('src') ?? '').toMatch(/\/maps\/vladivostok-pilot\.png$/);
    const mapImages = Array.from(document.querySelectorAll('img')).filter((image) => (
      (image.getAttribute('src') ?? '').endsWith(MAP_IMAGE_SUFFIX)
    ));
    expect(mapImages).toHaveLength(1);

    expect(map.querySelectorAll('.leaflet-tile, .leaflet-tile-container')).toHaveLength(0);
    expect(externalReferences(document)).toEqual([]);
  });
});
