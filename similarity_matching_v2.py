"""
PROPIO — Similarity Matching v2.1
Motor de admisión con Cobertura Ácida + CV bifurcado.

Cambios vs v1:
- Ossian Leiva removido (caso puntual, no estructural)
- CR_ácido es GATE BINARIO (>=1.0), NO variable de distancia (peso 0.0)
- CV_norm como dimensión secundaria (peso 0.5x)
- CV bifurcado: dependientes raw, independientes normalizado intra-grupo
- 15 clientes en portfolio (1 problemático: Pablo Pérez)
- Oscar Paduro agregado como exit #6 (pensionado Armada + U. Chile)

Vector: PD×3.0 + Pie×1.0 + C/I×1.5 + Tipo×1.0 + CV_norm×0.5
CR_ácido: solo gate binario (>=1.0). No entra en distancia euclidiana.
"""

import json
import math
import statistics

# ============================================================
# PORTFOLIO DATA (15 clientes — Ossian removido, Oscar Paduro agregado)
# ============================================================
# tipo: 1 = Dependiente, 0 = Independiente
# cr_acido: min(ingreso_recurrente) / cuota_clp
# cv: CV de liquidaciones pre-admisión (corregido)

PORTFOLIO = [
    {"nombre": "Adrián Zabaleta",   "pd": 0.05,   "pie": 0.123, "ratio": 0.349, "tipo": 1, "cr_acido": 1.05, "cv": 0.000, "outcome": "exit",         "detalle": "Enviado Coopeuch, Renta Nacional"},
    {"nombre": "Alicia Vega",       "pd": 0.05,   "pie": 0.299, "ratio": 0.211, "tipo": 0, "cr_acido": 2.12, "cv": 0.080, "outcome": "activo",       "detalle": "Engine v2.1: Deteriorating+Fragile"},
    {"nombre": "Álvaro Alvarado",   "pd": 0.25,   "pie": 0.130, "ratio": 0.317, "tipo": 1, "cr_acido": 1.90, "cv": 0.060, "outcome": "activo",       "detalle": "PD sobreestimada, RBI 100"},
    {"nombre": "Belén Vidal",       "pd": 0.0407, "pie": 0.091, "ratio": 0.297, "tipo": 0, "cr_acido": 1.78, "cv": 0.306, "outcome": "exit",         "detalle": "Aprobada Renta Nacional, pendiente BancoEstado"},
    {"nombre": "Brenda Ramírez",    "pd": 0.05,   "pie": 0.070, "ratio": 0.297, "tipo": 1, "cr_acido": 3.90, "cv": 0.027, "outcome": "exit",         "detalle": "Pre-aprobada Coopeuch"},
    {"nombre": "Gabriela González", "pd": 0.05,   "pie": 0.267, "ratio": 0.317, "tipo": 1, "cr_acido": 2.14, "cv": 0.029, "outcome": "exit",         "detalle": "Aprobada BancoEstado"},
    {"nombre": "Gerardo Aguayo",    "pd": 0.05,   "pie": 0.100, "ratio": 0.298, "tipo": 0, "cr_acido": 1.81, "cv": 0.310, "outcome": "activo",       "detalle": "Shock=Recovered, CV alto (honorarios)"},
    {"nombre": "Hugo Ayala",        "pd": 0.10,   "pie": 0.070, "ratio": 0.435, "tipo": 1, "cr_acido": 1.91, "cv": 0.050, "outcome": "activo",       "detalle": "Gendarmería, bonos retroactivos"},
    {"nombre": "Joaquín Morán",     "pd": 0.25,   "pie": 0.133, "ratio": None,  "tipo": 1, "cr_acido": 2.39, "cv": 0.029, "outcome": "activo",       "detalle": "Recién entró"},
    {"nombre": "Juan García",       "pd": 0.05,   "pie": 0.150, "ratio": 0.274, "tipo": 0, "cr_acido": 2.20, "cv": 0.000, "outcome": "activo",       "detalle": "Boletas fijas"},
    {"nombre": "María Pérez",       "pd": 0.05,   "pie": 0.396, "ratio": 0.526, "tipo": 1, "cr_acido": 2.21, "cv": 0.042, "outcome": "activo",       "detalle": "Pie muy alto, ratio muy alto"},
    {"nombre": "Oscar Paduro",      "pd": 0.10,   "pie": 0.2124,"ratio": 0.28,  "tipo": 1, "cr_acido": 3.57, "cv": 0.013, "outcome": "exit",         "detalle": "Pensionado Armada + U. Chile. PD 10% Sinacofi"},
    {"nombre": "Pablo Pérez",       "pd": 0.83,   "pie": 0.200, "ratio": 0.246, "tipo": 0, "cr_acido": 0.56, "cv": 0.478, "outcome": "problematico", "detalle": "CR<1, no cubre cuota en peor mes"},
    {"nombre": "Valentín Vidal",    "pd": 0.05,   "pie": 0.100, "ratio": 0.429, "tipo": 0, "cr_acido": 2.14, "cv": 0.353, "outcome": "activo",       "detalle": "Independiente, ratio alto pero RBI 100"},
    {"nombre": "Yenny Barreto",     "pd": 0.05,   "pie": 0.113, "ratio": 0.270, "tipo": 1, "cr_acido": 1.76, "cv": 0.012, "outcome": "exit",         "detalle": "Aprobada Evoluciona, Renta Nacional"},
]

# ============================================================
# NORMALIZACIÓN Y DISTANCIA
# ============================================================

# Rangos para min-max
RANGES = {
    "pd":       (0.0,  0.85),   # 0% a 85%
    "pie":      (0.0,  0.40),   # 0% a 40%
    "ratio":    (0.20, 0.55),   # 20% a 55%
    "cr_acido": (0.5,  5.0),    # 0.5x a 5.0x cobertura
    "cv_dep":   (0.0,  0.10),   # Dependientes: 0% a 10%
    "cv_ind":   (0.0,  0.60),   # Independientes: 0% a 60%
}

# Pesos v2.1
# CR_ácido REMOVIDO del vector — es gate binario, no variable de distancia.
# Liquidez excedente no correlaciona linealmente con éxito conductual.
WEIGHTS = {
    "pd":       3.0,    # Mayor poder discriminante (17x gap)
    "pie":      1.0,
    "ratio":    1.5,
    "tipo":     1.0,    # Penalización categórica
    "cv_norm":  0.5,    # CV normalizado — contexto secundario
}

def normalize(value, lo, hi):
    """Min-max normalization to [0, 1]"""
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))

def normalize_cv(cv_value, tipo):
    """CV bifurcado: normaliza según tipo de contrato"""
    if tipo == 1:  # Dependiente
        return normalize(cv_value, *RANGES["cv_dep"])
    else:  # Independiente
        return normalize(cv_value, *RANGES["cv_ind"])

def distance(postulante, cliente):
    """Distancia euclidiana ponderada normalizada — 5 dimensiones.
    CR_ácido NO participa: es gate binario, no variable de distancia."""
    d_sq = 0.0
    n_vars = 0.0

    # 1. PD
    d = normalize(postulante["pd"], *RANGES["pd"]) - normalize(cliente["pd"], *RANGES["pd"])
    d_sq += WEIGHTS["pd"] * d * d
    n_vars += WEIGHTS["pd"]

    # 2. Pie%
    d = normalize(postulante["pie"], *RANGES["pie"]) - normalize(cliente["pie"], *RANGES["pie"])
    d_sq += WEIGHTS["pie"] * d * d
    n_vars += WEIGHTS["pie"]

    # 3. Cuota/Ingreso — skip si alguno no tiene
    if cliente["ratio"] is not None and postulante["ratio"] is not None:
        d = normalize(postulante["ratio"], *RANGES["ratio"]) - normalize(cliente["ratio"], *RANGES["ratio"])
        d_sq += WEIGHTS["ratio"] * d * d
        n_vars += WEIGHTS["ratio"]

    # 4. Tipo contrato — penalización binaria
    if postulante["tipo"] != cliente["tipo"]:
        d_sq += WEIGHTS["tipo"] * 1.0
    n_vars += WEIGHTS["tipo"]

    # 5. CV normalizado (bifurcado por tipo)
    cv_post = normalize_cv(postulante["cv"], postulante["tipo"])
    cv_cli = normalize_cv(cliente["cv"], cliente["tipo"])
    d = cv_post - cv_cli
    d_sq += WEIGHTS["cv_norm"] * d * d
    n_vars += WEIGHTS["cv_norm"]

    return math.sqrt(d_sq / n_vars) if n_vars > 0 else 1.0

def similarity_pct(dist):
    """Distancia [0,1] → similaridad porcentual"""
    return max(0, round((1 - dist) * 100, 1))

# ============================================================
# MATCHING
# ============================================================
def find_similares(postulante, top_n=5):
    resultados = []
    for c in PORTFOLIO:
        d = distance(postulante, c)
        resultados.append({
            "nombre": c["nombre"],
            "pd": c["pd"],
            "pie": c["pie"],
            "ratio": c["ratio"],
            "tipo": "Dep" if c["tipo"] == 1 else "Indep",
            "cr_acido": c["cr_acido"],
            "cv": c["cv"],
            "outcome": c["outcome"],
            "detalle": c["detalle"],
            "distancia": round(d, 4),
            "similaridad": similarity_pct(d),
        })
    resultados.sort(key=lambda x: x["distancia"])
    return resultados[:top_n]

# ============================================================
# GATES (hard filters — pre-matching)
# ============================================================
def evaluar_gates(postulante):
    """Evalúa filtros duros antes del matching"""
    gates = []

    # Gate 1: CR Ácido >= 1.0
    cr = postulante["cr_acido"]
    gates.append({
        "nombre": "Cobertura Ácida",
        "valor": cr,
        "threshold": 1.0,
        "pass": cr >= 1.0,
        "detalle": f"min(ingreso recurrente) / cuota = {cr:.2f}x"
    })

    # Gate 2: CV < 0.08 (solo dependientes)
    if postulante["tipo"] == 1:
        cv = postulante["cv"]
        gates.append({
            "nombre": "CV Ingreso (Dependiente)",
            "valor": cv,
            "threshold": 0.08,
            "pass": cv < 0.08,
            "detalle": f"CV = {cv:.3f} {'< 0.08 ✓' if cv < 0.08 else '≥ 0.08 ✗'}"
        })
    else:
        gates.append({
            "nombre": "CV Ingreso (Independiente)",
            "valor": postulante["cv"],
            "threshold": None,
            "pass": True,
            "detalle": f"CV = {postulante['cv']:.3f} (metadata, sin gate duro)"
        })

    # Gate 3: PD < 10% (ideal < 5%)
    pd = postulante["pd"]
    gates.append({
        "nombre": "PD Sinacofi",
        "valor": pd,
        "threshold": 0.10,
        "pass": pd < 0.10,
        "detalle": f"PD = {pd*100:.1f}% {'< 10% ✓' if pd < 0.10 else '≥ 10% ✗'}"
    })

    return gates

# ============================================================
# BRIEF NARRATIVO (templates determinísticos)
# ============================================================
def generar_brief(postulante_nombre, similares, gates):
    lines = []
    n = len(similares)
    exits = [s for s in similares if s["outcome"] == "exit"]
    activos = [s for s in similares if s["outcome"] == "activo"]
    problematicos = [s for s in similares if s["outcome"] == "problematico"]
    mas = similares[0]

    # Gates summary
    gates_fail = [g for g in gates if not g["pass"]]
    if gates_fail:
        for g in gates_fail:
            lines.append(f"⚠ GATE FAIL: {g['nombre']} — {g['detalle']}")

    # Precedentes
    if len(exits) >= 3:
        lines.append(
            f"De los {n} clientes con perfil más comparable a {postulante_nombre}, "
            f"{len(exits)} fueron aprobados para crédito hipotecario. "
            f"Cliente más similar: {mas['nombre']} "
            f"(similaridad {mas['similaridad']}%, CR ácido {mas['cr_acido']:.2f}x). "
            f"{mas['detalle']}."
        )
    elif len(exits) >= 1:
        lines.append(
            f"De los {n} clientes más comparables, {len(exits)} logró exit hipotecario "
            f"y {len(activos)} siguen activos con buen comportamiento. "
            f"Cliente más similar: {mas['nombre']} (similaridad {mas['similaridad']}%)."
        )
    else:
        lines.append(
            f"Ninguno de los {n} clientes más comparables ha logrado exit hipotecario aún. "
            f"{len(activos)} siguen activos. "
            f"Cliente más similar: {mas['nombre']} (similaridad {mas['similaridad']}%)."
        )

    # Alerta problemáticos
    if problematicos:
        for p in problematicos:
            lines.append(
                f"Nota: {p['nombre']} tenía perfil con similaridad {p['similaridad']}% "
                f"y presenta deterioro activo (PD {p['pd']*100:.0f}%, CR {p['cr_acido']:.2f}x). "
                f"{p['detalle']}."
            )

    # CR ácido context
    crs = [s["cr_acido"] for s in similares]
    avg_cr = sum(crs) / len(crs)
    lines.append(
        f"CR ácido promedio de similares: {avg_cr:.2f}x. "
        f"{'Postulante por debajo del promedio de cobertura.' if postulante.get('cr_acido', 0) < avg_cr else 'Postulante en línea o por encima de sus pares.'}"
    )

    # Señal de confianza
    if gates_fail:
        lines.append("Señal de confianza: requiere atención. Uno o más gates no cumplidos.")
    elif len(exits) >= 3 and not problematicos:
        lines.append("Señal de confianza: alta. Precedentes consistentes sin casos adversos en el cluster.")
    elif len(exits) >= 1 and not problematicos:
        lines.append("Señal de confianza: moderada. Precedentes positivos pero muestra limitada.")
    elif problematicos:
        lines.append("Señal de confianza: requiere atención. Existen casos adversos con perfil parcialmente comparable.")
    else:
        lines.append("Señal de confianza: sin precedentes de exit. Información insuficiente para evaluar.")

    return "\n\n".join(lines)

# ============================================================
# EJECUCIÓN — CASO MONTECINOS
# ============================================================
if __name__ == "__main__":
    postulante = {
        "nombre": "Andrés Montecinos",
        "pd": 0.05,
        "pie": 0.10,
        "ratio": 0.367,
        "tipo": 1,          # dependiente indefinido
        "cr_acido": 1.39,   # min($1.27M) / cuota($912K)
        "cv": 0.006,        # CV de liquidaciones = 0.6%
    }

    print("=" * 80)
    print("PROPIO — Similarity Matching v2")
    print("=" * 80)
    print(f"\nPostulante: {postulante['nombre']}")
    print(f"  PD: {postulante['pd']*100:.1f}%  |  Pie: {postulante['pie']*100:.1f}%  |  C/I: {postulante['ratio']*100:.1f}%")
    print(f"  Tipo: {'Dependiente' if postulante['tipo'] == 1 else 'Independiente'}  |  CR ácido: {postulante['cr_acido']:.2f}x  |  CV: {postulante['cv']:.3f}")

    # Gates
    gates = evaluar_gates(postulante)
    print(f"\n{'─' * 80}")
    print("GATES")
    print(f"{'─' * 80}")
    for g in gates:
        status = "✓ PASS" if g["pass"] else "✗ FAIL"
        print(f"  {status}  {g['nombre']}: {g['detalle']}")

    all_pass = all(g["pass"] for g in gates)
    print(f"\n  → {'Todos los gates PASS. Procede al matching.' if all_pass else '⚠ Gate(s) fallido(s). Requiere revisión.'}")

    # Matching
    top5 = find_similares(postulante, top_n=5)
    print(f"\n{'─' * 80}")
    print("TOP 5 CLIENTES MÁS SIMILARES")
    print(f"{'─' * 80}")
    print(f"{'#':<3} {'Nombre':<22} {'Sim%':>5} {'PD':>7} {'Pie%':>7} {'C/I%':>7} {'CR':>5} {'CV':>6} {'Outcome':<13}")
    print(f"{'─' * 80}")
    for i, s in enumerate(top5, 1):
        ratio_str = f"{s['ratio']*100:.1f}%" if s['ratio'] else "N/A"
        print(f"{i:<3} {s['nombre']:<22} {s['similaridad']:>4.1f}% {s['pd']*100:>6.1f}% {s['pie']*100:>6.1f}% {ratio_str:>7} {s['cr_acido']:>5.2f} {s['cv']:>.4f} {s['outcome']:<13}")

    # Brief
    print(f"\n{'─' * 80}")
    print("BRIEF PARA COMITÉ")
    print(f"{'─' * 80}")
    brief = generar_brief(postulante["nombre"], top5, gates)
    print(brief)

    # Full ranking
    print(f"\n{'─' * 80}")
    print("RANKING COMPLETO (15 clientes)")
    print(f"{'─' * 80}")
    todos = find_similares(postulante, top_n=15)
    for i, s in enumerate(todos, 1):
        ratio_str = f"{s['ratio']*100:.1f}%" if s['ratio'] else "N/A"
        marker = " ◄" if s['outcome'] == 'exit' else (" ⚠" if s['outcome'] == 'problematico' else "")
        print(f"{i:>2}. {s['nombre']:<22} Sim={s['similaridad']:>4.1f}%  PD={s['pd']*100:>5.1f}%  CR={s['cr_acido']:>4.2f}  CV={s['cv']:.3f}  → {s['outcome']}{marker}")

    # Export
    output = {
        "postulante": postulante,
        "gates": gates,
        "all_gates_pass": all_pass,
        "top5": top5,
        "brief": brief,
        "metadata": {
            "engine": "similarity_matching_v2",
            "variables_distancia": ["pd_sinacofi", "pie_pct", "cuota_ingreso_pct", "tipo_contrato", "cv_norm"],
            "gates_binarios": ["cr_acido >= 1.0", "cv < 0.08 (dep)", "pd < 0.10"],
            "weights": WEIGHTS,
            "ranges": RANGES,
            "n_portfolio": len(PORTFOLIO),
            "removed": ["Ossian Leiva (caso puntual, no estructural)"],
            "changes_vs_v1": [
                "CR_ácido REMOVIDO del vector (era peso 2.0x) — ahora solo gate binario",
                "CV bifurcado: dep raw [0,0.10], indep normalizado [0,0.60]",
                "CV como metadata secundaria (peso 0.5x)",
                "Ossian Leiva removido del portfolio",
                "Gates: CR>=1.0, CV<0.08 (dep only), PD<10%"
            ]
        }
    }

    with open("/sessions/optimistic-trusting-lamport/mnt/similarity_output_v2_montecinos.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n✓ Output exportado a similarity_output_v2_montecinos.json")
