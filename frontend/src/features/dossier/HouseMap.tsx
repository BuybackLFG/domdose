import L from 'leaflet';
import type { GeoJsonObject } from 'geojson';
import coastline from './map/coastline.json';
import 'leaflet/dist/leaflet.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { scoreBand, type ScoreBand } from './format';
import { PILOT_HOUSES } from './pilotHouses';
import { PILOT_MAP } from './map/pilotMap';
import type { HouseId, HouseSummary } from './types';

interface HouseMapProps {
  /** Все дома ответа API; дом без совпадения с каталогом координат считается непоказанным. */
  houses: readonly HouseSummary[];
  selectedHouseId: HouseId | null;
  onSelectHouse: (houseId: HouseId) => void;
}

interface PlacedHouse extends HouseSummary {
  lat: number;
  lon: number;
}

/** Отступ начального вида от крайних маркеров, px. */
const MARKER_FIT_PADDING = 32;

/** Доля вида у каждого края, попадание выбранного дома в которую сдвигает карту. */
const VIEW_EDGE_SHARE = 0.1;

// Внешний обзор содержит упрощённую береговую линию OSM.
const OVERVIEW_BOUNDS = L.latLngBounds([42.7, 130.8], [43.7, 133.2]);

const OVERLAY_BOUNDS = L.latLngBounds(
  [PILOT_MAP.southWest.lat, PILOT_MAP.southWest.lng],
  [PILOT_MAP.northEast.lat, PILOT_MAP.northEast.lng],
);

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function markerIcon(selected: boolean, band: ScoreBand): L.DivIcon {
  return L.divIcon({
    className: `house-marker house-marker--${band}${selected ? ' house-marker-selected' : ''}`,
    html: '<span></span>',
    iconSize: selected ? [24, 24] : [18, 18],
    iconAnchor: selected ? [12, 12] : [9, 9],
  });
}

/**
 * Ставит minZoom так, чтобы внешний обзор целиком помещался в контейнер.
 * getBoundsZoom ограничен текущим minZoom снизу, поэтому он сначала сбрасывается:
 * иначе при сужении контейнера минимум не уменьшится. Возвращает false без размера.
 */
function applyOverviewMinZoom(map: L.Map): boolean {
  const size = map.getSize();
  if (size.x === 0 || size.y === 0) return false;
  map.setMinZoom(0);
  map.setMinZoom(map.getBoundsZoom(OVERVIEW_BOUNDS, false));
  return true;
}

/**
 * Вписывает вид во все маркеры с отступом; зум не ниже обзорного minZoom.
 * Без измеренного контейнера возвращает false: зум вписывания там не определён.
 */
function fitToHouses(map: L.Map, houses: readonly PlacedHouse[]): boolean {
  if (houses.length === 0 || !applyOverviewMinZoom(map)) return false;
  const size = map.getSize();
  if (size.x <= 2 * MARKER_FIT_PADDING || size.y <= 2 * MARKER_FIT_PADDING) return false;
  map.fitBounds(
    L.latLngBounds(houses.map((house): L.LatLngTuple => [house.lat, house.lon])),
    { padding: [MARKER_FIT_PADDING, MARKER_FIT_PADDING], animate: false },
  );
  return true;
}

/** URL подложки для зума: детальный уровень с detailMinZoom, иначе обзорный. */
function imageUrlForZoom(zoom: number): string {
  return zoom >= PILOT_MAP.detailMinZoom ? PILOT_MAP.detailImageUrl : PILOT_MAP.imageUrl;
}

/** Сдвигает вид к выбранному дому, только если он вне вида или у самого края. */
function revealHouse(map: L.Map, house: PlacedHouse | undefined, animate: boolean): void {
  if (!house || map.getBounds().pad(-VIEW_EDGE_SHARE).contains([house.lat, house.lon])) return;
  map.panTo([house.lat, house.lon], { animate });
}

export function HouseMap({ houses, selectedHouseId, onSelectHouse }: HouseMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<HouseId, L.Marker>>(new Map());
  const placedRef = useRef<readonly PlacedHouse[]>([]);
  const selectedIdRef = useRef<HouseId | null>(null);
  const fittedRef = useRef(false);
  const selectRef = useRef(onSelectHouse);
  const [assetError, setAssetError] = useState(false);
  selectRef.current = onSelectHouse;

  const geoById = useMemo(() => new Map(PILOT_HOUSES.map((house) => [house.house_id, house])), []);
  const placedHouses = useMemo(() => {
    const result: PlacedHouse[] = [];
    for (const house of houses) {
      const geo = geoById.get(house.house_id);
      if (!geo || geo.address !== house.address || geo.lat === null || geo.lon === null) continue;
      result.push({ ...house, lat: geo.lat, lon: geo.lon });
    }
    return result;
  }, [houses, geoById]);
  const unplacedCount = houses.length - placedHouses.length;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const reduceMotion = prefersReducedMotion();
    // Дробный зум позволяет показать обзор целиком при любой форме контейнера.
    const map = L.map(container, {
      zoomControl: true,
      attributionControl: true,
      keyboard: true,
      scrollWheelZoom: true,
      touchZoom: true,
      maxZoom: PILOT_MAP.maxZoom,
      zoomSnap: 0,
      maxBounds: OVERVIEW_BOUNDS,
      maxBoundsViscosity: 1,
      zoomAnimation: !reduceMotion,
      fadeAnimation: !reduceMotion,
      markerZoomAnimation: !reduceMotion,
    });
    map.zoomControl.getContainer()?.querySelector('.leaflet-control-zoom-in')?.setAttribute('aria-label', 'Приблизить карту');
    map.zoomControl.getContainer()?.querySelector('.leaflet-control-zoom-out')?.setAttribute('aria-label', 'Отдалить карту');
    // Prefix Leaflet по умолчанию содержит внешнюю ссылку; attribution — только текст manifest.
    map.attributionControl.setPrefix(false);

    // Подложка закрывает только свои bounds; вне них нужен фон. Держим фон в
    // отдельной панели ниже overlay-pane: Leaflet поднимает SVG-векторы над
    // image overlay, и в общей панели береговая линия перекрывала карту.
    const maskPane = map.createPane('house-map-mask');
    maskPane.style.zIndex = '350';
    L.rectangle(OVERVIEW_BOUNDS, {
      pane: 'house-map-mask',
      stroke: false,
      fillColor: '#aad3df',
      fillOpacity: 1,
      interactive: false,
    }).addTo(map);
    L.geoJSON(coastline as GeoJsonObject, {
      pane: 'house-map-mask',
      style: { stroke: false, fillColor: '#f2efe9', fillOpacity: 1 },
      interactive: false,
    }).addTo(map);

    // Один детальный оверлей на тех же bounds: при смене уровня меняется только src.
    let currentImageUrl = imageUrlForZoom(map.getZoom());
    const overlay = L.imageOverlay(
      currentImageUrl,
      OVERLAY_BOUNDS,
      {
        attribution: PILOT_MAP.attribution,
        interactive: false,
        alt: 'Карта Владивостока',
      },
    ).addTo(map);
    overlay.on('error', () => setAssetError(true));

    const syncImageUrl = () => {
      const next = imageUrlForZoom(map.getZoom());
      if (next === currentImageUrl) return;
      currentImageUrl = next;
      overlay.setUrl(next);
    };
    map.on('zoomend', syncImageUrl);

    applyOverviewMinZoom(map);
    map.setView(OVERVIEW_BOUNDS.getCenter(), map.getMinZoom(), { animate: false });
    syncImageUrl();

    // Размер контейнера может появиться или измениться позже: покрытие и начальный вид
    // пересчитываются по факту измерения.
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
      if (!applyOverviewMinZoom(map)) return;
      if (fitToHouses(map, placedRef.current)) {
        fittedRef.current = true;
        const selected = placedRef.current.find((house) => house.house_id === selectedIdRef.current);
        revealHouse(map, selected, false);
      }
      map.panInsideBounds(OVERVIEW_BOUNDS, { animate: false });
    });
    observer.observe(container);
    mapRef.current = map;

    const markers = markersRef.current;
    return () => {
      observer.disconnect();
      map.off('zoomend', syncImageUrl);
      for (const marker of markers.values()) marker.remove();
      markers.clear();
      map.remove();
      mapRef.current = null;
      fittedRef.current = false;
      setAssetError(false);
    };
  }, []);

  useEffect(() => {
    placedRef.current = placedHouses;
    selectedIdRef.current = selectedHouseId;
    const map = mapRef.current;
    if (!map) return;

    const nextIds = new Set(placedHouses.map((house) => house.house_id));
    for (const [houseId, marker] of markersRef.current) {
      if (!nextIds.has(houseId)) {
        marker.remove();
        markersRef.current.delete(houseId);
      }
    }

    for (const house of placedHouses) {
      const selected = house.house_id === selectedHouseId;
      const band = scoreBand(house.overall_score);
      let marker = markersRef.current.get(house.house_id);
      if (!marker) {
        marker = L.marker([house.lat, house.lon], {
          icon: markerIcon(selected, band),
          keyboard: true,
          title: house.address,
          alt: `${house.address}${selected ? ' (выбран)' : ''}`,
          riseOnHover: true,
        }).addTo(map);
        marker.on('click', () => selectRef.current(house.house_id));
        markersRef.current.set(house.house_id, marker);
      } else {
        marker.setLatLng([house.lat, house.lon]);
        marker.setIcon(markerIcon(selected, band));
        marker.setZIndexOffset(selected ? 1000 : 0);
      }

      const label = document.createElement('span');
      label.textContent = house.address;
      marker.bindTooltip(label, {
        permanent: false,
        direction: 'top',
        offset: [0, -14],
        className: 'house-marker-label',
      });
    }

    if (!fittedRef.current) {
      let tries = 0;
      const attempt = () => {
        if (mapRef.current !== map) return;
        const size = map.getSize();
        if (size.x > 2 * MARKER_FIT_PADDING && size.y > 2 * MARKER_FIT_PADDING
          && fitToHouses(map, placedHouses)) {
          fittedRef.current = true;
          const selected = placedHouses.find((house) => house.house_id === selectedHouseId);
          revealHouse(map, selected, !prefersReducedMotion());
          return;
        }
        if (tries++ < 20) requestAnimationFrame(attempt);
      };
      attempt();
    } else {
      const selected = placedHouses.find((house) => house.house_id === selectedHouseId);
      revealHouse(map, selected, !prefersReducedMotion());
    }
  }, [placedHouses, selectedHouseId]);
  return (
    <>
      <div ref={containerRef} className="map-canvas" role="region" aria-label="Карта домов" />
      {assetError && (
        <div role="alert" className="map-status">
          Не удалось загрузить локальную подложку. Список и досье доступны; online fallback не
          выполняется.
        </div>
      )}
      {unplacedCount > 0 && (
        <p role="status" className="map-status">
          {`Не удалось показать на карте: ${unplacedCount}`}
        </p>
      )}
    </>
  );
}
