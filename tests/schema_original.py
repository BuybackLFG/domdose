# ruff: noqa: E501
# The embedded dataset 1.0 schema is preserved verbatim; rewrapping it would
# alter the copied JSON text, so long source lines are intentional.
import json

ORIGINAL_SCHEMA = json.loads(r'''
{
  "type": "object",
  "description": "Датасет отключений коммунальных услуг во Владивостоке: городской журнал событий и выборка домов с паспортами. Только факты из источников; null означает «не удалось установить».",
  "additionalProperties": false,
  "required": ["meta", "houses", "events"],
  "properties": {
    "meta": {
      "type": "object",
      "description": "Сведения о датасете: период, источники, знаменатель для среднего по городу, ограничения.",
      "additionalProperties": false,
      "required": [
        "schema_version",
        "city",
        "timezone",
        "period",
        "heating_season_start",
        "generated_at",
        "city_houses",
        "sources",
        "limitations"
      ],
      "properties": {
        "schema_version": {
          "type": "string",
          "enum": ["1.0"],
          "description": "Версия формата."
        },
        "city": {
          "type": "string",
          "enum": ["Владивосток"],
          "description": "Город датасета."
        },
        "timezone": {
          "type": "string",
          "enum": ["Asia/Vladivostok"],
          "description": "Часовой пояс всех значений времени (UTC+10)."
        },
        "period": {
          "type": "object",
          "description": "Период наблюдения, обе даты включительно.",
          "additionalProperties": false,
          "required": ["from", "to"],
          "properties": {
            "from": {
              "type": "string",
              "format": "date",
              "description": "Первый день периода, ГГГГ-ММ-ДД."
            },
            "to": {
              "type": "string",
              "format": "date",
              "description": "Последний день периода, ГГГГ-ММ-ДД."
            }
          }
        },
        "heating_season_start": {
          "anyOf": [{ "type": "string", "format": "date" }, { "type": "null" }],
          "description": "Дата начала подачи отопления в жилые дома по официальному сообщению. null, если дата не найдена."
        },
        "generated_at": {
          "type": "string",
          "format": "date-time",
          "description": "Момент формирования датасета, ISO 8601 со смещением +10:00."
        },
        "city_houses": {
          "type": "object",
          "description": "Число многоквартирных домов в городе и по районам. Знаменатель для расчёта среднего по городу.",
          "additionalProperties": false,
          "required": ["total", "by_district", "source_url"],
          "properties": {
            "total": {
              "anyOf": [{ "type": "integer" }, { "type": "null" }],
              "description": "Всего многоквартирных домов в городе. null, если официальная цифра не найдена."
            },
            "by_district": {
              "type": "object",
              "description": "Число многоквартирных домов по административным районам.",
              "additionalProperties": false,
              "required": ["Ленинский", "Первомайский", "Первореченский", "Советский", "Фрунзенский"],
              "properties": {
                "Ленинский": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
                "Первомайский": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
                "Первореченский": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
                "Советский": { "anyOf": [{ "type": "integer" }, { "type": "null" }] },
                "Фрунзенский": { "anyOf": [{ "type": "integer" }, { "type": "null" }] }
              }
            },
            "source_url": {
              "anyOf": [{ "type": "string" }, { "type": "null" }],
              "description": "Страница, с которой взяты цифры. null, если цифры не найдены."
            }
          }
        },
        "sources": {
          "type": "array",
          "description": "Источники, из которых реально взяты записи датасета.",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["id", "name", "url", "types", "covered_from", "covered_to"],
            "properties": {
              "id": {
                "type": "string",
                "description": "Идентификатор источника вида src-1. На него ссылаются события."
              },
              "name": {
                "type": "string",
                "description": "Название источника."
              },
              "url": {
                "type": "string",
                "description": "Адрес раздела или канала с объявлениями об отключениях."
              },
              "types": {
                "type": "array",
                "description": "Категории отключений, которые источник покрывает.",
                "items": { "$ref": "#/$defs/outage_type" }
              },
              "covered_from": {
                "anyOf": [{ "type": "string", "format": "date" }, { "type": "null" }],
                "description": "С какой даты источник реально дал данные внутри периода. null, если установить нельзя."
              },
              "covered_to": {
                "anyOf": [{ "type": "string", "format": "date" }, { "type": "null" }],
                "description": "По какую дату источник реально дал данные внутри периода. null, если установить нельзя."
              }
            }
          }
        },
        "limitations": {
          "type": "array",
          "description": "Ограничения и пробелы датасета простыми фразами: неполные архивы, недоступные источники, районы без данных, отсутствие доступа к сети.",
          "items": { "type": "string" }
        }
      }
    },
    "houses": {
      "type": "array",
      "description": "Выборка домов: 20–25 реальных многоквартирных домов, по 4–5 на район, включая по одному контрольному.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "address",
          "district",
          "fias_id",
          "lat",
          "lon",
          "year_built",
          "floors",
          "apartments",
          "management_company",
          "services",
          "is_control",
          "passport_source_url"
        ],
        "properties": {
          "id": {
            "type": "string",
            "description": "Идентификатор дома вида h-01."
          },
          "address": {
            "type": "string",
            "description": "Нормализованный адрес без города: «ул. Русская, 57а»."
          },
          "district": { "$ref": "#/$defs/district" },
          "fias_id": {
            "anyOf": [{ "type": "string" }, { "type": "null" }],
            "description": "Идентификатор дома в ФИАС/ГАР. null, если не найден."
          },
          "lat": {
            "anyOf": [{ "type": "number" }, { "type": "null" }],
            "description": "Широта в градусах. null, если не установлена."
          },
          "lon": {
            "anyOf": [{ "type": "number" }, { "type": "null" }],
            "description": "Долгота в градусах. null, если не установлена."
          },
          "year_built": {
            "anyOf": [{ "type": "integer" }, { "type": "null" }],
            "description": "Год постройки."
          },
          "floors": {
            "anyOf": [{ "type": "integer" }, { "type": "null" }],
            "description": "Наибольшая этажность."
          },
          "apartments": {
            "anyOf": [{ "type": "integer" }, { "type": "null" }],
            "description": "Число квартир."
          },
          "management_company": {
            "anyOf": [{ "type": "string" }, { "type": "null" }],
            "description": "Управляющая организация."
          },
          "services": {
            "type": "object",
            "description": "Как дом получает каждую услугу. Категория участвует в рейтинге только при значении central.",
            "additionalProperties": false,
            "required": ["hot_water", "cold_water", "electricity", "heating"],
            "properties": {
              "hot_water": { "$ref": "#/$defs/service_kind" },
              "cold_water": { "$ref": "#/$defs/service_kind" },
              "electricity": { "$ref": "#/$defs/service_kind" },
              "heating": { "$ref": "#/$defs/service_kind" }
            }
          },
          "is_control": {
            "type": "boolean",
            "description": "true для контрольного дома: за период не встретился ни в одном найденном объявлении."
          },
          "passport_source_url": {
            "anyOf": [{ "type": "string" }, { "type": "null" }],
            "description": "Страница, с которой взяты сведения о доме. null, если паспорт не найден."
          }
        }
      }
    },
    "events": {
      "type": "array",
      "description": "Городской журнал: все подтверждённые отключения за период. Одно событие — одно отключение одной категории после склейки дублей и продлений.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "type",
          "kind",
          "start",
          "end_planned",
          "end_actual",
          "duration_hours",
          "duration_basis",
          "cause",
          "organization",
          "scope",
          "force_majeure",
          "houses_affected",
          "districts",
          "addresses_raw",
          "addresses",
          "houses",
          "sources",
          "notes"
        ],
        "properties": {
          "id": {
            "type": "string",
            "description": "Идентификатор события вида evt-0001."
          },
          "type": { "$ref": "#/$defs/outage_type" },
          "kind": {
            "type": "string",
            "enum": ["planned", "emergency", "unknown"],
            "description": "planned — работы объявлены заранее как плановые; emergency — авария, повреждение, внеплановое отключение; unknown — из источника не понять."
          },
          "start": {
            "type": "string",
            "format": "date-time",
            "description": "Начало отключения, ISO 8601 со смещением +10:00."
          },
          "end_planned": {
            "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }],
            "description": "Заявленное время восстановления. null, если не указано."
          },
          "end_actual": {
            "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }],
            "description": "Фактическое время восстановления по сообщению источника. null, если источник его не сообщает."
          },
          "duration_hours": {
            "anyOf": [{ "type": "number" }, { "type": "null" }],
            "description": "Длительность в часах: от start до end_actual, а если его нет — до end_planned. null, если конец неизвестен."
          },
          "duration_basis": {
            "type": "string",
            "enum": ["actual", "planned", "unknown"],
            "description": "По какому времени посчитана длительность: actual — по факту, planned — по объявлению, unknown — длительность не установлена."
          },
          "cause": {
            "anyOf": [{ "type": "string" }, { "type": "null" }],
            "description": "Причина словами источника, кратко. null, если не названа."
          },
          "organization": {
            "anyOf": [{ "type": "string" }, { "type": "null" }],
            "description": "Организация, которая проводит работы или отвечает за сеть. null, если не названа."
          },
          "scope": {
            "type": "string",
            "enum": ["house", "group", "district", "city"],
            "description": "Масштаб: house — один дом; group — несколько перечисленных домов; district — микрорайон или район без перечня домов; city — весь город или несколько районов."
          },
          "force_majeure": {
            "type": "boolean",
            "description": "true, если причина — стихия или крупная авария на магистральном либо генерирующем объекте."
          },
          "houses_affected": {
            "anyOf": [{ "type": "integer" }, { "type": "null" }],
            "description": "Число затронутых домов по объявлению. null, если оценить нельзя."
          },
          "districts": {
            "type": "array",
            "description": "Районы, которые затронуло отключение.",
            "items": { "$ref": "#/$defs/district" }
          },
          "addresses_raw": {
            "type": "string",
            "description": "Перечень адресов дословно, как в источнике."
          },
          "addresses": {
            "type": "array",
            "description": "Адреса из объявления в нормализованном виде. Только однозначно названные дома; пустой массив для масштаба district и city.",
            "items": { "type": "string" }
          },
          "houses": {
            "type": "array",
            "description": "Дома выборки, которых коснулось событие. Пустой массив, если ни один дом выборки не затронут.",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["house_id", "match"],
              "properties": {
                "house_id": {
                  "type": "string",
                  "description": "Идентификатор дома из раздела houses."
                },
                "match": {
                  "type": "string",
                  "enum": ["exact", "range", "street"],
                  "description": "Как дом сопоставлен с объявлением: exact — дом назван прямо; range — попал в диапазон номеров; street — названа только улица."
                }
              }
            }
          },
          "sources": {
            "type": "array",
            "description": "Страницы, подтверждающие событие. Не меньше одной.",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["source_id", "url", "published_at"],
              "properties": {
                "source_id": {
                  "type": "string",
                  "description": "Идентификатор источника из meta.sources."
                },
                "url": {
                  "type": "string",
                  "description": "Прямая ссылка на объявление или сообщение."
                },
                "published_at": {
                  "anyOf": [{ "type": "string", "format": "date-time" }, { "type": "null" }],
                  "description": "Время публикации. null, если не указано."
                }
              }
            }
          },
          "notes": {
            "anyOf": [{ "type": "string" }, { "type": "null" }],
            "description": "Оговорки по записи: неточное время, склеенные продления, расхождения между источниками. null, если оговорок нет."
          }
        }
      }
    }
  },
  "$defs": {
    "district": {
      "type": "string",
      "enum": ["Ленинский", "Первомайский", "Первореченский", "Советский", "Фрунзенский"],
      "description": "Административный район Владивостока."
    },
    "outage_type": {
      "type": "string",
      "enum": ["hot_water", "cold_water", "electricity", "heating"],
      "description": "Категория отключения: горячая вода, холодная вода, электричество, отопление."
    },
    "service_kind": {
      "type": "string",
      "enum": ["central", "individual", "none", "unknown"],
      "description": "central — централизованная услуга; individual — собственный источник (котельная, бойлер); none — услуги нет; unknown — не установлено."
    }
  }
}

''')
