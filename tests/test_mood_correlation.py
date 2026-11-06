"""Testes da correlação descritiva entre humor e contextos."""

from __future__ import annotations

import pytest

from services.mood_correlation import analyze_mood_correlation
from services.mood_metrics import CheckIn


def test_empty_analysis_raises_clear_error():
    with pytest.raises(ValueError, match="Sem dados suficientes"):
        analyze_mood_correlation([])


def test_correlation_compares_context_average_with_overall_average():
    result = analyze_mood_correlation(
        [
            CheckIn(5, 3, 2, ("Família", "Sono")),
            CheckIn(4, 3, 2, ("Família",)),
            CheckIn(2, 3, 4, ("Trabalho", "Corpo")),
            CheckIn(1, 2, 5, ("Trabalho",)),
        ]
    )

    assert result.media_geral_semanal == 3.0
    assert result.total_checkins == 4
    assert result.total_mencoes == 6
    by_name = {item.nome_contexto: item for item in result.analise_contextos}
    assert by_name["Família"].humor_medio_com_contexto == 4.5
    assert by_name["Família"].diferenca_para_media_geral == 1.5
    assert by_name["Trabalho"].humor_medio_com_contexto == 1.5
    assert by_name["Trabalho"].diferenca_para_media_geral == -1.5
    assert by_name["Trabalho"].classificacao_impacto == "Negativo"


def test_negative_and_positive_rankings_ignore_small_samples():
    result = analyze_mood_correlation(
        [
            CheckIn(1, 3, 3, ("Trabalho",)),
            CheckIn(2, 3, 3, ("Trabalho",)),
            CheckIn(5, 3, 3, ("Família",)),
            CheckIn(5, 3, 3, ("Família",)),
            CheckIn(5, 3, 3, ("Sono",)),
        ],
        min_sample=2,
    )

    assert [item.nome_contexto for item in result.principais_gatilhos_negativos] == ["Trabalho"]
    assert [item.nome_contexto for item in result.principais_fontes_bem_estar] == ["Família"]
    assert next(
        item for item in result.analise_contextos if item.nome_contexto == "Sono"
    ).amostra_suficiente is False


def test_full_context_list_is_sorted_by_lowest_average_mood():
    result = analyze_mood_correlation(
        [
            CheckIn(2, 3, 3, ("Trabalho",)),
            CheckIn(4, 3, 3, ("Sono",)),
            CheckIn(5, 3, 3, ("Família",)),
        ],
        min_sample=1,
    )

    assert [item.nome_contexto for item in result.analise_contextos] == [
        "Trabalho",
        "Sono",
        "Família",
    ]


def test_duplicate_context_in_same_checkin_counts_only_once():
    result = analyze_mood_correlation(
        [CheckIn(4, 3, 3, ("Sono", "Sono", " ")), CheckIn(2, 3, 3, ("Corpo",))],
        min_sample=1,
    )

    by_name = {item.nome_contexto: item for item in result.analise_contextos}
    assert by_name["Sono"].frequencia == 1
    assert result.total_mencoes == 2


def test_json_contract_uses_expected_field_names():
    payload = analyze_mood_correlation(
        [CheckIn(4, 3, 3, ("Sono",))], min_sample=1
    ).to_dict()

    assert payload["mediaGeralSemanal"] == 4.0
    assert payload["totalCheckIns"] == 1
    assert payload["totalMencoes"] == 1
    assert payload["analiseContextos"][0] == {
        "nomeContexto": "Sono",
        "frequencia": 1,
        "humorMedioComContexto": 4.0,
        "diferencaParaMediaGeral": 0.0,
        "classificacaoImpacto": "Neutro",
        "amostraSuficiente": True,
    }
    assert "não implica causalidade" in payload["aviso"]
