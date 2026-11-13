# Логические роли «ДомДосье»

Этот Markdown-реестр и соседние `agents/*.md` — исходник логических `u-*` ролей. Нативная
регистрация отдельных пресетов в текущей OpenCode-среде не подтверждена:
`ACTIVATION_NOT_CHECKED`.

Вызов выполняется через фактически доступный
`subagent(agent="explore"|"general", model=..., prompt=...)`. В самостоятельном prompt указываются
логическая роль, путь к её определению, цель, разрешённая зона, ограничения и ожидаемый результат.
Read-only роли используют `explore`, пишущие — `general`. Продолжение существующего ребёнка
выполняет родитель по его `sessionID`; ребёнок возвращает заказ другой роли финальным текстом.

## Реестр

| Логическая роль | Модель | Reasoning | Нативный agent | Назначение |
|---|---|---|---|---|
| `u-agentsmith` | `kimi-code-plan-global/k3.1-pro` | `high` | `general` | Персоны, логические роли, модели и границы полномочий |
| `u-analyst` | `kimi-code-plan-global/k3.1-pro` | `high` | `explore` | Причинный разбор потерь, аномалий и метрик без правок |
| `u-architect` | `kimi-code-plan-global/k3.1-pro` | `max` | `explore` | Контракты, границы и декомпозиция крупных изменений |
| `u-executor` | `kimi-code-plan-global/kimi-for-coding` | `high` | `general` | Минимальная реализация готового плана |
| `u-explorer` | `kimi-code-plan-global/k3.1-pro` | `low` | `explore` | Широкая разведка кода, потребителей и конфигурации |
| `u-frontend` | `kimi-code-plan-global/kimi-for-coding` | `high` | `general` | React/TypeScript-интерфейс и его основные/визуальные проверки |
| `u-golden` | `kimi-code-plan-global/k3.1-pro` | `high` | `general` | Независимые эталоны и мерила, особенно для скоринга |
| `u-lawsmith` | `kimi-code-plan-global/k3.1-pro` | `low` | `general` | Гигиена регламента без изменения смысла |
| `u-ops` | `kimi-code-plan-global/kimi-for-coding` | `low` | `general` | Среда, сборка, прогоны и согласованные эксплуатационные операции |
| `u-planner` | `kimi-code-plan-global/k3.1-pro` | `high` | `explore` | Разведка и самостоятельный план одной нетривиальной правки |
| `u-prompt` | `kimi-code-plan-global/k3.1-pro` | `high` | `general` | Черновики промптов и схем с независимой приёмкой |
| `u-refactor` | `kimi-code-plan-global/kimi-for-coding` | `low` | `general` | Поведенчески нейтральная гигиена кода |
| `u-researcher` | `kimi-code-plan-global/k3.1-pro` | `high` | `explore` | Внешние источники и проверка технических гипотез |
| `u-reviewer` | `kimi-code-plan-global/k3.1-pro` | `high` | `explore` | Независимое ревью корректности, рисков и проверок |
| `u-tester` | `kimi-code-plan-global/k3.1-pro` | `high` | `general` | Независимые проверки до исправления; строгий контур скоринга |

## Reasoning

Уровень в таблице — стартовая рекомендация. Диспетчер учитывает конкретную задачу: `low` для
простого и механического, `high` для обычной сложности, `max` для архитектуры, скоринга,
сложного анализа и рискованного ревью. Для `k3.1-pro` допустимы `low`, `high`, `max`; для
`kimi-for-coding` — `none`, `low`, `high`, `max`, причём `none` подходит только простым
детерминированным действиям.

Поля `dsh_*` в frontmatter сохранены как декларативные метаданные существующего профиля. Они не
подтверждают наличие отдельного генератора, сборки пакета, нативной регистрации или дополнительных
API в текущей среде.
