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
}

function readManifest(): MapManifest {
  expect(
    existsSync(MANIFEST_PATH),
    'Нужен prepared map manifest; нулевые или угадываемые bounds не принимаются.',
  ).toBe(true);
  return JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as MapManifest;
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
});
