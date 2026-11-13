import { PILOT_HOUSES } from '../pilotHouses';

function projectLongitude(longitude: number): number {
  return 6_378_137 * longitude * Math.PI / 180;
}

function projectLatitude(latitude: number): number {
  return 6_378_137 * Math.log(Math.tan(Math.PI / 4 + latitude * Math.PI / 360));
}

/**
 * Временная конфигурация рамки выводится только из подтверждённых candidate
 * координат. prepared=false является явным состоянием отсутствующего asset,
 * а не разрешением рисовать фиктивную карту.
 */
function deriveCandidateBounds() {
  const points = PILOT_HOUSES.filter((house) => (
    house.lat !== null && house.lon !== null
  )) as Array<{ lat: number; lon: number }>;

  if (points.length === 0) {
    throw new Error('Нет ни одной candidate-координаты для bounds');
  }

  const lats = points.map((point) => point.lat);
  const lons = points.map((point) => point.lon);
  const south = Math.min(...lats) - 0.05;
  const west = Math.min(...lons) - 0.05;
  const north = Math.max(...lats) + 0.05;
  const east = Math.max(...lons) + 0.05;
  const width = 2048;
  const projectedWidth = projectLongitude(east) - projectLongitude(west);
  const projectedHeight = projectLatitude(north) - projectLatitude(south);
  const height = Math.max(1, Math.round(width * projectedHeight / projectedWidth));

  return { south, west, north, east, width, height };
}

const candidateBounds = deriveCandidateBounds();

export const PILOT_MAP = {
  /** Asset и manifest ещё не подготовлены отдельным map-пакетом. */
  prepared: false,
  imageUrl: '/maps/vladivostok-pilot.png',
  crs: 'EPSG:3857',
  southWest: {
    lat: candidateBounds.south,
    lng: candidateBounds.west,
  },
  northEast: {
    lat: candidateBounds.north,
    lng: candidateBounds.east,
  },
  width: candidateBounds.width,
  height: candidateBounds.height,
  attribution: '© OpenStreetMap contributors',
} as const;
