// Удобные алиасы над сгенерированными типами. Правится руками, api.ts — нет.
//
// Все типы контракта приходят из `api.ts`, который генерируется из OpenAPI.
// Если здесь не хватает алиаса — не пишите интерфейс руками, добавьте модель
// в `backend/schemas/` и перегенерируйте типы.
import type { components } from './api'

type Schemas = components['schemas']

// Служебное
export type HealthResponse = Schemas['HealthResponse']
export type ErrorResponse = Schemas['ErrorResponse']

// Дома и поиск
export type House = Schemas['House']
export type HouseSummary = Schemas['HouseSummary']
export type HouseList = Schemas['HouseList']
export type ComponentBrief = Schemas['ComponentBrief']

// Индекс
export type HouseIndex = Schemas['HouseIndex']
export type Component = Schemas['Component']
export type ComponentKey = Schemas['ComponentKey']

// События и факты
export type Event = Schemas['Event']
export type EventType = Schemas['EventType']
export type EventKind = Schemas['EventKind']
export type Fact = Schemas['Fact']
export type FactType = Schemas['FactType']
export type Source = Schemas['Source']

// Досье, сравнение, чек-лист
export type Dossier = Schemas['Dossier']
export type CompareResponse = Schemas['CompareResponse']
export type ChecklistItem = Schemas['ChecklistItem']

// Live-репорты
export type ReportCreate = Schemas['ReportCreate']
export type ReportResult = Schemas['ReportResult']
export type IndexChange = Schemas['IndexChange']
