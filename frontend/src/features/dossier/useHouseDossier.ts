import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ClientError, isAbortError } from '../../lib/api';
import { fetchHouseDetail, fetchHouseList } from './api';
import { isListingUrl, searchHouses } from './search';
import type { HouseDetailResponse, HouseId, HouseListResponse, HouseSummary } from './types';

export type Loadable<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: ClientError };

export type SearchState =
  | { kind: 'idle' }
  | { kind: 'open'; matches: HouseSummary[]; activeIndex: number }
  | { kind: 'not_covered'; query: string }
  | { kind: 'unsupported_link'; query: string };

function sameSnapshot(
  left: Pick<HouseListResponse, 'scope' | 'window'>,
  right: Pick<HouseDetailResponse, 'scope' | 'window'>,
): boolean {
  return (
    left.scope.kind === right.scope.kind
    && left.scope.house_count === right.scope.house_count
    && left.scope.average_basis === right.scope.average_basis
    && left.window.start === right.window.start
    && left.window.end === right.window.end
  );
}

function publicMessage(error: ClientError): string {
  switch (error.kind) {
    case 'no_data':
      return 'Исходные данные недоступны. Рейтинг не рассчитан';
    case 'not_found':
      return 'Дом отсутствует в текущей пилотной выборке';
    case 'timeout':
      return 'Не удалось загрузить досье: превышено время ожидания';
    case 'invalid_response':
      return 'Набор данных не прошёл проверку полноты';
    default:
      return 'Не удалось загрузить досье';
  }
}

function listMessage(error: ClientError): string {
  switch (error.kind) {
    case 'no_data':
      return 'Исходные данные недоступны. Рейтинг не рассчитан';
    case 'invalid_response':
      return 'Набор данных не прошёл проверку полноты';
    default:
      return 'Не удалось связаться с сервером';
  }
}

export function useHouseDossier() {
  const [list, setList] = useState<Loadable<HouseListResponse>>({ status: 'idle' });
  const [selectedHouseId, setSelectedHouseId] = useState<HouseId | null>(null);
  const [detail, setDetail] = useState<Loadable<HouseDetailResponse>>({ status: 'idle' });
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState<SearchState>({ kind: 'idle' });
  const [listReloadToken, setListReloadToken] = useState(0);
  const [detailRetryToken, setDetailRetryToken] = useState(0);

  const listAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);
  const detailVersionRef = useRef(0);
  const selectedHouseIdRef = useRef<HouseId | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listAbortRef.current?.abort();
    listAbortRef.current = controller;
    let cancelled = false;

    setList({ status: 'loading' });
    fetchHouseList(controller.signal)
      .then((data) => {
        if (cancelled || controller.signal.aborted) return;
        setList({ status: 'success', data });
        setDetail({ status: 'loading' });
        setSelectedHouseId((current) => {
          const stillPresent = current !== null && data.houses.some((house) => house.house_id === current);
          return stillPresent ? current : data.houses[0].house_id;
        });
      })
      .catch((error: unknown) => {
        if (cancelled || isAbortError(error)) return;
        setList({
          status: 'error',
          error: error instanceof ClientError ? error : new ClientError('network', 'Не удалось связаться с сервером'),
        });
        setSelectedHouseId(null);
        setDetail({ status: 'idle' });
      });

    return () => {
      cancelled = true;
      controller.abort();
      if (listAbortRef.current === controller) listAbortRef.current = null;
    };
  }, [listReloadToken]);

  useEffect(() => {
    selectedHouseIdRef.current = selectedHouseId;
  }, [selectedHouseId]);

  const selectHouse = useCallback((houseId: HouseId) => {
    if (selectedHouseIdRef.current === houseId) return;
    selectedHouseIdRef.current = houseId;
    setSelectedHouseId(houseId);
    setDetail({ status: 'loading' });
  }, []);

  useEffect(() => {
    if (list.status !== 'success' || selectedHouseId === null) return;
    const house = list.data.houses.find((item) => item.house_id === selectedHouseId);
    if (!house) {
      setDetail({
        status: 'error',
        error: new ClientError('not_found', 'Дом отсутствует в текущей пилотной выборке'),
      });
      return;
    }

    detailAbortRef.current?.abort();
    const controller = new AbortController();
    detailAbortRef.current = controller;
    const requestVersion = ++detailVersionRef.current;
    setDetail({ status: 'loading' });

    fetchHouseDetail(selectedHouseId, controller.signal)
      .then((data) => {
        if (requestVersion !== detailVersionRef.current || controller.signal.aborted) return;
        if (data.house_id !== selectedHouseId || !sameSnapshot(list.data, data)) {
          setDetail({
            status: 'error',
            error: new ClientError('invalid_response', 'Набор данных не прошёл проверку полноты'),
          });
          return;
        }
        setDetail({ status: 'success', data });
      })
      .catch((error: unknown) => {
        if (requestVersion !== detailVersionRef.current || isAbortError(error)) return;
        const clientError = error instanceof ClientError
          ? error
          : new ClientError('network', 'Не удалось загрузить досье');
        setDetail({ status: 'error', error: clientError });
      });

    return () => {
      controller.abort();
      if (detailAbortRef.current === controller) detailAbortRef.current = null;
    };
  }, [list, selectedHouseId, detailRetryToken]);

  const updateQuery = useCallback((value: string) => {
    setQuery(value);
    if (isListingUrl(value)) {
      setSearch({ kind: 'unsupported_link', query: value });
      return;
    }

    const houses = list.status === 'success' ? list.data.houses : [];
    const matches = searchHouses(houses, value);
    if (!value.trim()) {
      setSearch({ kind: 'idle' });
    } else if (matches.length === 0) {
      setSearch({ kind: 'not_covered', query: value });
    } else {
      setSearch({ kind: 'open', matches, activeIndex: 0 });
    }
  }, [list]);

  const moveSearchActive = useCallback((direction: 1 | -1) => {
    setSearch((current) => {
      if (current.kind !== 'open' || current.matches.length === 0) return current;
      const next = (current.activeIndex + direction + current.matches.length) % current.matches.length;
      return { ...current, activeIndex: next };
    });
  }, []);

  const submitSearch = useCallback(() => {
    setSearch((current) => {
      if (current.kind === 'open' && current.matches[current.activeIndex]) {
        selectHouse(current.matches[current.activeIndex].house_id);
        setQuery('');
        return { kind: 'idle' };
      }
      return current;
    });
  }, [selectHouse]);

  const closeSearch = useCallback(() => {
    setSearch((current) => (current.kind === 'open' ? { ...current } : current));
  }, []);

  const retryList = useCallback(() => {
    setListReloadToken((token) => token + 1);
  }, []);

  const retryDetail = useCallback(() => {
    if (selectedHouseId === null) return;
    setDetail({ status: 'loading' });
    setDetailRetryToken((token) => token + 1);
  }, [selectedHouseId]);

  const selectedHouse = useMemo(() => {
    if (list.status !== 'success' || selectedHouseId === null) return null;
    return list.data.houses.find((house) => house.house_id === selectedHouseId) ?? null;
  }, [list, selectedHouseId]);

  return {
    list,
    listErrorMessage: list.status === 'error' ? listMessage(list.error) : null,
    selectedHouse,
    selectedHouseId,
    detail,
    detailErrorMessage: detail.status === 'error' ? publicMessage(detail.error) : null,
    query,
    search,
    selectHouse,
    updateQuery,
    moveSearchActive,
    submitSearch,
    closeSearch,
    retryList,
    retryDetail,
  };
}
