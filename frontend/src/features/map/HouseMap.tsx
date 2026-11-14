import L from 'leaflet'
import type { GeoJsonObject } from 'geojson'
import coastline from './coastline.json'
import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { PRED_HOUSES, type PredHouseGeo } from './predHouses'
import { PILOT_MAP } from './pilotMap'

export interface HouseMapProps {
  selectedHouseId?: string | null
  onSelectHouse: (houseId: string) => void
}

/** Отступ начального вида от крайних маркеров, px. */
const MARKER_FIT_PADDING = 32

/** Доля вида у каждого края, попадание выбранного дома в которую сдвигает карту. */
const VIEW_EDGE_SHARE = 0.1

// Внешний обзор содержит упрощённую береговую линию OSM.
const OVERVIEW_BOUNDS = L.latLngBounds([42.7, 130.8], [43.7, 133.2])

const OVERLAY_BOUNDS = L.latLngBounds(
  [PILOT_MAP.southWest.lat, PILOT_MAP.southWest.lng],
  [PILOT_MAP.northEast.lat, PILOT_MAP.northEast.lng],
)

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function markerIcon(selected: boolean): L.DivIcon {
  return L.divIcon({
    className: `house-marker${selected ? ' house-marker-selected' : ''}`,
    html: '<span></span>',
    iconSize: selected ? [24, 24] : [18, 18],
    iconAnchor: selected ? [12, 12] : [9, 9],
  })
}

/**
 * Ставит minZoom так, чтобы внешний обзор целиком помещался в контейнер.
 * `getBoundsZoom` ограничен текущим minZoom снизу, поэтому он сначала сбрасывается.
 */
function applyOverviewMinZoom(map: L.Map): boolean {
  const size = map.getSize()
  if (size.x === 0 || size.y === 0) return false
  map.setMinZoom(0)
  map.setMinZoom(map.getBoundsZoom(OVERVIEW_BOUNDS, false))
  return true
}

/** Вписывает вид во все маркеры с отступом; зум не ниже обзорного minZoom. */
function fitToHouses(map: L.Map, houses: readonly PredHouseGeo[]): boolean {
  if (houses.length === 0 || !applyOverviewMinZoom(map)) return false
  const size = map.getSize()
  if (size.x <= 2 * MARKER_FIT_PADDING || size.y <= 2 * MARKER_FIT_PADDING) return false
  map.fitBounds(
    L.latLngBounds(houses.map((house): L.LatLngTuple => [house.lat, house.lon])),
    { padding: [MARKER_FIT_PADDING, MARKER_FIT_PADDING], animate: false },
  )
  return true
}

/** URL подложки для зума: детальный уровень с detailMinZoom, иначе обзорный. */
function imageUrlForZoom(zoom: number): string {
  return zoom >= PILOT_MAP.detailMinZoom ? PILOT_MAP.detailImageUrl : PILOT_MAP.imageUrl
}

/** Сдвигает вид к выбранному дому, только если он вне вида или у самого края. */
function revealHouse(map: L.Map, house: PredHouseGeo | undefined, animate: boolean): void {
  if (!house || map.getBounds().pad(-VIEW_EDGE_SHARE).contains([house.lat, house.lon])) return
  map.panTo([house.lat, house.lon], { animate })
}

export function HouseMap({ selectedHouseId = null, onSelectHouse }: HouseMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<Map<string, L.Marker>>(new Map())
  const selectedIdRef = useRef<string | null>(selectedHouseId)
  const fittedRef = useRef(false)
  const selectRef = useRef(onSelectHouse)
  const [assetError, setAssetError] = useState(false)
  selectRef.current = onSelectHouse
  selectedIdRef.current = selectedHouseId

  const geoById = useMemo(() => new Map(PRED_HOUSES.map((house) => [house.id, house])), [])

  useEffect(() => {
    const container = containerRef.current
    if (!container || mapRef.current) return

    const reduceMotion = prefersReducedMotion()
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
    })
    map.zoomControl.getContainer()?.querySelector('.leaflet-control-zoom-in')?.setAttribute('aria-label', 'Приблизить карту')
    map.zoomControl.getContainer()?.querySelector('.leaflet-control-zoom-out')?.setAttribute('aria-label', 'Отдалить карту')
    // Prefix Leaflet по умолчанию содержит внешнюю ссылку; attribution — только текст manifest.
    map.attributionControl.setPrefix(false)

    L.rectangle(OVERVIEW_BOUNDS, { stroke: false, fillColor: '#aad3df', fillOpacity: 1, interactive: false }).addTo(map)
    L.geoJSON(coastline as GeoJsonObject, { style: { stroke: false, fillColor: '#f2efe9', fillOpacity: 1 }, interactive: false }).addTo(map)

    // Один оверлей на тех же bounds: при смене уровня меняется только src.
    let currentImageUrl = imageUrlForZoom(map.getZoom())
    const overlay = L.imageOverlay(currentImageUrl, OVERLAY_BOUNDS, {
      attribution: PILOT_MAP.attribution,
      interactive: false,
      alt: 'Карта Владивостока',
    }).addTo(map)
    overlay.on('error', () => setAssetError(true))

    const syncImageUrl = () => {
      const next = imageUrlForZoom(map.getZoom())
      if (next === currentImageUrl) return
      currentImageUrl = next
      overlay.setUrl(next)
    }
    map.on('zoomend', syncImageUrl)

    applyOverviewMinZoom(map)
    map.setView(OVERVIEW_BOUNDS.getCenter(), map.getMinZoom(), { animate: false })
    syncImageUrl()

    // Размер контейнера может появиться или измениться позже: покрытие и начальный вид
    // пересчитываются по факту измерения.
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false })
      if (!applyOverviewMinZoom(map)) return
      if (!fittedRef.current && fitToHouses(map, PRED_HOUSES)) {
        fittedRef.current = true
        revealHouse(map, geoById.get(selectedIdRef.current ?? ''), false)
      }
      map.panInsideBounds(OVERVIEW_BOUNDS, { animate: false })
    })
    observer.observe(container)
    mapRef.current = map

    const markers = markersRef.current
    return () => {
      observer.disconnect()
      map.off('zoomend', syncImageUrl)
      for (const marker of markers.values()) marker.remove()
      markers.clear()
      map.remove()
      mapRef.current = null
      fittedRef.current = false
      setAssetError(false)
    }
  }, [geoById])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const nextIds = new Set(PRED_HOUSES.map((house) => house.id))
    for (const [houseId, marker] of markersRef.current) {
      if (!nextIds.has(houseId)) {
        marker.remove()
        markersRef.current.delete(houseId)
      }
    }

    for (const house of PRED_HOUSES) {
      const selected = house.id === selectedHouseId
      let marker = markersRef.current.get(house.id)
      if (!marker) {
        marker = L.marker([house.lat, house.lon], {
          icon: markerIcon(selected),
          keyboard: true,
          title: house.address,
          alt: `${house.address}${selected ? ' (выбран)' : ''}`,
          riseOnHover: true,
        }).addTo(map)
        marker.on('click', () => selectRef.current(house.id))
        markersRef.current.set(house.id, marker)
      } else {
        marker.setLatLng([house.lat, house.lon])
        marker.setIcon(markerIcon(selected))
        marker.setZIndexOffset(selected ? 1000 : 0)
      }

      const label = document.createElement('span')
      label.textContent = house.address
      marker.bindTooltip(label, {
        permanent: false,
        direction: 'top',
        offset: [0, -14],
        className: 'house-marker-label',
      })
    }

    if (!fittedRef.current) fittedRef.current = fitToHouses(map, PRED_HOUSES)
    if (fittedRef.current) {
      revealHouse(map, geoById.get(selectedHouseId ?? ''), !prefersReducedMotion())
    }
  }, [geoById, selectedHouseId])

  return (
    <section
      aria-labelledby="house-map-heading"
      className="isolate overflow-hidden rounded-2xl bg-slate-900 ring-1 ring-slate-800"
    >
      <div className="flex items-baseline justify-between gap-3 px-4 pt-4">
        <h2 id="house-map-heading" className="text-sm font-semibold text-slate-200">
          Карта домов
        </h2>
        <span className="text-xs text-slate-500">{PRED_HOUSES.length} домов</span>
      </div>
      <div
        ref={containerRef}
        className="h-80 w-full sm:h-[26rem] lg:h-[30rem]"
        aria-label="Карта домов Владивостока"
      />
      {assetError && (
        <div
          role="alert"
          className="border-t border-rose-900/60 bg-rose-950/40 px-4 py-3 text-sm text-rose-200"
        >
          Не удалось загрузить локальную подложку. Список и досье доступны; online fallback не выполняется.
        </div>
      )}
      <p className="border-t border-slate-800 px-4 py-2 text-xs text-slate-500">
        © OpenStreetMap contributors, ODbL 1.0. Координаты домов приближённые.
      </p>
    </section>
  )
}
