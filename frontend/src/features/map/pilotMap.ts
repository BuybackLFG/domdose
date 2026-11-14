import manifest from './vladivostok-pilot.manifest.json'

/**
 * Локальная подложка для `L.imageOverlay`. Числа берутся из manifest рядом
 * с PNG и не дублируются в коде.
 */
export const PILOT_MAP = {
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
  detailImageUrl: manifest.detail.image,
  detailMinZoom: manifest.detail.min_zoom,
  maxZoom: manifest.max_zoom,
  attribution: manifest.attribution,
} as const
