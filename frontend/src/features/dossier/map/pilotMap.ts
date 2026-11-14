import manifest from '../../../../public/maps/vladivostok-pilot.manifest.json';

/**
 * Локальная подложка для L.imageOverlay. Единственный источник чисел —
 * prepared manifest рядом с PNG: URL, bounds WGS84, размеры и attribution
 * берутся из него и не дублируются в коде.
 */
export const PILOT_MAP = {
  prepared: true,
  imageUrl: manifest.image,
  crs: manifest.crs,
  southWest: {
    lat: manifest.bounds.south,
    lng: manifest.bounds.west,
  },
  northEast: {
    lat: manifest.bounds.north,
    lng: manifest.bounds.east,
  },
  width: manifest.width,
  height: manifest.height,
  /** Детальный уровень того же кадра; включается с detailMinZoom. */
  detailImageUrl: manifest.detail.image,
  detailMinZoom: manifest.detail.min_zoom,
  maxZoom: manifest.max_zoom,
  attribution: manifest.attribution,
} as const;
