import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useEffect, useMemo, useRef, useState } from 'react';
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

/**
 * Запас покрытия 2 px с каждой стороны (отрицательный padding getBoundsZoom):
 * Leaflet не исправляет выход вида за maxBounds до 1 px, и у края оставалась полоса фона.
 */
const COVER_OVERSCAN = L.point(-4, -4);

const OVERLAY_BOUNDS = L.latLngBounds(
  [PILOT_MAP.southWest.lat, PILOT_MAP.southWest.lng],
  [PILOT_MAP.northEast.lat, PILOT_MAP.northEast.lng],
);

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function markerIcon(selected: boolean): L.DivIcon {
  return L.divIcon({
    className: `house-marker${selected ? ' house-marker-selected' : ''}`,
    html: '<span></span>',
    iconSize: selected ? [24, 24] : [18, 18],
    iconAnchor: selected ? [12, 12] : [9, 9],
  });
}

/**
 * Ставит minZoom равным зуму, при котором подложка покрывает весь контейнер.
 * getBoundsZoom ограничен текущим minZoom снизу, поэтому он сначала сбрасывается:
 * иначе при сужении контейнера минимум не уменьшится. Возвращает false без размера.
 */
function applyCoverMinZoom(map: L.Map): boolean {
  const size = map.getSize();
  if (size.x === 0 || size.y === 0) return false;
  map.setMinZoom(0);
  map.setMinZoom(map.getBoundsZoom(OVERLAY_BOUNDS, true, COVER_OVERSCAN));
  return true;
}

/**
 * Вписывает вид во все маркеры с отступом; зум не ниже покрывающего minZoom.
 * Без измеренного контейнера возвращает false: зум вписывания там не определён.
 */
function fitToHouses(map: L.Map, houses: readonly PlacedHouse[]): boolean {
  if (houses.length === 0 || !applyCoverMinZoom(map)) return false;
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
    // Вид не выходит за подложку; zoomSnap 0 — покрытие без округления зума вверх.
    const map = L.map(container, {
      zoomControl: true,
      attributionControl: true,
      keyboard: true,
      scrollWheelZoom: false,
      maxZoom: PILOT_MAP.maxZoom,
      zoomSnap: 0,
      maxBounds: OVERLAY_BOUNDS,
      maxBoundsViscosity: 1,
      zoomAnimation: !reduceMotion,
      fadeAnimation: !reduceMotion,
      markerZoomAnimation: !reduceMotion,
    });
    // Prefix Leaflet по умолчанию содержит внешнюю ссылку; attribution — только текст manifest.
    map.attributionControl.setPrefix(false);

    // Один оверлей на тех же bounds: при смене уровня меняется только src.
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

    applyCoverMinZoom(map);
    map.setView(OVERLAY_BOUNDS.getCenter(), map.getMinZoom(), { animate: false });
    syncImageUrl();

    // Размер контейнера может появиться или измениться позже: покрытие и начальный вид
    // пересчитываются по факту измерения.
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false });
      if (!applyCoverMinZoom(map)) return;
      if (!fittedRef.current && fitToHouses(map, placedRef.current)) {
        fittedRef.current = true;
        const selected = placedRef.current.find((house) => house.house_id === selectedIdRef.current);
        revealHouse(map, selected, false);
      }
      map.panInsideBounds(OVERLAY_BOUNDS, { animate: false });
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
      let marker = markersRef.current.get(house.house_id);
      if (!marker) {
        marker = L.marker([house.lat, house.lon], {
          icon: markerIcon(selected),
          keyboard: true,
          title: house.address,
          alt: `${house.address}${selected ? ' (выбран)' : ''}`,
          riseOnHover: true,
        }).addTo(map);
        marker.on('click', () => selectRef.current(house.house_id));
        markersRef.current.set(house.house_id, marker);
      } else {
        marker.setLatLng([house.lat, house.lon]);
        marker.setIcon(markerIcon(selected));
        marker.setZIndexOffset(selected ? 1000 : 0);
      }

      marker.bindTooltip(house.address, {
        permanent: false,
        direction: 'top',
        offset: [0, -14],
        className: 'house-marker-label',
      });
    }

    if (!fittedRef.current) fittedRef.current = fitToHouses(map, placedHouses);
    if (fittedRef.current) {
      const selected = placedHouses.find((house) => house.house_id === selectedHouseId);
      revealHouse(map, selected, !prefersReducedMotion());
    }
  }, [placedHouses, selectedHouseId]);

  // isolate — свой контекст наложения: панели Leaflet (z-index 400–1000) не перекрывают
  // выпадающие подсказки поиска над картой.
  return (
    <section aria-labelledby="house-map-heading" className="isolate overflow-hidden rounded-2xl bg-surface shadow-sm ring-1 ring-border">
      <h2 id="house-map-heading" className="sr-only">Карта домов</h2>
      <div ref={containerRef} className="h-80 w-full sm:h-105 lg:h-120" aria-label="Карта домов" />
      {assetError && (
        <div role="alert" className="border-t border-danger/30 bg-danger/10 px-4 py-3 text-sm text-text">
          Не удалось загрузить локальную подложку. Список и досье доступны; online fallback не выполняется.
        </div>
      )}
      {unplacedCount > 0 && (
        <p role="status" className="border-t border-border px-4 py-3 text-sm font-medium text-warning">
          {`Не удалось показать на карте: ${unplacedCount}`}
        </p>
      )}
    </section>
  );
}
