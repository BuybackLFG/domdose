import { act, render, screen, waitFor } from '@testing-library/react';
import L from 'leaflet';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { expectNoForbiddenFragments, hiddenFromSightReason, normalizeText } from '../../test/uiText';
import { DossierPage } from './DossierPage';
import { PILOT_HOUSES } from './pilotHouses';
import type { HouseDetailResponse, HouseId, HouseListResponse } from './types';

const SCOPE = { kind: 'pilot', house_count: 20, average_basis: 'pilot_only' } as const;
const WINDOW = {
  start: '2026-01-01T00:00:00+10:00',
  end: '2026-01-31T00:00:00+10:00',
} as const;
// Любой из двух уровней одной подложки; уровень по зуму проверяет отдельная сцена.
const MAP_IMAGE_PATTERN = /\/maps\/vladivostok-pilot(?:-detail)?\.png$/;

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

function installFetch(list: HouseListResponse = makeList()) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = requestUrl(input);
    if (url.endsWith('/api/houses')) return Promise.resolve(jsonResponse(list));
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
    expect(overlays[0].getAttribute('src') ?? '').toMatch(MAP_IMAGE_PATTERN);
    const mapImages = Array.from(document.querySelectorAll('img')).filter((image) => (
      MAP_IMAGE_PATTERN.test(image.getAttribute('src') ?? '')
    ));
    expect(mapImages).toHaveLength(1);

    expect(map.querySelectorAll('.leaflet-tile, .leaflet-tile-container')).toHaveLength(0);
    expect(externalReferences(document)).toEqual([]);
  });
});

interface ManifestZoom {
  bounds: { south: number; west: number; north: number; east: number };
  image: string;
  max_zoom?: unknown;
  detail?: { image?: unknown; min_zoom?: unknown };
}

function readManifest(): ManifestZoom {
  const path = resolve(process.cwd(), 'public/maps/vladivostok-pilot.manifest.json');
  return JSON.parse(readFileSync(path, 'utf8')) as ManifestZoom;
}

type PointLayer = L.Marker | L.CircleMarker;

/** Перехват Map.addLayer: экземпляры карты и добавленные слои без правок реализации. */
function probeLeaflet() {
  const maps: L.Map[] = [];
  const layers: L.Layer[] = [];
  const original = L.Map.prototype.addLayer;
  vi.spyOn(L.Map.prototype, 'addLayer').mockImplementation(function addLayer(
    this: L.Map,
    layer: L.Layer,
  ) {
    if (!maps.includes(this)) maps.push(this);
    layers.push(layer);
    return original.call(this, layer);
  });
  const onlyMap = (): L.Map => {
    expect(maps, 'ровно один экземпляр Leaflet-карты').toHaveLength(1);
    return maps[0];
  };
  const live = <T extends L.Layer>(predicate: (layer: L.Layer) => layer is T): T[] => {
    const map = onlyMap();
    return [...new Set(layers)].filter(predicate).filter((layer) => map.hasLayer(layer));
  };
  return {
    onlyMap,
    points: () => live((layer): layer is PointLayer => (
      layer instanceof L.Marker || layer instanceof L.CircleMarker
    )),
    overlays: () => live((layer): layer is L.ImageOverlay => layer instanceof L.ImageOverlay),
  };
}

function overlayImages(container: HTMLElement): HTMLImageElement[] {
  return Array.from(container.querySelectorAll<HTMLImageElement>('img.leaflet-image-layer'));
}

function mapLossWarnings(): HTMLElement[] {
  return screen.queryAllByRole('status').filter((element) => (
    normalizeText(element.textContent ?? '').startsWith('Не удалось показать на карте:')
  ));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

describe('положение markers и уровни подложки', () => {
  it('ставит каждый из 20 markers в lat/lon дома из каталога внутри bounds подложки', async () => {
    const probe = probeLeaflet();
    installFetch();
    render(<DossierPage />);
    await waitFor(() => expect(probe.points()).toHaveLength(20));

    const { bounds } = readManifest();
    const positions = probe.points().map((point) => point.getLatLng());
    for (const position of positions) {
      expect(position.lat).toBeGreaterThanOrEqual(bounds.south);
      expect(position.lat).toBeLessThanOrEqual(bounds.north);
      expect(position.lng).toBeGreaterThanOrEqual(bounds.west);
      expect(position.lng).toBeLessThanOrEqual(bounds.east);
    }
    const matched = positions.map((position) => PILOT_HOUSES.find((house) => (
      house.lat === position.lat && house.lon === position.lng
    ))?.house_id ?? `нет дома в ${position.lat},${position.lng}`);
    expect([...matched].sort()).toEqual(PILOT_HOUSES.map((house) => house.house_id).sort());
    expect(mapLossWarnings()).toEqual([]);
  });

  it('меняет детализацию подменой src единственного оверлея на тех же bounds', async () => {
    const probe = probeLeaflet();
    installFetch();
    const { container } = render(<DossierPage />);
    await waitFor(() => expect(probe.points()).toHaveLength(20));

    const manifest = readManifest();
    const detailImage = String(manifest.detail?.image);
    const detailMinZoom = Number(manifest.detail?.min_zoom);
    expect(Number.isInteger(detailMinZoom), 'manifest.detail.min_zoom').toBe(true);
    const map = probe.onlyMap();
    expect(map.getMaxZoom()).toBe(manifest.max_zoom);

    const expectLevel = (zoom: number, image: string) => {
      act(() => {
        map.setZoom(zoom, { animate: false });
      });
      const overlays = probe.overlays();
      expect(overlays, `слои оверлея на zoom ${zoom}`).toHaveLength(1);
      const layerBounds = overlays[0].getBounds();
      expect(layerBounds.getSouth()).toBeCloseTo(manifest.bounds.south, 9);
      expect(layerBounds.getWest()).toBeCloseTo(manifest.bounds.west, 9);
      expect(layerBounds.getNorth()).toBeCloseTo(manifest.bounds.north, 9);
      expect(layerBounds.getEast()).toBeCloseTo(manifest.bounds.east, 9);
      const images = overlayImages(container);
      expect(images, `img.leaflet-image-layer на zoom ${zoom}`).toHaveLength(1);
      expect(images[0].getAttribute('src') ?? '', `src на zoom ${map.getZoom()}`)
        .toMatch(new RegExp(`${escapeRegExp(image)}$`));
    };

    expectLevel(map.getMinZoom(), manifest.image);
    expectLevel(detailMinZoom, detailImage);
    expectLevel(map.getMaxZoom(), detailImage);
    expectLevel(detailMinZoom - 1, manifest.image);
  });

  it('не теряет молча дом с адресом не из каталога и сообщает о нём', async () => {
    const probe = probeLeaflet();
    const list = makeList();
    const lost = list.houses[4];
    list.houses[4] = { ...lost, address: `${lost.address}, корпус вне каталога` };
    installFetch(list);
    render(<DossierPage />);
    await waitFor(() => expect(probe.points()).toHaveLength(19));

    const positions = probe.points().map((point) => point.getLatLng());
    const geo = PILOT_HOUSES.find((house) => house.house_id === lost.house_id);
    expect(positions.some((position) => (
      position.lat === geo?.lat && position.lng === geo?.lon
    ))).toBe(false);

    await waitFor(() => expect(mapLossWarnings()).toHaveLength(1));
    const warning = mapLossWarnings()[0];
    const text = normalizeText(warning.textContent ?? '');
    expect(text.slice('Не удалось показать на карте:'.length)).toMatch(/(^|\D)1(\D|$)/);
    expect(hiddenFromSightReason(warning)).toBeNull();
    expect(warning).toBeVisible();
  });

  it('не содержит запрещённых подстрок в тексте и доступных именах карты', async () => {
    const probe = probeLeaflet();
    installFetch();
    render(<DossierPage />);
    await waitFor(() => expect(probe.points()).toHaveLength(20));
    expect(await screen.findByRole('heading', { name: PILOT_HOUSES[0].address }))
      .toBeInTheDocument();

    expectNoForbiddenFragments(document.body);
  });
});

it('позволяет отдалить карту до полного кадра и приблизить кнопками и колесом', async () => {
  vi.spyOn(L.Map.prototype, 'getSize').mockImplementation(() => L.point(1000, 400));
  const probe = probeLeaflet();
  installFetch();
  const { container } = render(<DossierPage />);
  await waitFor(() => expect(probe.points()).toHaveLength(20));
  const map = probe.onlyMap();
  expect(map.scrollWheelZoom.enabled()).toBe(true);
  expect(map.keyboard.enabled()).toBe(true);
  expect(map.touchZoom.enabled()).toBe(true);
  expect(map.getMaxZoom()).toBeGreaterThanOrEqual(17);
  act(() => map.setZoom(map.getMinZoom(), { animate: false }));
  const bounds = readManifest().bounds;
  expect(map.getBounds().contains([bounds.south, bounds.west])).toBe(true);
  expect(map.getBounds().contains([bounds.north, bounds.east])).toBe(true);
  const before = map.getZoom();
  const plus = container.querySelector<HTMLElement>('.leaflet-control-zoom-in');
  expect(plus).not.toBeNull();
  act(() => plus?.click());
  expect(map.getZoom()).toBeGreaterThan(before);
  const minus = container.querySelector<HTMLElement>('.leaflet-control-zoom-out');
  expect(minus).not.toBeNull();
  act(() => minus?.click());
  expect(map.getZoom()).toBeCloseTo(before);
});


it.each([[1000, 400], [375, 320]])('при первоначальном виде все маркеры видны в контейнере %i×%i', async (width, height) => {
  vi.spyOn(L.Map.prototype, 'getSize').mockImplementation(() => L.point(width, height));
  const probe = probeLeaflet();
  installFetch();
  render(<DossierPage />);
  await waitFor(() => expect(probe.points()).toHaveLength(20));
  const bounds = probe.onlyMap().getBounds();
  for (const marker of probe.points()) expect(bounds.contains(marker.getLatLng())).toBe(true);
});


it('передаёт адреса во всплывающие подписи как текстовые DOM-узлы', async () => {
  const bindTooltip = vi.spyOn(L.Marker.prototype, 'bindTooltip');
  installFetch();
  render(<DossierPage />);
  await waitFor(() => expect(bindTooltip).toHaveBeenCalled());
  for (const call of bindTooltip.mock.calls) {
    expect(call[0]).toBeInstanceOf(HTMLElement);
    const node = call[0] as HTMLElement;
    expect(node.children).toHaveLength(0);
    expect(PILOT_HOUSES.some((house) => house.address === node.textContent)).toBe(true);
  }
});
