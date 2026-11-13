import { SearchPage } from './features/search/SearchPage'
import { HousePage, NotFoundPage } from './features/house/HousePage'
import { matchHouseId, usePathname } from './lib/router'

export default function App() {
  const pathname = usePathname()
  const houseId = matchHouseId(pathname)

  if (houseId) return <HousePage key={houseId} houseId={houseId} />
  if (pathname !== '/') return <NotFoundPage />

  return <SearchPage />
}
