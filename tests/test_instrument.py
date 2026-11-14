"""Test-only doubles: never replace or mutate production modules."""

import copy
import json

import pytest
from conftest import synthetic_dataset


def check_population(reader):
    for variant in ("base", "empty", "alternate"):
        data = synthetic_dataset()
        if variant == "empty":
            data["houses"] = []
            data["events"] = []
        elif variant == "alternate":
            data["meta"]["limitations"] = ["Different synthetic note"]
        before = copy.deepcopy(data)
        actual = reader(data)
        assert actual == before, "wrong normalized value"
        assert data == before, "input mutation"


@pytest.mark.parametrize("mutant", ["literal", "pattern", "empty-success", "mutation"])
def test_population_catches_safe_doubles(mutant):
    literal = synthetic_dataset()

    def fake(data):
        if mutant == "literal":
            return literal
        if mutant == "pattern":
            return (
                data if data["meta"]["limitations"] == literal["meta"]["limitations"] else literal
            )
        if mutant == "empty-success":
            return {}
        data["meta"]["limitations"].clear()
        return data

    with pytest.raises(AssertionError, match="wrong normalized value|input mutation"):
        check_population(fake)


def test_population_accepts_independent_serializing_double():
    check_population(lambda data: json.loads(json.dumps(data)))


def test_refusal_probe_catches_removed_validation_double():
    data = synthetic_dataset()
    data["events"][0]["sources"] = []

    class SyntheticRefused(Exception):
        pass

    def require_refusal(reader):
        try:
            reader(data)
        except SyntheticRefused:
            return
        raise AssertionError("illegal empty success; refusal missing")

    with pytest.raises(AssertionError, match="refusal missing"):
        require_refusal(lambda value: value)
