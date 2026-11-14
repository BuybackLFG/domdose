import type { HouseId } from './types';

export type District =
  | 'Ленинский'
  | 'Первомайский'
  | 'Первореченский'
  | 'Советский'
  | 'Фрунзенский';

export interface PilotHouseGeo {
  house_id: HouseId;
  address: string;
  district: District;
  lat: number | null;
  lon: number | null;
  coordinate_source:
    | 'osm_building_way_centroid'
    | 'osm_building_relation_centroid'
    | 'owner_provided'
    | null;
  osm_way_id: number | null;
  osm_relation_id?: number | null;
}

export const PILOT_HOUSES: readonly PilotHouseGeo[] = [
  {
    house_id: 'house_000001',
    address: 'Владивосток, переулок Шевченко, дом 4',
    district: 'Фрунзенский',
    lat: 43.123466,
    lon: 131.877083,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 158652939,
  },
  {
    house_id: 'house_000002',
    address: 'Владивосток, проспект 100-летия Владивостока, дом 129',
    district: 'Советский',
    lat: 43.171858,
    lon: 131.915612,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 166558361,
  },
  {
    house_id: 'house_000003',
    address: 'Владивосток, проспект 100-летия Владивостока, дом 153',
    district: 'Советский',
    lat: 43.178971,
    lon: 131.916926,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 95912559,
  },
  {
    house_id: 'house_000004',
    address: 'Владивосток, проспект 100-летия Владивостока, дом 54',
    district: 'Первореченский',
    lat: 43.155181,
    lon: 131.911845,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 40316923,
  },
  {
    house_id: 'house_000005',
    address: 'Владивосток, проспект Красного Знамени, дом 38',
    district: 'Фрунзенский',
    lat: 43.128174,
    lon: 131.897400,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 102124382,
  },
  {
    house_id: 'house_000006',
    address: 'Владивосток, проспект Острякова, дом 44',
    district: 'Фрунзенский',
    lat: 43.135083,
    lon: 131.898905,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 168693186,
  },
  {
    house_id: 'house_000007',
    address: 'Владивосток, улица 40 лет ВЛКСМ, дом 2/8',
    district: 'Первомайский',
    lat: 43.102541,
    lon: 131.934335,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 176907728,
  },
  {
    house_id: 'house_000008',
    address: 'Владивосток, улица Адмирала Кузнецова, дом 68',
    district: 'Ленинский',
    lat: 43.118681,
    lon: 131.944435,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 102246899,
  },
  {
    house_id: 'house_000009',
    address: 'Владивосток, улица Адмирала Фокина, дом 7А',
    district: 'Фрунзенский',
    lat: 43.118279,
    lon: 131.881616,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 102370329,
  },
  {
    house_id: 'house_000010',
    address: 'Владивосток, улица Борисенко, дом 66',
    district: 'Первомайский',
    lat: 43.096419,
    lon: 131.960659,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 81952508,
  },
  {
    house_id: 'house_000011',
    address: 'Владивосток, улица Вострецова, дом 36Б',
    district: 'Первореченский',
    lat: 43.145124,
    lon: 131.919370,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 470133512,
  },
  {
    house_id: 'house_000012',
    address: 'Владивосток, улица Героев Варяга, дом 2/2',
    district: 'Первореченский',
    lat: 43.161604,
    lon: 131.931144,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 525484722,
  },
  {
    house_id: 'house_000013',
    address: 'Владивосток, улица Громова, дом 12',
    district: 'Ленинский',
    lat: 43.109117,
    lon: 131.945481,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 470868266,
  },
  {
    house_id: 'house_000014',
    address: 'Владивосток, улица Ковальчука, дом 26',
    district: 'Ленинский',
    lat: 43.115486,
    lon: 131.926707,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 471302726,
  },
  {
    house_id: 'house_000015',
    address: 'Владивосток, улица Лиманная, дом 176',
    district: 'Советский',
    lat: 43.289554,
    lon: 132.056433,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 462016243,
  },
  {
    house_id: 'house_000016',
    address: 'Владивосток, улица Маньчжурская, дом 15',
    district: 'Ленинский',
    lat: 43.115236,
    lon: 131.916957,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 471302233,
  },
  {
    house_id: 'house_000017',
    address: 'Владивосток, улица Патрокл, дом 11',
    district: 'Первомайский',
    lat: 43.093341,
    lon: 131.936491,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 81952527,
  },
  {
    house_id: 'house_000018',
    address: 'Владивосток, улица Русская, дом 51',
    district: 'Советский',
    lat: 43.170289,
    lon: 131.924775,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 71879251,
  },
  {
    house_id: 'house_000019',
    address: 'Владивосток, улица Терешковой, дом 9',
    district: 'Первомайский',
    lat: 43.095350,
    lon: 131.915380,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 78490054,
  },
  {
    house_id: 'house_000020',
    address: 'Владивосток, улица Тухачевского, дом 46',
    district: 'Первореченский',
    lat: 43.159985,
    lon: 131.930626,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 86982447,
  },
];
