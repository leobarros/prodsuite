# Algoritmo de Cálculo de Hidratação Líquida e Compensação Alcoólica

## 1. Meta Base Diária
A meta base de hidratação é calculada com base no peso corporal (recomendação padrão de 35 mL/kg):

$$\text{Meta Base (mL)} = \text{Peso (kg)} \times 35$$

---

## 2. Coeficientes de Eficiência por Bebida
Nem todos os líquidos hidratam igualmente. Alguns possuem efeito diurético leve ou negativo.

| Categoria | Bebida | Coeficiente | Descrição / Efeito |
| :--- | :--- | :---: | :--- |
| **Hidratação Total** | Água pura, Água com gás | `+1.0` | 100% do volume conta como água ingerida. |
| **Infusões Leves** | Chás claros, Água de coco | `+0.9` | 90% do volume conta como hidratação. |
| **Café Coado** | Café filtrado, Café com leite | `+0.8` | Presença moderada de cafeína. |
| **Café Concentrado**| Espresso, Ristretto | `+0.6` | Maior concentração de cafeína por mL. |
| **Cerveja** | Cervejas comerciais (4%–5% ABV) | `-0.5` | Suprime o ADH. Saldo líquido negativo de -50%. |
| **Destilados / Vinho**| Vinho, Uísque, Vodka, Gin | `-1.2` | Diurético acentuado. Saldo líquido negativo de -120%. |

---

## 3. Lógica de Compensação Alcoólica
Bebidas alcoólicas inibem a vasopressina (hormônio antidiurético / ADH). Para manter o equilíbrio osmótico:

* **Para Cerveja:** Para cada $100\text{ mL}$ consumidos, o corpo perde aproximadamente $150\text{ mL}$ de líquido. É necessária uma compensação de **1,5x o volume de cerveja** em água pura.
* **Para Destilados / Vinho:** É necessária uma compensação de **2,2x o volume** em água pura.

---

## 4. Código do Algoritmo em Python

```python
def calcular_saldo_hidratacao(peso_kg: float, consumos: list) -> dict:
    """
    Calcula a hidratação líquida diária considerando o consumo de água, 
    cafeína e penalizações por consumo de álcool.
    
    :param peso_kg: Peso da pessoa em quilogramas
    :param consumos: Lista de dicionários no formato [{"tipo": str, "volume_ml": float}]
    :return: Dicionário com métricas de hidratação e água extra necessária
    """
    # Meta base
    meta_diaria = peso_kg * 35.0
    
    # Coeficientes de hidratação
    coeficientes = {
        "agua": 1.0,
        "cha": 0.9,
        "cafe_coado": 0.8,
        "cafe_espresso": 0.6,
        "cerveja": -0.5,
        "destilado": -1.2,
        "vinho": -1.0
    }
    
    hidratacao_liquida = 0.0
    agua_extra_compensatoria = 0.0

    for item in consumos:
        bebida = item["tipo"].lower()
        volume = item["volume_ml"]
        
        fator = coeficientes.get(bebida, 1.0)
        ganho_liquido = volume * fator
        
        hidratacao_liquida += ganho_liquido
        
        # Cálculo do débito hídrico causado pelo álcool
        if fator < 0:
            # Volume consumido + Volume perdido por diurese induzida
            agua_extra_compensatoria += volume * (1.0 + abs(fator))

    progresso_pct = (hidratacao_liquida / meta_diaria) * 100.0

    return {
        "meta_diaria_ml": meta_diaria,
        "hidratacao_liquida_ml": round(hidratacao_liquida, 1),
        "progresso_pct": round(max(0.0, progresso_pct), 1),
        "agua_extra_para_compensar_ml": round(agua_extra_compensatoria, 1)
    }

# Exemplo de uso:
if __name__ == "__main__":
    usuario_peso = 70.0  # kg
    registros_do_dia = [
        {"tipo": "agua", "volume_ml": 1000},
        {"tipo": "cafe_coado", "volume_ml": 200},
        {"tipo": "cerveja", "volume_ml": 700}
    ]
    
    resultado = calcular_saldo_hidratacao(usuario_peso, registros_do_dia)
    print(resultado)