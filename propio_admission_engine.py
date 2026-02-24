"""
PROPIO — Motor de Admisión v3.0
================================
Ejecutar: python propio_admission_engine.py

Flujo:
  1. Credit Score (4 verticales + renta depurada + PD)
  2. Asset Credit Score (5 dimensiones)
  3. Matriz Credit × Asset → Nivel → Decisión
  4. Plusvalía & Exit (motor de amortización + simulación hipotecaria)
  5. Gates complementarios (CR ácido, CV, PD)
  6. Similarity Matching (5D euclidiana)
  7. Marcadores Semánticos (M1, M2, M3)
  8. Brief determinístico

Requisitos: Python 3.9+, sin dependencias externas.
"""

import json
import math
import os
from datetime import datetime

from asset_credit_score import run_asset_score

# ============================================================
# PORTFOLIO (15 clientes — Ossian removido, Oscar Paduro agregado)
# ============================================================
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
    {"nombre": "Oscar Paduro",      "pd": 0.10,   "pie": 0.2124,"ratio": 0.28,  "tipo": 1, "cr_acido": 3.57, "cv": 0.013, "outcome": "exit",         "detalle": "Pensionado Armada + U. Chile"},
    {"nombre": "Pablo Pérez",       "pd": 0.83,   "pie": 0.200, "ratio": 0.246, "tipo": 0, "cr_acido": 0.56, "cv": 0.478, "outcome": "problematico", "detalle": "CR<1, no cubre cuota en peor mes"},
    {"nombre": "Valentín Vidal",    "pd": 0.05,   "pie": 0.100, "ratio": 0.429, "tipo": 0, "cr_acido": 2.14, "cv": 0.353, "outcome": "activo",       "detalle": "Independiente, ratio alto pero RBI 100"},
    {"nombre": "Yenny Barreto",     "pd": 0.05,   "pie": 0.113, "ratio": 0.270, "tipo": 1, "cr_acido": 1.76, "cv": 0.012, "outcome": "exit",         "detalle": "Aprobada Evoluciona, Renta Nacional"},
]

# ============================================================
# CONFIGURACIÓN
# ============================================================
RANGES = {
    "pd":     (0.0, 0.85),
    "pie":    (0.0, 0.40),
    "ratio":  (0.20, 0.55),
    "cv_dep": (0.0, 0.10),
    "cv_ind": (0.0, 0.60),
}

WEIGHTS = {
    "pd":      3.0,
    "pie":     1.0,
    "ratio":   1.5,
    "tipo":    1.0,
    "cv_norm": 0.5,
}

# Marcadores Semánticos — niveles para vertical Política
MARCADOR_NIVELES = {
    "M1": {
        1: {"label": "RÍGIDO",       "desc": ">95% ingreso fijo, varianza irrelevante", "valor": 0.00},
        2: {"label": "ESTRUCTURAL",  "desc": "Variable predecible (bonos por ley, comisiones con piso)", "valor": 0.33},
        3: {"label": "MIXTO",        "desc": "Componente variable significativo pero con base", "valor": 0.66},
        4: {"label": "VOLÁTIL",      "desc": "Predominantemente variable, sin piso garantizado", "valor": 1.00},
    },
    "M2": {
        1: {"label": "MUY BAJO",     "desc": "Estado, FFAA, utilities reguladas, universidades públicas", "valor": 0.00},
        2: {"label": "BAJO",         "desc": "Empresa grande privada, sector estable, >3 años", "valor": 0.33},
        3: {"label": "MEDIO",        "desc": "Pyme establecida, sector cíclico", "valor": 0.66},
        4: {"label": "ALTO",         "desc": "Startup, honorarios sin contrato, sector inestable", "valor": 1.00},
    },
    "M3": {
        1: {"label": "LIMPIO",           "desc": "Sin señales de deuda sombra", "valor": 0.00},
        2: {"label": "OBSERVACIÓN",      "desc": "Patrones menores, monitorear", "valor": 0.33},
        3: {"label": "BANDERA AMARILLA", "desc": "Señales de apalancamiento paralelo", "valor": 0.66},
        4: {"label": "BANDERA ROJA",     "desc": "Deuda sombra evidente", "valor": 1.00},
    },
}


# ============================================================
# FUNCIONES CORE
# ============================================================
def normalize(value, lo, hi):
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def normalize_cv(cv_value, tipo):
    if tipo == 1:
        return normalize(cv_value, *RANGES["cv_dep"])
    else:
        return normalize(cv_value, *RANGES["cv_ind"])


def distance(postulante, cliente):
    """Distancia euclidiana ponderada — 5 dimensiones."""
    d_sq = 0.0
    n_vars = 0.0

    # PD
    d = normalize(postulante["pd"], *RANGES["pd"]) - normalize(cliente["pd"], *RANGES["pd"])
    d_sq += WEIGHTS["pd"] * d * d
    n_vars += WEIGHTS["pd"]

    # Pie
    d = normalize(postulante["pie"], *RANGES["pie"]) - normalize(cliente["pie"], *RANGES["pie"])
    d_sq += WEIGHTS["pie"] * d * d
    n_vars += WEIGHTS["pie"]

    # Ratio — skip si alguno no tiene
    if cliente["ratio"] is not None and postulante["ratio"] is not None:
        d = normalize(postulante["ratio"], *RANGES["ratio"]) - normalize(cliente["ratio"], *RANGES["ratio"])
        d_sq += WEIGHTS["ratio"] * d * d
        n_vars += WEIGHTS["ratio"]

    # Tipo contrato
    if postulante["tipo"] != cliente["tipo"]:
        d_sq += WEIGHTS["tipo"] * 1.0
    n_vars += WEIGHTS["tipo"]

    # CV normalizado
    cv_post = normalize_cv(postulante["cv"], postulante["tipo"])
    cv_cli = normalize_cv(cliente["cv"], cliente["tipo"])
    d = cv_post - cv_cli
    d_sq += WEIGHTS["cv_norm"] * d * d
    n_vars += WEIGHTS["cv_norm"]

    return math.sqrt(d_sq / n_vars) if n_vars > 0 else 1.0


def similarity_pct(dist):
    return max(0, round((1 - dist) * 100, 1))


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
# GATES
# ============================================================
def evaluar_gates(postulante):
    gates = []
    cr = postulante["cr_acido"]
    gates.append({
        "nombre": "Cobertura Ácida",
        "valor": cr,
        "threshold": 1.0,
        "pass": cr >= 1.0,
        "detalle": f"min(ingreso recurrente) / cuota = {cr:.2f}x"
    })

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
        cv = postulante["cv"]
        gates.append({
            "nombre": "CV Ingreso (Independiente)",
            "valor": cv,
            "threshold": None,
            "pass": True,
            "detalle": f"CV = {cv:.3f} (metadata — flag comité si CV > 0.25)"
        })

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
# BRIEF (templates determinísticos)
# ============================================================
def generar_brief(nombre, similares, gates):
    lines = []
    exits = [s for s in similares if s["outcome"] == "exit"]
    problematicos = [s for s in similares if s["outcome"] == "problematico"]
    mas = similares[0]

    gates_fail = [g for g in gates if not g["pass"]]
    if gates_fail:
        for g in gates_fail:
            lines.append(f"⚠ GATE FAIL: {g['nombre']} — {g['detalle']}")

    if len(exits) >= 3:
        lines.append(
            f"De los {len(similares)} clientes con perfil más comparable a {nombre}, "
            f"{len(exits)} fueron aprobados para crédito hipotecario. "
            f"Cliente más similar: {mas['nombre']} (similaridad {mas['similaridad']}%). "
            f"{mas['detalle']}."
        )
    elif len(exits) >= 1:
        lines.append(
            f"De los {len(similares)} más comparables, {len(exits)} logró exit hipotecario. "
            f"Cliente más similar: {mas['nombre']} (similaridad {mas['similaridad']}%)."
        )
    else:
        lines.append(f"Ninguno de los {len(similares)} más comparables ha logrado exit.")

    if problematicos:
        for p in problematicos:
            lines.append(
                f"Nota: {p['nombre']} (similaridad {p['similaridad']}%) presenta deterioro activo."
            )

    if gates_fail:
        lines.append("Señal de confianza: requiere atención.")
    elif len(exits) >= 3 and not problematicos:
        lines.append("Señal de confianza: alta.")
    elif len(exits) >= 1:
        lines.append("Señal de confianza: moderada.")
    else:
        lines.append("Señal de confianza: sin precedentes de exit.")

    return "\n".join(lines)


# ============================================================
# MARCADORES SEMÁNTICOS — Estructura de datos
# ============================================================
def crear_marcador(marcador_id, nivel, narrativa, datos_soporte=None):
    """
    Crea un marcador semántico validado.

    Args:
        marcador_id: "M1", "M2", o "M3"
        nivel: 1-4 (clasificado por AI, validado por operador)
        narrativa: texto explicativo generado por AI
        datos_soporte: dict con evidencia (glosas, empleador, etc.)

    Returns:
        dict con marcador completo
    """
    config = MARCADOR_NIVELES[marcador_id][nivel]
    trunca = nivel == 4

    return {
        "id": marcador_id,
        "nivel": nivel,
        "label": config["label"],
        "descripcion": config["desc"],
        "valor_politica": config["valor"],
        "trunca": trunca,
        "narrativa": narrativa,
        "datos_soporte": datos_soporte or {},
        "validado_por_operador": False,  # Siempre False hasta que operador confirme
    }


# ============================================================
# EJECUCIÓN COMPLETA
# ============================================================
def run_admission(postulante, marcadores=None, activo=None,
                  cliente_credit=None, datos_plusvalor=None,
                  stress_input=None):
    """
    Ejecuta el motor completo de admisión v3.0.

    Args:
        postulante: dict con {nombre, pd, pie, ratio, tipo, cr_acido, cv}
        marcadores: lista de marcadores semánticos (output de crear_marcador)
        activo: dict con datos del activo (opcional). Si se pasa, corre Asset Credit Score.
        cliente_credit: dict con datos para Credit Score (opcional). Ver credit_score.run_credit_score.
        datos_plusvalor: dict con datos para Motor de Plusvalía (opcional). Ver plusvalor_engine.run_plusvalor.

    Returns:
        dict con resultado completo
    """
    # 1. Gates complementarios
    gates = evaluar_gates(postulante)
    all_gates_pass = all(g["pass"] for g in gates)

    # 2. Matching
    top5 = find_similares(postulante, top_n=5)
    ranking = find_similares(postulante, top_n=len(PORTFOLIO))

    # 3. Brief
    brief = generar_brief(postulante["nombre"], top5, gates)

    # 4. Marcadores — check truncamiento
    marcadores = marcadores or []
    politica_trunca = any(m["trunca"] for m in marcadores)

    # 5. Asset Credit Score
    asset_score = None
    if activo is not None:
        asset_score = run_asset_score(activo)

    # 6. Credit Score (lazy import — module optional for web deploy)
    credit_score_result = None
    if cliente_credit is not None:
        from credit_score import run_credit_score
        credit_score_result = run_credit_score(cliente_credit)

    # 7. Matriz Credit × Asset
    matrix_result = None
    if credit_score_result and asset_score and "error" not in asset_score:
        from credit_score import lookup_matrix
        matrix_result = lookup_matrix(
            credit_score_result["credit_score"],
            asset_score["total"],
        )

    # 8. Motor de Plusvalía & Exit (lazy import — module optional for web deploy)
    plusvalor_result = None
    if datos_plusvalor is not None:
        from plusvalor_engine import run_plusvalor
        plusvalor_result = run_plusvalor(datos_plusvalor)

    # 9. Stress Test (lazy import — module optional for web deploy)
    stress_result = None
    if stress_input is not None:
        from stress_test import run_stress_test
        stress_result = run_stress_test(
            cuota=stress_input["cuota"],
            ingreso=stress_input["ingreso"],
            score=stress_input["score"],
            tipo=stress_input["tipo"],
            egreso_total=stress_input.get("egreso_total"),
        )

    resultado = {
        "postulante": postulante,
        # --- EJE FORMAL (Motor 19.12) ---
        "credit_score": credit_score_result,
        "asset_score": asset_score,
        "matrix": matrix_result,
        # --- PLUSVALÍA & EXIT ---
        "plusvalor": plusvalor_result,
        # --- STRESS TEST ---
        "stress_test": stress_result,
        # --- CAPA COMPLEMENTARIA ---
        "gates": {
            "detalle": gates,
            "all_pass": all_gates_pass,
        },
        "matching": {
            "top5": top5,
            "ranking_completo": ranking,
        },
        "brief": brief,
        "marcadores_semanticos": {
            "marcadores": marcadores,
            "politica_trunca": politica_trunca,
            "resumen": {m["id"]: f"Nivel {m['nivel']} — {m['label']}" for m in marcadores},
        },
        "metadata": {
            "engine": "propio_admission_v3.0",
            "timestamp": datetime.now().isoformat(),
            "n_portfolio": len(PORTFOLIO),
            "modules_enabled": {
                "credit_score": cliente_credit is not None,
                "asset_score": activo is not None,
                "matrix": matrix_result is not None,
                "plusvalor": datos_plusvalor is not None,
                "stress_test": stress_input is not None,
                "marcadores": len(marcadores) > 0,
            },
        }
    }

    return resultado


def print_resultado(r):
    """Imprime resultado en consola."""
    p = r["postulante"]
    print("=" * 80)
    print(f"PROPIO — Motor de Admisión v3.0")
    print("=" * 80)
    print(f"\nPostulante: {p['nombre']}")
    print(f"  PD: {p['pd']*100:.1f}%  |  Pie: {p['pie']*100:.1f}%  |  C/I: {p['ratio']*100:.1f}%")
    print(f"  Tipo: {'Dep' if p['tipo']==1 else 'Indep'}  |  CR ácido: {p['cr_acido']:.2f}x  |  CV: {p['cv']:.3f}")

    # --- CREDIT SCORE ---
    cs = r.get("credit_score")
    if cs:
        print(f"\n{'─' * 80}")
        print("CREDIT SCORE (Motor 19.12)")
        print(f"{'─' * 80}")
        print(f"  Credit Score: {cs['credit_score']}  |  PD ajustada: {cs['pd']['pd_ajustada']*100:.2f}%")
        renta = cs.get("renta", {})
        if renta:
            print(f"  Renta depurada: ${renta.get('renta_total', 0):,.0f}")
        endeu = cs.get("endeudamiento", {})
        if endeu:
            er = endeu.get("egreso_renta", 0)
            print(f"  Egreso/Renta: {er*100:.1f}%")
        verts = cs["verticales"]
        print(f"  Verticales:")
        for v_name, v_data in verts.items():
            print(f"    {v_name:<20} Nivel {v_data['score']}")

    # --- ASSET CREDIT SCORE ---
    if r.get("asset_score") and "error" not in r["asset_score"]:
        a = r["asset_score"]
        print(f"\n{'─' * 80}")
        print("ASSET CREDIT SCORE v2.2")
        print(f"{'─' * 80}")
        print(f"  Score: {a['total']}  |  Decisión: {a['decision']}  |  Confianza: {a['nivel_confianza']}")
        for dim, data in a["dimensiones"].items():
            print(f"    {dim:<14} {data['score']:>7.2f}  (x{data['peso']:.0%} = {data['ponderado']:.2f})")
        gk = a["gatekeepers"]
        print(f"  Gatekeepers: {'✓ Todos PASS' if gk['all_pass'] else '⚠ FALLA'}")
        if a["alerta"] != "Sin alertas críticas":
            print(f"  ⚠ {a['alerta']}")
        print(f"  → {a['recomendacion']}")

    # --- MATRIX ---
    mx = r.get("matrix")
    if mx:
        print(f"\n{'─' * 80}")
        print("MATRIZ CREDIT x ASSET")
        print(f"{'─' * 80}")
        print(f"  Rating: {mx['rating']}  |  Nivel: {mx['nivel']}  |  Decisión: {mx['decision']}")
        print(f"  Banda Credit: {mx['credit_band']}  |  Banda Asset: {mx['asset_band']}")

    # --- PLUSVALOR ---
    pv = r.get("plusvalor")
    if pv:
        print(f"\n{'─' * 80}")
        print("PLUSVALÍA & EXIT")
        print(f"{'─' * 80}")
        motor = pv["motor"]
        ex = pv["exit"]
        print(f"  Arriendo: {motor['arriendo_uf']:.2f} UF  |  Alpha: {motor['alpha']:.4f}")
        print(f"  Exit: mes {ex['mes']}  ({ex['anos']:.1f} años)  |  Ahorro: {ex['ahorro_meses']} meses vs sin plusvalía")
        hip = pv.get("hipotecario", {})
        if hip:
            califica = "Califica" if hip.get("pass") else "No califica"
            print(f"  Hipotecario: dividendo {hip['dividendo_uf']:.2f} UF  |  ratio {hip['ratio_dividendo_ingreso']*100:.1f}%  |  {califica}")
        print(f"  Sensibilidad IPV:")
        for s in pv.get("sensibilidad_ipv", []):
            exit_str = f"mes {s['exit_mes']}" if s['exit_mes'] and s['exit_mes'] <= 60 else "no alcanza"
            print(f"    IPV {s['ipv']*100:.0f}%: {exit_str}")

    # --- STRESS TEST ---
    st = r.get("stress_test")
    if st:
        print(f"\n{'─' * 80}")
        print("STRESS TEST")
        print(f"{'─' * 80}")
        pre = st["pre_estres"]
        s = st["stress"]
        d = st["decision"]
        print(f"  Pre-estrés:")
        print(f"    C/I: {pre['ratio_ci']:.1%}  |  Tramo: {st['tramo']['rango']}  |  Max: {st['tramo']['cuota_max']:.0%}")
        ci_status = "✓" if d["ci_en_tramo"] else "✗ FLAG COMITÉ"
        print(f"    En tramo: {ci_status}")
        print(f"  Stress:")
        print(f"    Haircut: {s['haircut_pct']:.0%} ({s['tipo_label']})")
        print(f"    Ingreso estresado: ${s['ingreso_estresado']:,.0f}")
        print(f"    C/I estresado: {s['ratio_ci_estresado']:.1%}")
        gate_status = "✓ PASA" if s["pasa_hard_gate"] else "✗ RECHAZADO"
        print(f"    Hard gate (≤45%): {gate_status}")
        print(f"\n  → {d['resumen']}")

    # --- GATES ---
    print(f"\n{'─' * 80}")
    print("GATES COMPLEMENTARIOS")
    print(f"{'─' * 80}")
    for g in r["gates"]["detalle"]:
        status = "✓ PASS" if g["pass"] else "✗ FAIL"
        print(f"  {status}  {g['nombre']}: {g['detalle']}")
    print(f"\n  → {'Todos PASS' if r['gates']['all_pass'] else '⚠ Gate(s) fallido(s)'}")

    # --- TOP 5 ---
    print(f"\n{'─' * 80}")
    print("TOP 5 SIMILARES")
    print(f"{'─' * 80}")
    print(f"{'#':<3} {'Nombre':<22} {'Sim%':>5} {'PD':>7} {'Pie%':>7} {'C/I%':>7} {'Outcome':<13}")
    for i, s in enumerate(r["matching"]["top5"], 1):
        ratio_str = f"{s['ratio']*100:.1f}%" if s['ratio'] else "N/A"
        print(f"{i:<3} {s['nombre']:<22} {s['similaridad']:>4.1f}% {s['pd']*100:>6.1f}% {s['pie']*100:>6.1f}% {ratio_str:>7} {s['outcome']}")

    # --- BRIEF ---
    print(f"\n{'─' * 80}")
    print("BRIEF")
    print(f"{'─' * 80}")
    print(r["brief"])

    # --- MARCADORES ---
    if r["marcadores_semanticos"]["marcadores"]:
        print(f"\n{'─' * 80}")
        print("MARCADORES SEMÁNTICOS (Vertical: Política)")
        print(f"{'─' * 80}")
        for m in r["marcadores_semanticos"]["marcadores"]:
            trunca_str = " [TRUNCA POLÍTICA]" if m["trunca"] else ""
            validado = "✓" if m["validado_por_operador"] else "pendiente"
            print(f"  {m['id']}: Nivel {m['nivel']} — {m['label']}{trunca_str}  (validación: {validado})")
            print(f"       {m['narrativa'][:120]}...")
        if r["marcadores_semanticos"]["politica_trunca"]:
            print(f"\n  ⚠ POLÍTICA TRUNCADA: Nivel 4 detectado. No aprueba.")

    # --- METADATA ---
    meta = r["metadata"]
    print(f"\n{'─' * 80}")
    print(f"Engine: {meta['engine']}  |  Portfolio: {meta['n_portfolio']}  |  {meta['timestamp']}")
    mods = meta["modules_enabled"]
    enabled = [k for k, v in mods.items() if v]
    print(f"  Módulos activos: {', '.join(enabled) if enabled else 'solo gates+matching'}")


# ============================================================
# EJEMPLO — CASO MONTECINOS
# ============================================================
if __name__ == "__main__":

    # --- DATOS DEL POSTULANTE ---
    postulante = {
        "nombre": "Andrés Montecinos",
        "pd": 0.05,
        "pie": 0.10,
        "ratio": 0.367,
        "tipo": 1,
        "cr_acido": 1.39,
        "cv": 0.006,
    }

    # --- MARCADORES SEMÁNTICOS (clasificados por AI, pendientes de validación) ---
    m1 = crear_marcador(
        "M1", nivel=1,
        narrativa=(
            "CV observado: 0.6%. 99.6% del ingreso es estructural fijo: sueldo base "
            "($3,037,000), gratificación ($418,792) y bonos ($473,193) idénticos en 3 meses. "
            "Única fuente de varianza: horas extras ($13K-$71K sobre $3.4M). "
            "Ingreso predecible mes a mes. Sin riesgo de caída por componente variable."
        ),
        datos_soporte={
            "pct_fijo": 0.984,
            "componentes_fijos": ["sueldo_base", "gratificacion", "bonos"],
            "componente_variable": "horas_extras",
            "rango_variable": {"min": 13897, "max": 71485},
            "renta_depurada_promedio": 3410985,
        }
    )

    m2 = crear_marcador(
        "M2", nivel=1,
        narrativa=(
            "Empleador: AES Andes (ex AES Gener). Multinacional energética, parte de "
            "AES Corporation (NYSE: AES). Mayor generadora eléctrica de Chile. "
            "Sector regulado, infraestructura crítica, demanda inelástica. "
            "Cargo: Analista de Redes (técnico operativo, baja exposición a reestructuración). "
            "Contrato indefinido desde Nov 2024 (~15 meses). "
            "Codeudor: Javiera Melo, Swiss Trading Group, indefinido desde May 2022 (~3.7 años)."
        ),
        datos_soporte={
            "empleador": "AES Andes",
            "sector": "Energía / Utilities",
            "tipo_empresa": "Multinacional (NYSE: AES)",
            "cargo": "Analista de Redes",
            "contrato": "Indefinido",
            "antiguedad_meses": 15,
            "codeudor_empleador": "Swiss Trading Group",
            "codeudor_antiguedad_meses": 44,
        }
    )

    # --- DATOS DEL ACTIVO ---
    activo = {
        "direccion": "Santa Leonor 741",
        "comuna": "Padre hurtado",
        "precio_uf": 4487.22,
        "buffer_pct": 0.15,
        "renta_mensual_uf": 22.0,
        "opex_mensual_uf": 3.55,
        "antiguedad_anos": 0,
        "fase_economica": "NORMAL",
        "trimestre": "Q3",
        "estado_fisico": 10,
        "cumplimiento_legal": 10,
        "riesgo_sismico": 8,
        "conectividad": 4,
        "servicios": 6,
        "velocidad_absorcion": 6,
        "demanda_zona": 8,
        "renta_cliente_uf": 24.0,
    }

    # --- DATOS CREDIT SCORE (Motor 19.12) ---
    cliente_credit = {
        "pd_sinacofi": 0.05,
        "score_sinacofi": 534,
        "rbi": None,  # No existe en admisión
        "tipo_contrato": "dependiente",
        "antiguedad_meses": 15,
        "historial_equifax_meses": 36,
        "morosidades_vigentes": 0,
        "protestos": 0,
        "deuda_total_clp": 0,
        "cuota_propio_clp": 1_155_384,
        "otros_creditos_clp": 0,
        "ingreso_bruto_clp": 3_929_285,
        "liquidaciones": [
            {"total_haberes": 3_410_985, "colacion": 0, "movilizacion": 0},
            {"total_haberes": 3_420_000, "colacion": 0, "movilizacion": 0},
            {"total_haberes": 3_402_000, "colacion": 0, "movilizacion": 0},
        ],
        "valor_prop_uf": 4487.22,
        "pie_pct": 0.10,
        "ltv": 0.90,
        "plazo_meses": 60,
        "tasa_anual": 0.065,
        "arriendo_uf": 22.0,
        "cuota_ingreso_ratio": 0.367,
    }

    # --- DATOS PLUSVALOR ---
    valor_prop = 4487.22
    pie_uf = valor_prop * 0.10  # 10% pie
    meta_uf = valor_prop * 0.20  # meta 20%
    cuota_propio_uf = 1_155_384 / 35660  # CLP → UF aprox
    datos_plusvalor = {
        "valor_activo": valor_prop,
        "pie_uf": pie_uf,
        "meta_uf": meta_uf,
        "cuota_propio": cuota_propio_uf,
        "ingreso_uf": 110.0,
        "ipv": 0.03,
        "plazo_max": 60,
        "tasa_banco": 0.045,
        "plazo_hipotecario": 240,
    }

    # --- DATOS STRESS TEST ---
    stress_input = {
        "cuota": 1_155_384,
        "ingreso": 3_410_985,
        "score": 534,
        "tipo": 1,  # dependiente
    }

    # --- EJECUTAR v3.0 ---
    resultado = run_admission(
        postulante,
        marcadores=[m1, m2],
        activo=activo,
        cliente_credit=cliente_credit,
        datos_plusvalor=datos_plusvalor,
        stress_input=stress_input,
    )

    # --- IMPRIMIR ---
    print_resultado(resultado)

    # --- EXPORTAR JSON ---
    output_path = os.path.join(os.path.dirname(__file__), "admission_output_montecinos.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n✓ Output exportado a {output_path}")

    # --- RANKING COMPLETO ---
    print(f"\n{'─' * 80}")
    print(f"RANKING COMPLETO ({len(PORTFOLIO)} clientes)")
    print(f"{'─' * 80}")
    for i, s in enumerate(resultado["matching"]["ranking_completo"], 1):
        marker = " ◄" if s['outcome'] == 'exit' else (" ⚠" if s['outcome'] == 'problematico' else "")
        print(f"{i:>2}. {s['nombre']:<22} Sim={s['similaridad']:>4.1f}%  → {s['outcome']}{marker}")
