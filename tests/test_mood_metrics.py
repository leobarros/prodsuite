"""Testes unitários da agregação de humor e contextos."""

from __future__ import annotations

import pytest

from services.mood_metrics import CheckIn, aggregate_mood_contexts


def test_empty_checkins_returns_zeroed_summary():
    summary = aggregate_mood_contexts([])

    assert summary.media_humor == 0.0
    assert summary.total_checkins == 0
    assert summary.checkins_com_contexto == 0
    assert summary.total_mencoes == 0
    assert summary.contextos_ordenados == ()


def test_media_and_context_percent_use_mentions_as_denominator():
    summary = aggregate_mood_contexts(
        [
            CheckIn(4, 3, 2, ("Sono", "Trabalho")),
            CheckIn(5, 4, 1, ("Sono",)),
            CheckIn(3, 2, 4, ()),
        ]
    )

    assert summary.media_humor == 4.0
    assert summary.total_checkins == 3
    assert summary.checkins_com_contexto == 2
    assert summary.total_mencoes == 3
    assert [(item.contexto, item.frequencia, item.percentual) for item in summary.contextos_ordenados] == [
        ("Sono", 2, 66.67),
        ("Trabalho", 1, 33.33),
    ]
    payload = summary.to_dict()
    assert payload["mediaHumor"] == 4.0
    assert payload["totalCheckIns"] == 3
    assert payload["checkInsComContexto"] == 2
    assert payload["totalMencoes"] == 3
    assert payload["contextosOrdenados"][0] == {
        "contexto": "Sono",
        "frequencia": 2,
        "percentual": 66.67,
    }


def test_contexts_are_sorted_by_frequency_descending_with_stable_tiebreak():
    summary = aggregate_mood_contexts(
        [
            CheckIn(3, 3, 3, ("Trabalho", "Sono")),
            CheckIn(3, 3, 3, ("Sono", "Corpo")),
            CheckIn(3, 3, 3, ("Sono",)),
        ]
    )

    assert [item.contexto for item in summary.contextos_ordenados] == [
        "Sono",
        "Corpo",
        "Trabalho",
    ]
    assert [item.frequencia for item in summary.contextos_ordenados] == [3, 1, 1]


def test_duplicate_context_in_same_checkin_counts_once():
    summary = aggregate_mood_contexts(
        [
            CheckIn(4, 3, 2, ("Sono", "Sono", "  ")),
            CheckIn(2, 3, 4, ("Trabalho",)),
        ]
    )

    assert summary.total_checkins == 2
    assert summary.checkins_com_contexto == 2
    assert summary.total_mencoes == 2
    assert summary.contextos_ordenados[0].contexto == "Sono"
    assert summary.contextos_ordenados[0].percentual == 50.0


def test_invalid_humor_raises_value_error():
    with pytest.raises(ValueError, match="Humor"):
        aggregate_mood_contexts([CheckIn(6, 3, 2, ("Sono",))])
