"""
PROPIO — Motor de Admisión v2.1 + Marcadores Semánticos
========================================================
Ejecutar: python propio_admission_engine.py

Flujo:
  1. Gates binarios (pasa/no pasa)
  2. Similarity Matching (5D euclidiana)
  3. Marcadores Semánticos (clasificación para vertical Política)
  4. Genera HTML para Comité

Requisitos: Python 3.9+, sin dependencias externas.
"""

import json
import math
import os
from datetime import datetime

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
        gates.append({
            "nombre": "CV Ingreso (Independiente)",
            "valor": postulante["cv"],
            "threshold": None,
            "pass": True,
            "detalle": f"CV = {postulante['cv']:.3f} (metadata, sin gate duro)"
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
def run_admission(postulante, marcadores=None):
    """
    Ejecuta el motor completo de admisión.

    Args:
        postulante: dict con {nombre, pd, pie, ratio, tipo, cr_acido, cv}
        marcadores: lista de marcadores semánticos (output de crear_marcador)

    Returns:
        dict con resultado completo
    """
    # 1. Gates
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

    resultado = {
        "postulante": postulante,
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
            "engine": "propio_admission_v2.1",
            "timestamp": datetime.now().isoformat(),
            "n_portfolio": len(PORTFOLIO),
            "variables_distancia": ["pd", "pie", "ratio", "tipo", "cv_norm"],
            "gates": ["cr_acido >= 1.0", "cv < 0.08 (dep)", "pd < 0.10"],
            "weights": WEIGHTS,
        }
    }

    return resultado


def print_resultado(r):
    """Imprime resultado en consola."""
    p = r["postulante"]
    print("=" * 80)
    print(f"PROPIO — Motor de Admisión v2.1")
    print("=" * 80)
    print(f"\nPostulante: {p['nombre']}")
    print(f"  PD: {p['pd']*100:.1f}%  |  Pie: {p['pie']*100:.1f}%  |  C/I: {p['ratio']*100:.1f}%")
    print(f"  Tipo: {'Dep' if p['tipo']==1 else 'Indep'}  |  CR ácido: {p['cr_acido']:.2f}x  |  CV: {p['cv']:.3f}")

    print(f"\n{'─' * 80}")
    print("GATES")
    print(f"{'─' * 80}")
    for g in r["gates"]["detalle"]:
        status = "✓ PASS" if g["pass"] else "✗ FAIL"
        print(f"  {status}  {g['nombre']}: {g['detalle']}")
    print(f"\n  → {'Todos PASS' if r['gates']['all_pass'] else '⚠ Gate(s) fallido(s)'}")

    print(f"\n{'─' * 80}")
    print("TOP 5 SIMILARES")
    print(f"{'─' * 80}")
    print(f"{'#':<3} {'Nombre':<22} {'Sim%':>5} {'PD':>7} {'Pie%':>7} {'C/I%':>7} {'Outcome':<13}")
    for i, s in enumerate(r["matching"]["top5"], 1):
        ratio_str = f"{s['ratio']*100:.1f}%" if s['ratio'] else "N/A"
        print(f"{i:<3} {s['nombre']:<22} {s['similaridad']:>4.1f}% {s['pd']*100:>6.1f}% {s['pie']*100:>6.1f}% {ratio_str:>7} {s['outcome']}")

    print(f"\n{'─' * 80}")
    print("BRIEF")
    print(f"{'─' * 80}")
    print(r["brief"])

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

    # --- EJECUTAR ---
    resultado = run_admission(postulante, marcadores=[m1, m2])

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
