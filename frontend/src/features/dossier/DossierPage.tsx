import { useMemo } from 'react';
import { CategoryScores } from './CategoryScores';
import { HouseEvents } from './HouseEvents';
import { HouseList } from './HouseList';
import { HouseMap } from './HouseMap';
import { HouseSearch } from './HouseSearch';
import { HouseSummary } from './HouseSummary';
import { PILOT_HOUSES } from './pilotHouses';
import { useHouseDossier } from './useHouseDossier';
import { WeakestCategory } from './WeakestCategory';

export function DossierPage() {
  const dossier = useHouseDossier();
  const {
    list,
    listErrorMessage,
    selectedHouse,
    selectedHouseId,
    detail,
    detailErrorMessage,
    query,
    search,
    selectHouse,
    updateQuery,
    moveSearchActive,
    submitSearch,
    retryList,
    retryDetail,
  } = dossier;

  const districts = useMemo(
    () => new Map(PILOT_HOUSES.map((house) => [house.house_id, house.district] as const)),
    [],
  );

  const houses = useMemo(() => (list.status === 'success' ? list.data.houses : []), [list]);

  return (
    <div className="min-h-screen pb-[env(safe-area-inset-bottom)]">
      <a href="#house-summary-heading" className="skip-link">Перейти к сводке дома</a>
      <a href="#house-list-heading" className="skip-link">Перейти к списку домов</a>

      <header className="px-4 pb-5 pt-7 sm:px-6 sm:pt-10">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">ДомДосье</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-text sm:text-3xl">
            Коммунальная надёжность домов
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
            Приближённые данные по публичным объявлениям об отключениях. Дома сравниваются между
            собой, а не со всем Владивостоком.
          </p>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-5 px-4 pb-12 sm:gap-6 sm:px-6">
        <HouseSearch
          query={query}
          search={search}
          onQueryChange={updateQuery}
          onMoveActive={moveSearchActive}
          onSubmit={submitSearch}
          onSelect={selectHouse}
        />

        <HouseMap
          houses={houses}
          selectedHouseId={selectedHouseId}
          onSelectHouse={selectHouse}
        />

        {list.status === 'loading' && (
          <section aria-labelledby="list-loading-heading" className="rounded-2xl bg-surface p-4 shadow-sm ring-1 ring-border sm:p-5">
            <h2 id="list-loading-heading" className="sr-only">Загрузка списка домов</h2>
            <p role="status" className="loading-pulse text-sm font-medium text-text-secondary">
              Загружаем дома…
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" aria-hidden="true">
              {Array.from({ length: 8 }, (_, index) => (
                <div key={index} className="h-16 rounded-xl bg-surface-subtle" />
              ))}
            </div>
          </section>
        )}

        {list.status === 'error' && (
          <section role="alert" className="rounded-2xl border border-danger/30 bg-danger/10 p-4 sm:p-5">
            <h2 className="text-base font-semibold text-text">{listErrorMessage}</h2>
            <p className="mt-1 text-sm text-text-secondary">
              Пустая выборка или правдоподобный ноль не подставляются.
            </p>
            <button
              type="button"
              onClick={retryList}
              className="mt-3 min-h-11 rounded-xl bg-accent px-4 text-sm font-medium text-white transition hover:bg-accent-hover"
            >
              Повторить загрузку
            </button>
          </section>
        )}

        {list.status === 'success' && selectedHouse && (
          <>
            <HouseSummary
              house={selectedHouse}
              district={districts.get(selectedHouse.house_id) ?? null}
              detail={detail}
              errorMessage={detailErrorMessage}
              onRetryDetail={retryDetail}
            />
            {detail.status === 'success' && (
              // key сбрасывает фильтр и пагинацию событий при смене дома.
              <HouseEvents key={detail.data.house_id} events={detail.data.events} />
            )}
            <CategoryScores detail={detail} />
            {detail.status === 'success' && <WeakestCategory detail={detail.data} />}
          </>
        )}

        {list.status === 'success' && (
          <HouseList
            houses={houses}
            districts={districts}
            selectedHouseId={selectedHouseId}
            onSelect={selectHouse}
          />
        )}
      </main>
    </div>
  );
}
