import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PILOT_HOUSES } from './pilotHouses';
import { PILOT_MAP } from './map/pilotMap';

const ASSET_PATH = resolve(process.cwd(), 'public/maps/vladivostok-pilot.png');
const MANIFEST_PATH = resolve(process.cwd(), 'public/maps/vladivostok-pilot.manifest.json');

interface MapManifest {
  image: string;
  crs: string;
  bounds: { south: number; west: number; north: number; east: number };
  projected_bounds: { min_x: number; min_y: number; max_x: number; max_y: number };
  width: number;
  height: number;
  image_sha256: unknown;
  attribution: unknown;
  license: unknown;
  source: Record<string, unknown>;
  commands: unknown;
}

function readManifest(): MapManifest {
  expect(
    existsSync(MANIFEST_PATH),
    'Нужен prepared map manifest; нулевые или угадываемые bounds не принимаются.',
  ).toBe(true);
  return JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as MapManifest;
}

function readAsset(): Buffer {
  expect(
    existsSync(ASSET_PATH),
    'Отсутствует prepared asset public/maps/vladivostok-pilot.png; online fallback запрещён.',
  ).toBe(true);
  return readFileSync(ASSET_PATH);
}

/** Все строковые значения вложенной структуры manifest. */
function collectStrings(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(collectStrings);
  if (value !== null && typeof value === 'object') {
    return Object.values(value).flatMap(collectStrings);
  }
  return [];
}

function looksAbsolute(path: string): boolean {
  return /^(?:[A-Za-z]:|[/\\])/.test(path);
}

function projectLongitude(longitude: number): number {
  return 6_378_137 * longitude * Math.PI / 180;
}

function projectLatitude(latitude: number): number {
  return 6_378_137 * Math.log(Math.tan(Math.PI / 4 + latitude * Math.PI / 360));
}

describe('пилотный геокаталог', () => {
  it('содержит ровно 20 уникальных домов и по 4 в каждом из пяти районов', () => {
    const expectedIds = Array.from(
      { length: 20 },
      (_, index) => `house_${String(index + 1).padStart(6, '0')}`,
    );

    expect(PILOT_HOUSES.map((house) => house.house_id)).toEqual(expectedIds);
    expect(new Set(PILOT_HOUSES.map((house) => house.house_id)).size).toBe(20);

    const counts = new Map<string, number>();
    for (const house of PILOT_HOUSES) {
      counts.set(house.district, (counts.get(house.district) ?? 0) + 1);
    }
    expect(Object.fromEntries(counts)).toEqual({
      'Ленинский': 4,
      'Первомайский': 4,
      'Первореченский': 4,
      'Советский': 4,
      'Фрунзенский': 4,
    });
  });

  it('имеет конечные координаты всех 20 домов внутри prepared bounds', () => {
    const invalid = PILOT_HOUSES.filter((house) => (
      typeof house.lat !== 'number'
      || !Number.isFinite(house.lat)
      || typeof house.lon !== 'number'
      || !Number.isFinite(house.lon)
    ));
    expect(
      invalid.map((house) => house.house_id),
      'Каждый дом должен иметь проверенные координаты; null не считается полной картой.',
    ).toEqual([]);

    for (const house of PILOT_HOUSES) {
      if (house.lat === null || house.lon === null) continue;
      expect(house.lat).toBeGreaterThanOrEqual(PILOT_MAP.southWest.lat);
      expect(house.lat).toBeLessThanOrEqual(PILOT_MAP.northEast.lat);
      expect(house.lon).toBeGreaterThanOrEqual(PILOT_MAP.southWest.lng);
      expect(house.lon).toBeLessThanOrEqual(PILOT_MAP.northEast.lng);
    }
  });
});

describe('подготовленная offline-карта', () => {
  it('требует реальный PNG asset, а не placeholder', () => {
    expect(
      existsSync(ASSET_PATH),
      'Отсутствует prepared asset public/maps/vladivostok-pilot.png; online fallback запрещён.',
    ).toBe(true);

    const png = readFileSync(ASSET_PATH);
    expect(png.length).toBeGreaterThan(100);
    expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  });

  it('совпадает с manifest и сохраняет EPSG:3857 aspect ratio', () => {
    const manifest = readManifest();
    expect(manifest.image).toBe('/maps/vladivostok-pilot.png');
    expect(manifest.crs).toBe('EPSG:3857');
    expect(manifest.width).toBe(2048);
    expect(Number.isInteger(manifest.height)).toBe(true);
    expect(manifest.height).toBeGreaterThan(0);

    const { south, west, north, east } = manifest.bounds;
    expect([south, west, north, east].every(Number.isFinite)).toBe(true);
    expect(north).toBeGreaterThan(south);
    expect(east).toBeGreaterThan(west);
    expect(PILOT_MAP.southWest).toEqual({ lat: south, lng: west });
    expect(PILOT_MAP.northEast).toEqual({ lat: north, lng: east });
    expect(PILOT_MAP.imageUrl).toBe(manifest.image);
    expect(PILOT_MAP.width).toBe(manifest.width);
    expect(PILOT_MAP.height).toBe(manifest.height);

    const projected = manifest.projected_bounds;
    expect(Object.values(projected).every(Number.isFinite)).toBe(true);
    expect(projected.max_x).toBeGreaterThan(projected.min_x);
    expect(projected.max_y).toBeGreaterThan(projected.min_y);
    expect(Math.abs(projected.min_x - projectLongitude(west))).toBeLessThan(0.01);
    expect(Math.abs(projected.max_x - projectLongitude(east))).toBeLessThan(0.01);
    expect(Math.abs(projected.min_y - projectLatitude(south))).toBeLessThan(0.01);
    expect(Math.abs(projected.max_y - projectLatitude(north))).toBeLessThan(0.01);

    const projectedWidth = projected.max_x - projected.min_x;
    const projectedHeight = projected.max_y - projected.min_y;
    expect(
      Math.abs(manifest.width * projectedHeight - manifest.height * projectedWidth),
      'height должен быть round(width * projectedHeight / projectedWidth), без растяжения карты.',
    ).toBeLessThanOrEqual(projectedWidth / 2 + 1e-6);
  });

  it('берёт width и height manifest из IHDR реального PNG', () => {
    const manifest = readManifest();
    const png = readAsset();

    expect(png.subarray(12, 16).toString('ascii')).toBe('IHDR');
    expect(png.readUInt32BE(16)).toBe(manifest.width);
    expect(png.readUInt32BE(20)).toBe(manifest.height);
  });

  it('фиксирует sha256 байтов PNG в manifest', () => {
    const manifest = readManifest();
    const digest = createHash('sha256').update(readAsset()).digest('hex');

    expect(manifest.image_sha256).toBe(digest);
  });

  it('несёт attribution и лицензию OpenStreetMap', () => {
    const manifest = readManifest();

    expect(manifest.attribution).toBe('© OpenStreetMap contributors');
    expect(manifest.license).toBe('ODbL-1.0');
  });

  it('описывает исходный PBF без абсолютных путей машины', () => {
    const { source } = readManifest();

    expect(typeof source.pbf_name).toBe('string');
    expect(String(source.pbf_name).trim()).not.toBe('');
    expect(source.pbf_sha256).toEqual(expect.stringMatching(/^[0-9a-f]{64}$/));
    expect(collectStrings(source).filter(looksAbsolute)).toEqual([]);
  });

  it('хранит команды воспроизведения подготовки', () => {
    const { commands } = readManifest();

    expect(Array.isArray(commands)).toBe(true);
    const list = Array.isArray(commands) ? commands : [];
    expect(list.length).toBeGreaterThan(0);
    expect(list.filter((command) => (
      typeof command !== 'string' || command.trim() === ''
    ))).toEqual([]);
  });

  it('включает подготовленную карту с attribution из manifest', () => {
    expect(PILOT_MAP.prepared, 'PILOT_MAP.prepared должен быть true при готовом asset').toBe(true);
    const manifest = readManifest();

    expect(PILOT_MAP.attribution).toBe(manifest.attribution);
  });
});
