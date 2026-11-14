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
    address: 'Владивосток, улица 1-я Пригородная, дом 1',
    district: 'Советский',
    lat: 43.281878,
    lon: 132.053021,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 462025005,
  },
  {
    house_id: 'house_000002',
    address: 'Владивосток, улица Верхнепортовая, дом 41б',
    district: 'Фрунзенский',
    lat: 43.101069,
    lon: 131.866521,
    coordinate_source: 'owner_provided',
    osm_way_id: null,
  },
  {
    house_id: 'house_000003',
    address: 'Владивосток, улица Всеволода Сибирцева, дом 20А',
    district: 'Ленинский',
    lat: 43.116845,
    lon: 131.902514,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 51863625,
  },
  {
    house_id: 'house_000004',
    address: 'Владивосток, улица Всеволода Сибирцева, дом 46',
    district: 'Ленинский',
    lat: 43.117612,
    lon: 131.913163,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 315439817,
  },
  {
    house_id: 'house_000005',
    address: 'Владивосток, улица Гамарника, дом 18Б',
    district: 'Первореченский',
    lat: 43.158382,
    lon: 131.916246,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 104478202,
  },
  {
    house_id: 'house_000006',
    address: 'Владивосток, улица Иртышская, дом 40',
    district: 'Первореченский',
    lat: 43.161949,
    lon: 131.929190,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 79723887,
  },
  {
    house_id: 'house_000007',
    address: 'Владивосток, улица Калинина, дом 6',
    district: 'Первомайский',
    lat: 43.102620,
    lon: 131.919061,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 106739163,
  },
  {
    house_id: 'house_000008',
    address: 'Владивосток, улица Калинина, дом 85',
    district: 'Первомайский',
    lat: 43.103070,
    lon: 131.905679,
    coordinate_source: 'owner_provided',
    osm_way_id: null,
  },
  {
    house_id: 'house_000009',
    address: 'Владивосток, улица Карбышева, дом 14',
    district: 'Первореченский',
    lat: 43.154805,
    lon: 131.923204,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 86981883,
  },
  {
    house_id: 'house_000010',
    address: 'Владивосток, улица Окатовая, дом 10',
    district: 'Первомайский',
    lat: 43.099126,
    lon: 131.918795,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 157025740,
  },
  {
    house_id: 'house_000011',
    address: 'Владивосток, улица Полетаева, дом 26',
    district: 'Советский',
    lat: 43.206261,
    lon: 131.959099,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 462225644,
  },
  {
    house_id: 'house_000012',
    address: 'Владивосток, улица Посьетская, дом 9',
    district: 'Фрунзенский',
    lat: 43.108426,
    lon: 131.877718,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 105464435,
  },
  {
    house_id: 'house_000013',
    address: 'Владивосток, улица Сабанеева, дом 14в',
    district: 'Первореченский',
    lat: 43.128665,
    lon: 131.950106,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 462462486,
  },
  {
    house_id: 'house_000014',
    address: 'Владивосток, улица Садгородская, дом 29',
    district: 'Советский',
    lat: 43.264275,
    lon: 132.021606,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 657744715,
  },
  {
    house_id: 'house_000015',
    address: 'Владивосток, улица Сафонова, дом 12',
    district: 'Первомайский',
    lat: 43.097003,
    lon: 131.949567,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 81952302,
  },
  {
    house_id: 'house_000016',
    address: 'Владивосток, улица Станюковича, дом 3',
    district: 'Фрунзенский',
    lat: 43.1100311,
    lon: 131.8749790,
    coordinate_source: 'osm_building_relation_centroid',
    osm_way_id: null,
    osm_relation_id: 8705579,
  },
  {
    house_id: 'house_000017',
    address: 'Владивосток, улица Тигровая, дом 23а',
    district: 'Фрунзенский',
    lat: 43.116031,
    lon: 131.877978,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 108437126,
  },
  {
    house_id: 'house_000018',
    address: 'Владивосток, улица Тобольская, дом 29',
    district: 'Ленинский',
    lat: 43.123190,
    lon: 131.932053,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 81968259,
  },
  {
    house_id: 'house_000019',
    address: 'Владивосток, улица Третья, дом 7а',
    district: 'Советский',
    lat: 43.230961,
    lon: 132.000089,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 632699502,
  },
  {
    house_id: 'house_000020',
    address: 'Владивосток, улица Шилкинская, дом 10',
    district: 'Ленинский',
    lat: 43.119701,
    lon: 131.921495,
    coordinate_source: 'osm_building_way_centroid',
    osm_way_id: 60341454,
  },
];
