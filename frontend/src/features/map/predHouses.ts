/**
 * Геометрия 20 домов каталога `pred_main`.
 *
 * Координаты — приближённые центроиды зданий из Nominatim/OpenStreetMap.
 * Они не являются геодезическими точками входов. Адреса и ID должны совпадать
 * с `data/datasets/communal-outages-2026.json`; при изменении каталога
 * координаты проверяются отдельно.
 */
export interface PredHouseGeo {
  id: string
  address: string
  district: string
  lat: number
  lon: number
  coordinate_source: 'osm_nominatim'
}

export const PRED_HOUSES: readonly PredHouseGeo[] = [
  {
    id: 'h-01',
    address: 'ул. Ковальчука, 26',
    district: 'Ленинский',
    lat: 43.1154861,
    lon: 131.9267071,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-02',
    address: 'ул. Адмирала Кузнецова, 68',
    district: 'Ленинский',
    lat: 43.1186805,
    lon: 131.9444346,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-03',
    address: 'ул. Громова, 12',
    district: 'Ленинский',
    lat: 43.1091174,
    lon: 131.9454811,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-04',
    address: 'ул. Маньчжурская, 15',
    district: 'Ленинский',
    lat: 43.1152362,
    lon: 131.9169575,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-05',
    address: 'ул. Терешковой, 9',
    district: 'Первомайский',
    lat: 43.0953504,
    lon: 131.9153805,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-06',
    address: 'ул. 40 лет ВЛКСМ, 2/8',
    district: 'Первомайский',
    lat: 43.1025408,
    lon: 131.9343348,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-07',
    address: 'ул. Патрокл, 11',
    district: 'Первомайский',
    lat: 43.0933412,
    lon: 131.9364911,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-08',
    address: 'ул. Борисенко, 66',
    district: 'Первомайский',
    lat: 43.0964192,
    lon: 131.9606586,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-09',
    address: 'ул. Тухачевского, 46',
    district: 'Первореченский',
    lat: 43.1599846,
    lon: 131.9306258,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-10',
    address: 'ул. Героев Варяга, 2/2',
    district: 'Первореченский',
    lat: 43.1616041,
    lon: 131.9311445,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-11',
    address: 'ул. Вострецова, 36Б',
    district: 'Первореченский',
    lat: 43.1451238,
    lon: 131.9193698,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-12',
    address: 'пр-кт 100-летия Владивостока, 54',
    district: 'Первореченский',
    lat: 43.155181,
    lon: 131.9118445,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-13',
    address: 'ул. Лиманная, 176',
    district: 'Советский',
    lat: 43.2895537,
    lon: 132.0564331,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-14',
    address: 'пр-кт 100-летия Владивостока, 153',
    district: 'Советский',
    lat: 43.1789714,
    lon: 131.9169262,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-15',
    address: 'ул. Русская, 51',
    district: 'Советский',
    lat: 43.1702888,
    lon: 131.9247751,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-16',
    address: 'пр-кт 100-летия Владивостока, 129',
    district: 'Советский',
    lat: 43.1718577,
    lon: 131.9156123,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-17',
    address: 'пер. Шевченко, 4',
    district: 'Фрунзенский',
    lat: 43.1234665,
    lon: 131.8770827,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-18',
    address: 'пр-кт Острякова, 44',
    district: 'Фрунзенский',
    lat: 43.1350834,
    lon: 131.8989046,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-19',
    address: 'ул. Адмирала Фокина, 7А',
    district: 'Фрунзенский',
    lat: 43.1182785,
    lon: 131.8816163,
    coordinate_source: 'osm_nominatim',
  },
  {
    id: 'h-20',
    address: 'пр-кт Красного Знамени, 38',
    district: 'Фрунзенский',
    lat: 43.1281736,
    lon: 131.8974,
    coordinate_source: 'osm_nominatim',
  },
]
