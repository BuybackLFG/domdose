"""Pure rating engine for ``rating_observed_exposure_proxy_v1``.

The engine reads only validated dataset facts and the normalized request.  It
never consults a clock, environment, files, network, logging or stdout.  Every
computation is deterministic over the input order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from contract.dataset import Dataset
from rating.models import (
    CATEGORY_ORDER,
    CATEGORY_WEIGHTS,
    MAXIMUM_METHOD,
    Baseline,
    CalculationReport,
    CategoryRating,
    Diagnostic,
    EffectiveWeight,
    HouseRating,
    MetricTriple,
    SourceInterval,
    SourceSpan,
    Window,
)
from rating.requests import ValidRequest

TZ10 = timezone(timedelta(hours=10))
WINDOW_SIZE = timedelta(days=30)
_MASS_SCOPES = frozenset(("district", "city"))
_AMBIGUOUS_MATCHES = frozenset(("range", "street"))
_MEASURES = ("frequency", "hours", "maximum")
_ANCHORS = ((1.0, 0.0), (2.0, 0.33), (4.0, 0.67), (8.0, 1.0))


@dataclass(frozen=True)
class _View:
    """One category event as seen through a clipped category window."""

    index: int
    event: Any
    weight: float | None
    duration: float | None
    overlap_uncertain: bool


@dataclass(frozen=True)
class _BaselineFlags:
    unknown_weight: bool
    unknown_duration: bool
    unknown_overlap: bool
    unknown_n: bool
    culprits: tuple[str, ...]


@dataclass(frozen=True)
class _CategoryContext:
    category: str
    window: tuple[datetime, datetime] | None
    season_unknown: bool
    views: tuple[_View, ...]
    baseline: Baseline
    flags: _BaselineFlags
    estimated: bool
    city_houses: int | None


def _empty_metrics() -> MetricTriple:
    return MetricTriple(frequency=None, hours=None, maximum=None)


def _empty_baseline(city_houses: int | None) -> Baseline:
    return Baseline(
        frequency=None,
        hours=None,
        maximum=None,
        city_houses=city_houses,
        exposures=None,
        maximum_method=MAXIMUM_METHOD,
    )


def _event_weight(event: Any) -> float | None:
    """Emergency 1, planned 0.4, unknown unavailable; one 0.5 mass/force factor."""
    if event.kind == "emergency":
        weight = 1.0
    elif event.kind == "planned":
        weight = 0.4
    else:
        return None
    if event.scope in _MASS_SCOPES or event.force_majeure:
        weight *= 0.5
    return weight


def _event_span(event: Any) -> tuple[datetime, datetime] | None:
    """Known span from the stored duration; an unknown basis never infers timing."""
    if event.duration_basis == "unknown" or event.duration_hours is None:
        return None
    return event.start, event.start + timedelta(hours=event.duration_hours)


def _build_views(
    dataset: Dataset, category: str, window: tuple[datetime, datetime]
) -> tuple[_View, ...]:
    """Clip category events to the half-open category window."""
    window_start, window_end = window
    views: list[_View] = []
    for index, event in enumerate(dataset.events):
        if event.type != category:
            continue
        span = _event_span(event)
        weight = _event_weight(event)
        if span is None:
            if event.start >= window_end:
                continue
            views.append(
                _View(
                    index=index,
                    event=event,
                    weight=weight,
                    duration=None,
                    overlap_uncertain=event.start < window_start,
                )
            )
            continue
        start_at, end_at = span
        if start_at >= window_end:
            continue
        if end_at < window_start:
            continue
        if end_at == window_start and start_at < window_start:
            continue
        clipped_start = max(start_at, window_start)
        clipped_end = min(end_at, window_end)
        duration = max(0.0, (clipped_end - clipped_start).total_seconds() / 3600.0)
        views.append(
            _View(
                index=index,
                event=event,
                weight=weight,
                duration=duration,
                overlap_uncertain=False,
            )
        )
    return tuple(views)


def _compute_baseline(
    views: tuple[_View, ...], city_houses: int | None
) -> tuple[Baseline, _BaselineFlags]:
    unknown_weight = any(view.weight is None for view in views)
    unknown_duration = any(view.duration is None for view in views)
    unknown_overlap = any(view.overlap_uncertain for view in views)
    unknown_n = any(view.event.houses_affected is None for view in views)
    culprits = tuple(
        view.event.id
        for view in views
        if view.weight is None
        or view.duration is None
        or view.overlap_uncertain
        or view.event.houses_affected is None
    )
    if unknown_n or unknown_overlap:
        exposures: int | None = None
    else:
        exposures = sum(int(view.event.houses_affected) for view in views)

    frequency: float | None = None
    hours: float | None = None
    maximum: float | None = None
    if city_houses is not None and not (unknown_weight or unknown_overlap or unknown_n):
        weighted_count = 0.0
        weighted_hours = 0.0
        exposure_sum = 0
        try:
            for view in views:
                affected = int(view.event.houses_affected)
                weighted_count += affected * view.weight
                exposure_sum += affected
                if view.duration is not None:
                    weighted_hours += affected * view.weight * view.duration
            frequency = weighted_count / city_houses
            if not unknown_duration:
                hours = weighted_hours / city_houses
                maximum = weighted_hours / exposure_sum if exposure_sum else 0.0
        except OverflowError:
            frequency = hours = maximum = None

    baseline = Baseline(
        frequency=frequency,
        hours=hours,
        maximum=maximum,
        city_houses=city_houses,
        exposures=exposures,
        maximum_method=MAXIMUM_METHOD,
    )
    flags = _BaselineFlags(
        unknown_weight=unknown_weight,
        unknown_duration=unknown_duration,
        unknown_overlap=unknown_overlap,
        unknown_n=unknown_n,
        culprits=culprits,
    )
    return baseline, flags


def _heating_window(
    dataset: Dataset, window: tuple[datetime, datetime]
) -> tuple[tuple[datetime, datetime] | None, bool]:
    """Return the season-clipped heating window and whether the season is unknown."""
    season_start = dataset.meta.heating_season_start
    if season_start is None:
        return None, True
    start = datetime(season_start.year, season_start.month, season_start.day, tzinfo=TZ10)
    if start >= window[1]:
        return None, False
    return (max(window[0], start), window[1]), False


def _build_context(
    dataset: Dataset, category: str, window: tuple[datetime, datetime], city_houses: int | None
) -> _CategoryContext:
    season_unknown = False
    category_window: tuple[datetime, datetime] | None = window
    if category == "heating":
        category_window, season_unknown = _heating_window(dataset, window)
        if season_unknown:
            flags = _BaselineFlags(False, False, False, False, ())
            return _CategoryContext(
                category=category,
                window=None,
                season_unknown=True,
                views=(),
                baseline=_empty_baseline(city_houses),
                flags=flags,
                estimated=False,
                city_houses=city_houses,
            )
        if category_window is None:
            baseline, flags = _compute_baseline((), city_houses)
            return _CategoryContext(
                category=category,
                window=None,
                season_unknown=False,
                views=(),
                baseline=baseline,
                flags=flags,
                estimated=False,
                city_houses=city_houses,
            )
    views = _build_views(dataset, category, category_window)
    baseline, flags = _compute_baseline(views, city_houses)
    estimated = any(
        view.event.duration_basis == "planned" and view.duration is not None for view in views
    )
    return _CategoryContext(
        category=category,
        window=category_window,
        season_unknown=season_unknown,
        views=views,
        baseline=baseline,
        flags=flags,
        estimated=estimated,
        city_houses=city_houses,
    )


def _penalty(ratio: float) -> float:
    """Piecewise linear in log2 through (1,0), (2,.33), (4,.67), (8,1)."""
    if ratio <= 1.0:
        return 0.0
    if ratio >= 8.0:
        return 1.0
    for (left_ratio, left_penalty), (right_ratio, right_penalty) in zip(_ANCHORS, _ANCHORS[1:]):
        if ratio <= right_ratio:
            position = (math.log2(ratio) - math.log2(left_ratio)) / (
                math.log2(right_ratio) - math.log2(left_ratio)
            )
            return left_penalty + (right_penalty - left_penalty) * position
    return 1.0


def _ratio_penalty(
    metric: float | None, baseline: float | None
) -> tuple[float | None, float | None, bool]:
    """Ratio, penalty and the zero-baseline inconsistency marker."""
    if metric is None or baseline is None:
        return None, None, False
    if baseline == 0.0:
        if metric == 0.0:
            return None, 0.0, False
        return None, None, True
    ratio = metric / baseline
    return ratio, _penalty(ratio), False


def _metrics_inconsistent(metrics: MetricTriple, baseline: Baseline) -> bool:
    for name in _MEASURES:
        metric = getattr(metrics, name)
        reference = getattr(baseline, name)
        if metric is not None and reference is not None and reference == 0 and metric > 0:
            return True
    return False


def _baseline_incomplete(baseline: Baseline) -> bool:
    return any(getattr(baseline, name) is None for name in _MEASURES)


def _unavailable_category(category: str, reason: str, city_houses: int | None) -> CategoryRating:
    return CategoryRating(
        type=category,
        state="unavailable",
        reason=reason,
        estimated=False,
        metrics=_empty_metrics(),
        baseline=_empty_baseline(city_houses),
        ratios=_empty_metrics(),
        penalties=_empty_metrics(),
        score=None,
    )


def _not_applicable_category(category: str, city_houses: int | None) -> CategoryRating:
    return CategoryRating(
        type=category,
        state="not_applicable",
        reason="NOT_APPLICABLE",
        estimated=False,
        metrics=_empty_metrics(),
        baseline=_empty_baseline(city_houses),
        ratios=_empty_metrics(),
        penalties=_empty_metrics(),
        score=None,
    )


def _category_rating(house: Any, category: str, context: _CategoryContext) -> CategoryRating:
    service = getattr(house.services, category)
    if service == "unknown":
        return _unavailable_category(category, "UNKNOWN_SERVICE", context.city_houses)
    if service != "central":
        return _not_applicable_category(category, context.city_houses)
    if category == "heating" and context.season_unknown:
        return _unavailable_category(category, "HEATING_SEASON_UNKNOWN", context.city_houses)
    if context.window is None:
        return _not_applicable_category(category, context.city_houses)

    links: list[tuple[_View, str]] = []
    for view in context.views:
        for link in view.event.houses:
            if link.house_id == house.id:
                links.append((view, link.match))
    if any(match in _AMBIGUOUS_MATCHES for _view, match in links):
        return CategoryRating(
            type=category,
            state="unavailable",
            reason="AMBIGUOUS_MATCH",
            estimated=context.estimated,
            metrics=_empty_metrics(),
            baseline=context.baseline,
            ratios=_empty_metrics(),
            penalties=_empty_metrics(),
            score=None,
        )

    exact = tuple(view for view, match in links if match == "exact")
    unknown_overlap = any(view.overlap_uncertain for view in exact)
    unknown_weight = any(view.weight is None for view in exact)
    unknown_duration = any(view.duration is None for view in exact)

    frequency: float | None
    hours: float | None
    maximum: float | None
    if unknown_overlap or unknown_weight:
        frequency = hours = maximum = None
    else:
        frequency = sum(view.weight for view in exact)
        if unknown_duration:
            hours = maximum = None
        else:
            contributions = [view.weight * view.duration for view in exact]
            hours = sum(contributions)
            maximum = max(contributions) if contributions else 0.0

    metrics = MetricTriple(frequency=frequency, hours=hours, maximum=maximum)
    ratio_frequency, penalty_frequency, inconsistent_frequency = _ratio_penalty(
        frequency, context.baseline.frequency
    )
    ratio_hours, penalty_hours, inconsistent_hours = _ratio_penalty(hours, context.baseline.hours)
    ratio_maximum, penalty_maximum, inconsistent_maximum = _ratio_penalty(
        maximum, context.baseline.maximum
    )
    inconsistent = inconsistent_frequency or inconsistent_hours or inconsistent_maximum
    if penalty_frequency is None or penalty_hours is None or penalty_maximum is None:
        score: float | None = None
    else:
        score = 1.0 - (0.4 * penalty_frequency + 0.4 * penalty_hours + 0.2 * penalty_maximum)

    if score is None:
        if unknown_overlap:
            reason: str | None = "UNKNOWN_OVERLAP"
        elif unknown_weight:
            reason = "UNKNOWN_KIND"
        elif unknown_duration:
            reason = "UNKNOWN_DURATION"
        elif inconsistent:
            reason = "BASELINE_INCONSISTENT"
        elif context.city_houses is None:
            reason = "BASELINE_UNAVAILABLE"
        elif context.flags.unknown_n:
            reason = "UNKNOWN_AFFECTED_COUNT"
        elif context.flags.unknown_overlap:
            reason = "UNKNOWN_OVERLAP"
        elif context.flags.unknown_weight:
            reason = "UNKNOWN_KIND"
        elif context.flags.unknown_duration:
            reason = "UNKNOWN_DURATION"
        else:
            reason = "BASELINE_UNAVAILABLE"
        state: Literal["approximate", "unavailable"] = "unavailable"
    else:
        reason = None
        state = "approximate"

    return CategoryRating(
        type=category,
        state=state,
        reason=reason,
        estimated=context.estimated,
        metrics=metrics,
        baseline=context.baseline,
        ratios=MetricTriple(frequency=ratio_frequency, hours=ratio_hours, maximum=ratio_maximum),
        penalties=MetricTriple(
            frequency=penalty_frequency, hours=penalty_hours, maximum=penalty_maximum
        ),
        score=score,
    )


def _house_rating(house: Any, contexts: dict[str, _CategoryContext]) -> HouseRating:
    ratings = tuple(
        _category_rating(house, category, contexts[category]) for category in CATEGORY_ORDER
    )
    by_category = {rating.type: rating for rating in ratings}
    applicable: list[str] = []
    unknown_eligibility = False
    for category in CATEGORY_ORDER:
        service = getattr(house.services, category)
        if service == "unknown":
            unknown_eligibility = True
            continue
        if service != "central":
            continue
        context = contexts[category]
        if category == "heating":
            if context.season_unknown:
                unknown_eligibility = True
                continue
            if context.window is None:
                continue
        applicable.append(category)

    total_weight = sum(CATEGORY_WEIGHTS[category] for category in applicable)
    if total_weight:
        effective_weights = tuple(
            EffectiveWeight(type=category, weight=CATEGORY_WEIGHTS[category] / total_weight)
            for category in applicable
        )
    else:
        effective_weights = ()
    scores = {category: by_category[category].score for category in applicable}

    overall: float | None
    limiting: tuple[str, ...]
    state: Literal["approximate", "unavailable", "not_applicable"]
    if unknown_eligibility:
        state = "unavailable"
        overall = None
        limiting = ()
    elif not applicable:
        state = "not_applicable"
        overall = None
        limiting = ()
    elif any(scores[category] is None for category in applicable):
        state = "unavailable"
        overall = None
        limiting = ()
    else:
        weighted = (
            sum(CATEGORY_WEIGHTS[category] * scores[category] for category in applicable)
            / total_weight
        )
        minimum = min(scores[category] for category in applicable)
        overall = min(weighted, minimum + 0.25)
        state = "approximate"
        limiting = tuple(category for category in applicable if scores[category] == minimum)

    return HouseRating(
        house_id=house.id,
        categories=ratings,
        state=state,
        overall=overall,
        effective_weights=effective_weights,
        limiting_categories=limiting,
    )


def _window_last_date(end_exclusive: datetime) -> date:
    """Last calendar date touched by [start, end_exclusive)."""
    if (
        end_exclusive.hour == 0
        and end_exclusive.minute == 0
        and end_exclusive.second == 0
        and end_exclusive.microsecond == 0
    ):
        return end_exclusive.date() - timedelta(days=1)
    return end_exclusive.date()


def _affected_targets(event: Any, target_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        target for target in target_ids if any(link.house_id == target for link in event.houses)
    )


def _ambiguous_targets(event: Any, target_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        target
        for target in target_ids
        if any(
            link.house_id == target and link.match in _AMBIGUOUS_MATCHES for link in event.houses
        )
    )


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    merged: list[tuple[date, date]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + timedelta(days=1):
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def _source_spans(
    dataset: Dataset, window_start: datetime, end_exclusive: datetime
) -> tuple[SourceSpan, ...]:
    first_date = window_start.date()
    last_date = _window_last_date(end_exclusive)
    spans: list[SourceSpan] = []
    for category in CATEGORY_ORDER:
        unknown_ids: list[str] = []
        intervals: list[tuple[date, date]] = []
        for source in dataset.meta.sources:
            if category not in source.types:
                continue
            if source.covered_from is None or source.covered_to is None:
                unknown_ids.append(source.id)
                continue
            start = max(source.covered_from, first_date)
            end = min(source.covered_to, last_date)
            if start <= end:
                intervals.append((start, end))
        merged = _merge_intervals(intervals)
        gaps: list[tuple[date, date]] = []
        if not merged:
            gaps.append((first_date, last_date))
        else:
            if merged[0][0] > first_date:
                gaps.append((first_date, merged[0][0] - timedelta(days=1)))
            for previous, following in zip(merged, merged[1:]):
                if following[0] > previous[1] + timedelta(days=1):
                    gaps.append((previous[1] + timedelta(days=1), following[0] - timedelta(days=1)))
            if merged[-1][1] < last_date:
                gaps.append((merged[-1][1] + timedelta(days=1), last_date))
        spans.append(
            SourceSpan(
                type=category,
                intervals=tuple(SourceInterval(start=start, end=end) for start, end in merged),
                gaps=tuple(SourceInterval(start=start, end=end) for start, end in gaps),
                unknown_source_ids=tuple(unknown_ids),
            )
        )
    return tuple(spans)


def _category_evaluated(service: str, context: _CategoryContext) -> bool:
    if service != "central":
        return False
    if context.category == "heating":
        return not context.season_unknown and context.window is not None
    return True


def _rating_for(category: str, rating: HouseRating) -> CategoryRating:
    for item in rating.categories:
        if item.type == category:
            return item
    raise AssertionError("category rating is missing")


def _diagnostics(
    dataset: Dataset,
    request: ValidRequest,
    contexts: dict[str, _CategoryContext],
    ratings: tuple[HouseRating, ...],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    target_ids = request.target_house_ids
    house_by_id = {house.id: house for house in dataset.houses}
    index_by_id = {house.id: index for index, house in enumerate(dataset.houses)}
    rating_by_id = {rating.house_id: rating for rating in ratings}

    window_start = request.end_exclusive - WINDOW_SIZE
    if (
        window_start.date() < dataset.meta.period.date_from
        or _window_last_date(request.end_exclusive) > dataset.meta.period.date_to
    ):
        diagnostics.append(
            Diagnostic(
                code="WINDOW_OUTSIDE_DATASET",
                path=("meta", "period"),
                event_ids=(),
                house_ids=(),
            )
        )
    diagnostics.append(
        Diagnostic(code="SOURCE_COVERAGE_UNPROVEN", path=(), event_ids=(), house_ids=())
    )
    if dataset.meta.heating_season_start is None and any(
        house_by_id[target].services.heating == "central" for target in target_ids
    ):
        diagnostics.append(
            Diagnostic(
                code="HEATING_SEASON_UNKNOWN",
                path=("meta", "heating_season_start"),
                event_ids=(),
                house_ids=(),
            )
        )

    for category in CATEGORY_ORDER:
        if contexts[category].window is not None:
            diagnostics.append(
                Diagnostic(
                    code="PROXY_BASELINE_USED",
                    path=(),
                    event_ids=(),
                    house_ids=(),
                )
            )

    for category in CATEGORY_ORDER:
        context = contexts[category]
        if context.window is None:
            continue
        for view in context.views:
            event = view.event
            path = ("events", view.index)
            event_ids = (event.id,)
            if view.weight is None:
                diagnostics.append(
                    Diagnostic(
                        code="UNKNOWN_KIND",
                        path=path,
                        event_ids=event_ids,
                        house_ids=_affected_targets(event, target_ids),
                    )
                )
            if view.duration is None:
                code = "UNKNOWN_OVERLAP" if view.overlap_uncertain else "UNKNOWN_DURATION"
                diagnostics.append(
                    Diagnostic(
                        code=code,
                        path=path,
                        event_ids=event_ids,
                        house_ids=_affected_targets(event, target_ids),
                    )
                )
            if event.houses_affected is None:
                diagnostics.append(
                    Diagnostic(
                        code="UNKNOWN_AFFECTED_COUNT",
                        path=path,
                        event_ids=event_ids,
                        house_ids=_affected_targets(event, target_ids),
                    )
                )
            if any(link.match in _AMBIGUOUS_MATCHES for link in event.houses):
                diagnostics.append(
                    Diagnostic(
                        code="AMBIGUOUS_MATCH",
                        path=path,
                        event_ids=event_ids,
                        house_ids=_ambiguous_targets(event, target_ids),
                    )
                )

    for category in CATEGORY_ORDER:
        context = contexts[category]
        if context.window is None or not _baseline_incomplete(context.baseline):
            continue
        path = ("meta", "city_houses", "total") if context.city_houses is None else ()
        diagnostics.append(
            Diagnostic(
                code="BASELINE_UNAVAILABLE",
                path=path,
                event_ids=context.flags.culprits,
                house_ids=(),
            )
        )

    for category in CATEGORY_ORDER:
        context = contexts[category]
        if context.window is None:
            continue
        flagged = tuple(
            target
            for target in target_ids
            if _metrics_inconsistent(
                _rating_for(category, rating_by_id[target]).metrics, context.baseline
            )
        )
        if flagged:
            diagnostics.append(
                Diagnostic(
                    code="BASELINE_INCONSISTENT",
                    path=(),
                    event_ids=(),
                    house_ids=flagged,
                )
            )

    for target in target_ids:
        rating = rating_by_id[target]
        source_house = house_by_id[target]
        dataset_index = index_by_id[target]
        for category in CATEGORY_ORDER:
            context = contexts[category]
            service = getattr(source_house.services, category)
            path = ("houses", dataset_index)
            house_ids = (target,)
            if service == "unknown":
                diagnostics.append(
                    Diagnostic(
                        code="SERVICE_UNKNOWN",
                        path=path,
                        event_ids=(),
                        house_ids=house_ids,
                    )
                )
            if not _category_evaluated(service, context):
                continue
            if context.estimated:
                planned_ids = tuple(
                    view.event.id
                    for view in context.views
                    if view.event.duration_basis == "planned" and view.duration is not None
                )
                diagnostics.append(
                    Diagnostic(
                        code="PLANNED_DURATION_USED",
                        path=path,
                        event_ids=planned_ids,
                        house_ids=house_ids,
                    )
                )
            if not context.views:
                diagnostics.append(
                    Diagnostic(
                        code="NO_OBSERVED_EVENTS",
                        path=path,
                        event_ids=(),
                        house_ids=house_ids,
                    )
                )
            if _baseline_incomplete(context.baseline):
                diagnostics.append(
                    Diagnostic(
                        code="BASELINE_UNAVAILABLE",
                        path=path,
                        event_ids=(),
                        house_ids=house_ids,
                    )
                )
            if _metrics_inconsistent(_rating_for(category, rating).metrics, context.baseline):
                diagnostics.append(
                    Diagnostic(
                        code="BASELINE_INCONSISTENT",
                        path=path,
                        event_ids=(),
                        house_ids=house_ids,
                    )
                )

    return _deduplicate(diagnostics)


def _deduplicate(diagnostics: list[Diagnostic]) -> tuple[Diagnostic, ...]:
    seen: set[tuple[str, tuple[str | int, ...], tuple[str, ...], tuple[str, ...]]] = set()
    result: list[Diagnostic] = []
    for diagnostic in diagnostics:
        key = (
            diagnostic.code,
            diagnostic.path,
            diagnostic.event_ids,
            diagnostic.house_ids,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(diagnostic)
    return tuple(result)


def build_report(dataset: Dataset, request: ValidRequest) -> CalculationReport:
    """Compute the immutable report for one validated dataset and request."""
    window_start = request.end_exclusive - WINDOW_SIZE
    window = (window_start, request.end_exclusive)
    city_houses = dataset.meta.city_houses.total
    contexts = {
        category: _build_context(dataset, category, window, city_houses)
        for category in CATEGORY_ORDER
    }
    house_by_id = {house.id: house for house in dataset.houses}
    ratings = tuple(
        _house_rating(house_by_id[target], contexts) for target in request.target_house_ids
    )
    diagnostics = _diagnostics(dataset, request, contexts, ratings)
    return CalculationReport(
        policy_version=request.policy_version,
        window=Window(start=window_start, end_exclusive=request.end_exclusive),
        houses=ratings,
        source_spans=_source_spans(dataset, window_start, request.end_exclusive),
        limitations=tuple(dataset.meta.limitations),
        diagnostics=diagnostics,
    )
