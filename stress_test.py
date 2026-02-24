"""
PROPIO — Stress Test Module v1.0
=================================
Escala graduada de C/I por score + stress test con haircut.

Lógica:
  1. Escala graduada: C/I max por tramo de score Sinacofi (flag, no eliminatorio)
  2. Stress test: haircut al ingreso (dep -10%, indep -15%), recalcular C/I
  3. Hard gate: C/I estresado > 45% → RECHAZA (eliminatorio)
  4. Egreso y Leverage por tramo (flag para comité)

Respaldo:
  - 40% techo máximo anclado a viabilidad de exit hipotecario (25+ años, GG Fin < 40%)
  - 45% post-estrés alineado con DSTI europeo (IMF/Columbia SIPA: 8/15 países usan 40-45%)
  - Escala graduada: score bajo → techo más bajo (proporcional al riesgo crediticio)
"""

from datetime import datetime

# ============================================================
# ESCALA GRADUADA POR SCORE SINACOFI
# ============================================================
# (score_min, score_max, pd_ref, cuota_max, egreso_max, leverage_max)
ESCALA = [
    (1,   124,  0.8316, 0.20, 0.55, 60),
    (125, 357,  0.2546, 0.20, 0.55, 60),
    (358, 487,  0.1001, 0.20, 0.55, 60),
    (488, 534,  0.0600, 0.30, 0.55, 60),
    (535, 620,  0.0600, 0.30, 0.55, 60),
    (621, 716,  0.0507, 0.35, 0.592, 65),
    (717, 797,  0.0447, 0.38, 0.62, 65),
    (798, 999,  0.0281, 0.40, 0.65, 65),
]

# ============================================================
# HAIRCUTS POR TIPO DE CONTRATO
# ============================================================
HAIRCUT = {
    1: 0.10,   # Dependiente: -10%
    0: 0.15,   # Independiente: -15%
}

# Hard gate post-estrés
STRESS_CI_MAX = 0.45


def get_tramo(score):
    """Retorna el tramo de la escala para un score dado."""
    for s_min, s_max, pd_ref, ci_max, egreso_max, lev_max in ESCALA:
        if s_min <= score <= s_max:
            return {
                "score_min": s_min,
                "score_max": s_max,
                "pd_ref": pd_ref,
                "cuota_max": ci_max,
                "egreso_max": egreso_max,
                "leverage_max": lev_max,
            }
    # Score fuera de rango → tramo más restrictivo
    return {
        "score_min": 1,
        "score_max": 124,
        "pd_ref": 0.8316,
        "cuota_max": 0.20,
        "egreso_max": 0.55,
        "leverage_max": 60,
    }


def aplicar_haircut(ingreso, tipo):
    """Aplica haircut al ingreso según tipo de contrato.

    Args:
        ingreso: ingreso mensual (CLP o UF)
        tipo: 1=dependiente, 0=independiente

    Returns:
        ingreso estresado
    """
    h = HAIRCUT.get(tipo, 0.15)  # default independiente si tipo desconocido
    return ingreso * (1 - h)


def evaluar_ci_tramo(ratio_ci, score):
    """Evalúa C/I contra el techo del tramo.

    Returns:
        dict con pass/fail y detalle (flag para comité, NO eliminatorio)
    """
    tramo = get_tramo(score)
    ci_max = tramo["cuota_max"]
    pasa = ratio_ci <= ci_max

    return {
        "ratio_ci": round(ratio_ci, 4),
        "ci_max_tramo": ci_max,
        "tramo": f"{tramo['score_min']}-{tramo['score_max']}",
        "pasa": pasa,
        "tipo": "flag_comite",  # NO eliminatorio
        "detalle": (
            f"C/I {ratio_ci:.1%} {'≤' if pasa else '>'} {ci_max:.0%} "
            f"(tramo {tramo['score_min']}-{tramo['score_max']})"
        ),
    }


def evaluar_egreso_tramo(ratio_egreso, score):
    """Evalúa Egreso/Ingreso contra el techo del tramo.

    Returns:
        dict con pass/fail y detalle (flag para comité)
    """
    tramo = get_tramo(score)
    egreso_max = tramo["egreso_max"]
    pasa = ratio_egreso <= egreso_max

    return {
        "ratio_egreso": round(ratio_egreso, 4),
        "egreso_max_tramo": egreso_max,
        "tramo": f"{tramo['score_min']}-{tramo['score_max']}",
        "pasa": pasa,
        "tipo": "flag_comite",
        "detalle": (
            f"Egreso {ratio_egreso:.1%} {'≤' if pasa else '>'} {egreso_max:.0%} "
            f"(tramo {tramo['score_min']}-{tramo['score_max']})"
        ),
    }


def run_stress_test(cuota, ingreso, score, tipo, egreso_total=None):
    """Ejecuta stress test completo.

    Args:
        cuota: cuota mensual PROPIO (CLP o UF, misma unidad que ingreso)
        ingreso: ingreso mensual bruto
        score: score Sinacofi
        tipo: 1=dependiente, 0=independiente
        egreso_total: gastos financieros totales (opcional, para ratio egreso)

    Returns:
        dict con resultados completos
    """
    tramo = get_tramo(score)
    haircut_pct = HAIRCUT.get(tipo, 0.15)

    # --- Pre-estrés ---
    ratio_ci = cuota / ingreso if ingreso > 0 else 1.0
    ci_tramo = evaluar_ci_tramo(ratio_ci, score)

    egreso_tramo = None
    if egreso_total is not None:
        ratio_egreso = egreso_total / ingreso if ingreso > 0 else 1.0
        egreso_tramo = evaluar_egreso_tramo(ratio_egreso, score)

    # --- Post-estrés (haircut) ---
    ingreso_estresado = aplicar_haircut(ingreso, tipo)
    ratio_ci_estresado = cuota / ingreso_estresado if ingreso_estresado > 0 else 1.0

    # Hard gate: C/I estresado > 45% → RECHAZA
    stress_pasa = ratio_ci_estresado <= STRESS_CI_MAX

    egreso_estresado = None
    if egreso_total is not None:
        ratio_egreso_estresado = egreso_total / ingreso_estresado if ingreso_estresado > 0 else 1.0
        egreso_estresado = {
            "ratio": round(ratio_egreso_estresado, 4),
            "max": tramo["egreso_max"],
            "pasa": ratio_egreso_estresado <= tramo["egreso_max"],
        }

    # --- Resultado consolidado ---
    resultado = {
        "pre_estres": {
            "ingreso": round(ingreso, 2),
            "cuota": round(cuota, 2),
            "ratio_ci": round(ratio_ci, 4),
            "ci_tramo": ci_tramo,
            "egreso_tramo": egreso_tramo,
        },
        "stress": {
            "haircut_pct": haircut_pct,
            "tipo_label": "Dependiente" if tipo == 1 else "Independiente",
            "ingreso_estresado": round(ingreso_estresado, 2),
            "ratio_ci_estresado": round(ratio_ci_estresado, 4),
            "techo_stress": STRESS_CI_MAX,
            "pasa_hard_gate": stress_pasa,
            "egreso_estresado": egreso_estresado,
        },
        "tramo": {
            "score": score,
            "rango": f"{tramo['score_min']}-{tramo['score_max']}",
            "cuota_max": tramo["cuota_max"],
            "egreso_max": tramo["egreso_max"],
            "leverage_max": tramo["leverage_max"],
        },
        "decision": {
            "hard_gate_stress": stress_pasa,
            "ci_en_tramo": ci_tramo["pasa"],
            "resumen": _generar_resumen(ci_tramo, stress_pasa, ratio_ci_estresado),
        },
        "metadata": {
            "module": "stress_test_v1.0",
            "timestamp": datetime.now().isoformat(),
        },
    }

    return resultado


def _generar_resumen(ci_tramo, stress_pasa, ratio_ci_estresado):
    """Genera resumen textual de la evaluación."""
    if not stress_pasa:
        return (
            f"RECHAZADO — C/I estresado {ratio_ci_estresado:.1%} > 45% hard gate. "
            f"No admisible."
        )
    if not ci_tramo["pasa"]:
        return (
            f"OBSERVACIÓN — {ci_tramo['detalle']}. "
            f"Stress test OK ({ratio_ci_estresado:.1%} < 45%). "
            f"Decisión de comité."
        )
    return (
        f"APROBADO — C/I dentro de tramo ({ci_tramo['detalle']}). "
        f"Stress test OK ({ratio_ci_estresado:.1%} < 45%)."
    )


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    # Caso Montecinos
    print("=" * 60)
    print("STRESS TEST — Andrés Montecinos")
    print("=" * 60)
    r = run_stress_test(
        cuota=1_155_384,
        ingreso=3_410_985,
        score=534,
        tipo=1,  # dependiente
    )
    print(f"\nPre-estrés:")
    print(f"  Ingreso: ${r['pre_estres']['ingreso']:,.0f}")
    print(f"  Cuota:   ${r['pre_estres']['cuota']:,.0f}")
    print(f"  C/I:     {r['pre_estres']['ratio_ci']:.1%}")
    print(f"  Tramo:   {r['tramo']['rango']} → Max {r['tramo']['cuota_max']:.0%}")
    print(f"  En tramo: {'✓' if r['decision']['ci_en_tramo'] else '✗ FLAG COMITÉ'}")

    print(f"\nStress test:")
    print(f"  Haircut: {r['stress']['haircut_pct']:.0%} ({r['stress']['tipo_label']})")
    print(f"  Ingreso estresado: ${r['stress']['ingreso_estresado']:,.0f}")
    print(f"  C/I estresado:     {r['stress']['ratio_ci_estresado']:.1%}")
    print(f"  Hard gate (≤45%):  {'✓ PASA' if r['stress']['pasa_hard_gate'] else '✗ RECHAZADO'}")

    print(f"\n→ {r['decision']['resumen']}")

    # Caso Pablo Pérez (problemático)
    print("\n" + "=" * 60)
    print("STRESS TEST — Pablo Pérez (problemático)")
    print("=" * 60)
    # Pablo: independiente, ingreso variable, cuota ~246k estimada
    # Ingreso promedio ~1M, cuota/ingreso ~24.6%, pero CR_ácido 0.56
    r2 = run_stress_test(
        cuota=246_000,
        ingreso=1_000_000,
        score=100,  # PD 83% → tramo más bajo
        tipo=0,  # independiente
    )
    print(f"\nPre-estrés:")
    print(f"  C/I:     {r2['pre_estres']['ratio_ci']:.1%}")
    print(f"  Tramo:   {r2['tramo']['rango']} → Max {r2['tramo']['cuota_max']:.0%}")
    print(f"  En tramo: {'✓' if r2['decision']['ci_en_tramo'] else '✗ FLAG COMITÉ'}")

    print(f"\nStress test:")
    print(f"  Haircut: {r2['stress']['haircut_pct']:.0%} ({r2['stress']['tipo_label']})")
    print(f"  C/I estresado: {r2['stress']['ratio_ci_estresado']:.1%}")
    print(f"  Hard gate:     {'✓ PASA' if r2['stress']['pasa_hard_gate'] else '✗ RECHAZADO'}")

    print(f"\n→ {r2['decision']['resumen']}")
