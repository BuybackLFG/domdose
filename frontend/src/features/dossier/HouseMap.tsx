import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { PILOT_HOUSES } from './pilotHouses';
import { PILOT_MAP } from './map/pilotMap';
import type { HouseId, HouseSummary } from './types';

interface HouseMapProps {
  houses: HouseSummary[];
  selectedHouseId: HouseId | null;
  onSelectHouse: (houseId: HouseId) => void;
}

interface PlacedHouse extends HouseSummary {
  lat: number;
  lon: number;
}

function markerIcon(selected: boolean): L.DivIcon {
  return L.divIcon({
    className: `house-marker${selected ? ' house-marker-selected' : ''}`,
    html: '<span></span>',
    iconSize: selected ? [24, 24] : [18, 18],
    iconAnchor: selected ? [12, 12] : [9, 9],
  });
}

export function HouseMap({ houses, selectedHouseId, onSelectHouse }: HouseMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<HouseId, L.Marker>>(new Map());
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

  const knownCoordinates = useMemo(
    () => PILOT_HOUSES.filter((house) => house.lat !== null && house.lon !== null).length,
    [],
  );

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const southWest: [number, number] = [PILOT_MAP.southWest.lat, PILOT_MAP.southWest.lng];
    const northEast: [number, number] = [PILOT_MAP.northEast.lat, PILOT_MAP.northEast.lng];
    const bounds = L.latLngBounds(southWest, northEast);

    const map = L.map(containerRef.current, {
      center: bounds.getCenter(),
      zoom: 12,
      zoomControl: true,
      attributionControl: true,
      keyboard: true,
      scrollWheelZoom: false,
      minZoom: 11,
      maxZoom: 17,
      zoomSnap: 0.5,
      maxBounds: bounds.pad(0.05),
      maxBoundsViscosity: 1,
      zoomAnimation: !reduceMotion,
      fadeAnimation: !reduceMotion,
      markerZoomAnimation: !reduceMotion,
    });
    // Prefix Leaflet по умолчанию содержит внешнюю ссылку; attribution — только текст manifest.
    map.attributionControl.setPrefix(false);

    const overlay = L.imageOverlay(
      PILOT_MAP.imageUrl,
      bounds,
      {
        attribution: PILOT_MAP.attribution,
        interactive: false,
        alt: 'Карта Владивостока с домами пилотной выборки',
      },
    ).addTo(map);
    overlay.on('error', () => setAssetError(true));
    map.fitBounds(bounds);

    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(containerRef.current);
    mapRef.current = map;

    const markers = markersRef.current;
    return () => {
      observer.disconnect();
      for (const marker of markers.values()) marker.remove();
      markers.clear();
      map.remove();
      mapRef.current = null;
      setAssetError(false);
    };
  }, []);

  useEffect(() => {
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

    const selected = placedHouses.find((house) => house.house_id === selectedHouseId);
    if (selected) {
      map.panTo([selected.lat, selected.lon], {
        animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      });
    }
  }, [placedHouses, selectedHouseId]);

  return (
    <section aria-labelledby="house-map-heading" className="overflow-hidden rounded-2xl bg-surface shadow-sm ring-1 ring-border">
      <h2 id="house-map-heading" className="sr-only">Карта пилотной выборки</h2>
      <div ref={containerRef} className="h-80 w-full sm:h-105 lg:h-120" aria-label="Карта пилотной выборки" />
      {assetError && (
        <div role="alert" className="border-t border-danger/30 bg-danger/10 px-4 py-3 text-sm text-text">
          Не удалось загрузить локальную подложку. Список и досье доступны; online fallback не выполняется.
        </div>
      )}
      {knownCoordinates < PILOT_HOUSES.length && (
        <p className="border-t border-border px-4 py-3 text-sm font-medium text-warning" role="status">
          Координаты доступны не для всех домов: {knownCoordinates} из {PILOT_HOUSES.length}.
        </p>
      )}
    </section>
  );
}
