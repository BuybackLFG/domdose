import { describe, expect, it } from 'vitest';
import { isListingUrl, normalizeHouseQuery, searchHouses } from './search';
import type { HouseSummary } from './types';

function house(id: number, address: string): HouseSummary {
  return {
    house_id: `house_${String(id).padStart(6, '0')}`,
    address,
    overall_score: 0.8,
  };
}

const HOUSES: HouseSummary[] = [
  house(1, 'Владивосток, улица Ёлочная, дом 1'),
  house(2, 'Владивосток, улица Лесная, дом 2'),
  house(3, 'Владивосток, улица Лесная, дом 3'),
];

describe('локальный поиск по пилотному каталогу', () => {
  it('находит один дом без учёта ё/е и служебных слов адреса', () => {
    expect(normalizeHouseQuery('  Ёлочная   Улица ')).toBe('елочная улица');
    expect(searchHouses(HOUSES, 'елочная 1').map((item) => item.house_id)).toEqual([
      'house_000001',
    ]);
  });

  it('возвращает несколько совпадений в исходном порядке для явного выбора', () => {
    expect(searchHouses(HOUSES, 'лесная').map((item) => item.house_id)).toEqual([
      'house_000002',
      'house_000003',
    ]);
  });

  it('возвращает пустой результат, а не ближайший или первый дом', () => {
    expect(searchHouses(HOUSES, 'Несуществующая 999')).toEqual([]);
  });

  it('распознаёт ссылку на объявление до любого сетевого сценария', () => {
    expect(isListingUrl('https://example.test/listing/42')).toBe(true);
    expect(isListingUrl('www.example.test/listing/42')).toBe(true);
    expect(isListingUrl('Владивосток, улица Лесная, дом 2')).toBe(false);
  });
});
