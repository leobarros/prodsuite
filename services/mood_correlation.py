"""Correlação descritiva entre contextos e humor.

O resultado é uma associação observada no período. Não é uma estimativa causal:
contextos podem coexistir e uma amostra pequena produz médias instáveis.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from services.mood_metrics import CheckIn

DEFAULT_IMPACT_THRESHOLD = 0.3
DEFAULT_MIN_SAMPLE = 2


@dataclass(frozen=True, slots=True)
class ContextStats:
    nome_contexto: str
    frequencia: int
    humor_medio_com_contexto: float
    diferenca_para_media_geral: float
    classificacao_impacto: str
    amostra_suficiente: bool


@dataclass(frozen=True, slots=True)
class CorrelationResult:
    media_geral_semanal: float
    total_checkins: int
    total_mencoes: int
    analise_contextos: tuple[ContextStats, ...]
    principais_gatilhos_negativos: tuple[ContextStats, ...]
    principais_fontes_bem_estar: tuple[ContextStats, ...]
    min_amostra: int
    limiar_impacto: float

    def to_dict(self) -> dict:
        def context_dict(item: ContextStats) -> dict:
            return {
                "nomeContexto": item.nome_contexto,
                "frequencia": item.frequencia,
                "humorMedioComContexto": item.humor_medio_com_contexto,
                "diferencaParaMediaGeral": item.diferenca_para_media_geral,
                "classificacaoImpacto": item.classificacao_impacto,
                "amostraSuficiente": item.amostra_suficiente,
            }

        return {
            "mediaGeralSemanal": self.media_geral_semanal,
            "totalCheckIns": self.total_checkins,
            "totalMencoes": self.total_mencoes,
            "analiseContextos": [
                context_dict(item) for item in self.analise_contextos
            ],
            "principaisGatilhosNegativos": [
                context_dict(item) for item in self.principais_gatilhos_negativos
            ],
            "principaisFontesBemEstar": [
                context_dict(item) for item in self.principais_fontes_bem_estar
            ],
            "minAmostra": self.min_amostra,
            "limiarImpacto": self.limiar_impacto,
            "aviso": (
                "Associação descritiva no período; não implica causalidade "
                "e amostras pequenas devem ser lidas com cautela."
            ),
        }


def analyze_mood_correlation(
    checkins: Iterable[CheckIn],
    *,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    impact_threshold: float = DEFAULT_IMPACT_THRESHOLD,
) -> CorrelationResult:
    """Compara o humor médio por contexto com a média geral do período."""
    if min_sample < 1:
        raise ValueError("min_sample deve ser maior ou igual a 1.")
    if impact_threshold < 0:
        raise ValueError("impact_threshold não pode ser negativo.")

    checkins = list(checkins)
    if not checkins:
        raise ValueError("Sem dados suficientes")

    humor_total = 0
    context_sums: Counter[str] = Counter()
    context_counts: Counter[str] = Counter()

    for checkin in checkins:
        humor = int(checkin.humor)
        if not 1 <= humor <= 5:
            raise ValueError("Humor deve estar entre 1 e 5.")
        humor_total += humor

        contextos = {
            str(contexto).strip()
            for contexto in checkin.contextos
            if contexto is not None and str(contexto).strip()
        }
        for contexto in contextos:
            context_sums[contexto] += humor
            context_counts[contexto] += 1

    media_geral = round(humor_total / len(checkins), 2)
    stats: list[ContextStats] = []

    for contexto, frequencia in context_counts.items():
        media_contexto = round(context_sums[contexto] / frequencia, 2)
        diferenca = round(media_contexto - media_geral, 2)
        amostra_suficiente = frequencia >= min_sample

        if not amostra_suficiente:
            classificacao = "Neutro"
        elif diferenca > impact_threshold:
            classificacao = "Positivo"
        elif diferenca < -impact_threshold:
            classificacao = "Negativo"
        else:
            classificacao = "Neutro"

        stats.append(
            ContextStats(
                nome_contexto=contexto,
                frequencia=frequencia,
                humor_medio_com_contexto=media_contexto,
                diferenca_para_media_geral=diferenca,
                classificacao_impacto=classificacao,
                amostra_suficiente=amostra_suficiente,
            )
        )

    # A lista completa começa pelos contextos com menor humor médio.
    stats.sort(
        key=lambda item: (
            item.humor_medio_com_contexto,
            -item.frequencia,
            item.nome_contexto.casefold(),
        )
    )
    gatilhos = tuple(
        item
        for item in sorted(
            (item for item in stats if item.amostra_suficiente and item.classificacao_impacto == "Negativo"),
            key=lambda item: (item.diferenca_para_media_geral, item.nome_contexto.casefold()),
        )
    )
    fontes = tuple(
        item
        for item in sorted(
            (item for item in stats if item.amostra_suficiente and item.classificacao_impacto == "Positivo"),
            key=lambda item: (-item.diferenca_para_media_geral, item.nome_contexto.casefold()),
        )
    )

    return CorrelationResult(
        media_geral_semanal=media_geral,
        total_checkins=len(checkins),
        total_mencoes=sum(context_counts.values()),
        analise_contextos=tuple(stats),
        principais_gatilhos_negativos=gatilhos,
        principais_fontes_bem_estar=fontes,
        min_amostra=min_sample,
        limiar_impacto=impact_threshold,
    )
