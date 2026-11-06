"""Agregação pura de humor e contextos de check-ins."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class CheckIn:
    humor: int
    energia: int
    tensao: int
    contextos: Sequence[str]


@dataclass(frozen=True, slots=True)
class ContextoResumo:
    contexto: str
    frequencia: int
    percentual: float


@dataclass(frozen=True, slots=True)
class ResumoSemanal:
    media_humor: float
    total_checkins: int
    checkins_com_contexto: int
    total_mencoes: int
    contextos_ordenados: tuple[ContextoResumo, ...]

    def to_dict(self) -> dict:
        """Serializa no contrato público da especificação."""
        return {
            "mediaHumor": self.media_humor,
            "totalCheckIns": self.total_checkins,
            "checkInsComContexto": self.checkins_com_contexto,
            "totalMencoes": self.total_mencoes,
            "contextosOrdenados": [
                {
                    "contexto": item.contexto,
                    "frequencia": item.frequencia,
                    "percentual": item.percentual,
                }
                for item in self.contextos_ordenados
            ],
        }


def aggregate_mood_contexts(checkins: Iterable[CheckIn]) -> ResumoSemanal:
    """Agrega check-ins sem contar contextos duplicados no mesmo check-in.

    O percentual de cada contexto usa o total de menções como denominador,
    nunca o total de check-ins.
    """
    total_checkins = 0
    checkins_com_contexto = 0
    humor_sum = 0
    context_counts: Counter[str] = Counter()

    for checkin in checkins:
        humor = int(checkin.humor)
        if not 1 <= humor <= 5:
            raise ValueError("Humor deve estar entre 1 e 5.")
        total_checkins += 1
        humor_sum += humor

        contextos = {
            str(contexto).strip()
            for contexto in checkin.contextos
            if contexto is not None and str(contexto).strip()
        }
        if contextos:
            checkins_com_contexto += 1
            context_counts.update(contextos)

    total_mencoes = sum(context_counts.values())
    contextos_ordenados = tuple(
        ContextoResumo(
            contexto=contexto,
            frequencia=frequencia,
            percentual=round(frequencia / total_mencoes * 100, 2),
        )
        for contexto, frequencia in sorted(
            context_counts.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    )
    media_humor = (
        round(humor_sum / total_checkins, 2) if total_checkins else 0.0
    )

    return ResumoSemanal(
        media_humor=media_humor,
        total_checkins=total_checkins,
        checkins_com_contexto=checkins_com_contexto,
        total_mencoes=total_mencoes,
        contextos_ordenados=contextos_ordenados,
    )
