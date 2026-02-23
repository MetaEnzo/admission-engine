"""
PROPIO — Asset Credit Score v2.2
=================================
Motor determinístico para scoring de activos inmobiliarios.
Replica exactamente la lógica del Excel Asset Credit Score v2.2.

5 dimensiones:
  - Liquidez (40%)
  - Cap Rate (30%)
  - Estructural (20%)
  - Locación (5%)
  - Tipología (5%)

Dependencias: solo math (stdlib). Sin scipy — CDF normal implementada con math.erf.

Fuente: Asset Credit Score Andres montecinos.xlsx (hoja EVALUACION, 104 fórmulas)
"""

import math
from datetime import datetime


# ============================================================
# DATOS_MERCADO — lookup por comuna
# Fuente: hoja DATOS_MERCADO del Excel v2.2
# Columnas: DTS, QSD, Vol, Trx, Stk, Cap_Min, Cap_Max, ICVU, ISMT, IPS, Zona, Riesgo
# ============================================================
DATOS_MERCADO = {
    "San Bernardo":      {"dts": 70,  "qsd": 0.07,  "vol": 0.16, "trx": 45, "stk": 380, "cap_min": 0.055, "cap_max": 0.065, "icvu": 55, "ismt": 65, "ips": 35, "zona": "Sur",             "riesgo": "Medio"},
    "Maipu":             {"dts": 65,  "qsd": 0.06,  "vol": 0.15, "trx": 50, "stk": 320, "cap_min": 0.055, "cap_max": 0.065, "icvu": 65, "ismt": 70, "ips": 30, "zona": "Poniente",         "riesgo": "Medio"},
    "La Florida":        {"dts": 60,  "qsd": 0.055, "vol": 0.14, "trx": 60, "stk": 350, "cap_min": 0.054, "cap_max": 0.064, "icvu": 70, "ismt": 75, "ips": 28, "zona": "Sur-Oriente",     "riesgo": "Bajo"},
    "Puente Alto":       {"dts": 75,  "qsd": 0.075, "vol": 0.17, "trx": 40, "stk": 400, "cap_min": 0.056, "cap_max": 0.066, "icvu": 50, "ismt": 60, "ips": 40, "zona": "Sur",             "riesgo": "Medio-Alto"},
    "Las Condes":        {"dts": 45,  "qsd": 0.04,  "vol": 0.12, "trx": 80, "stk": 200, "cap_min": 0.045, "cap_max": 0.055, "icvu": 85, "ismt": 90, "ips": 15, "zona": "Oriente",         "riesgo": "Muy Bajo"},
    "Providencia":       {"dts": 50,  "qsd": 0.045, "vol": 0.13, "trx": 70, "stk": 180, "cap_min": 0.048, "cap_max": 0.058, "icvu": 82, "ismt": 88, "ips": 18, "zona": "Centro-Oriente",  "riesgo": "Muy Bajo"},
    "Nunoa":             {"dts": 55,  "qsd": 0.05,  "vol": 0.14, "trx": 65, "stk": 250, "cap_min": 0.052, "cap_max": 0.062, "icvu": 78, "ismt": 85, "ips": 22, "zona": "Centro-Oriente",  "riesgo": "Bajo"},
    "La Reina":          {"dts": 48,  "qsd": 0.042, "vol": 0.12, "trx": 40, "stk": 150, "cap_min": 0.047, "cap_max": 0.057, "icvu": 80, "ismt": 83, "ips": 20, "zona": "Oriente",         "riesgo": "Muy Bajo"},
    "Vitacura":          {"dts": 42,  "qsd": 0.038, "vol": 0.11, "trx": 50, "stk": 120, "cap_min": 0.044, "cap_max": 0.054, "icvu": 88, "ismt": 92, "ips": 12, "zona": "Oriente",         "riesgo": "Muy Bajo"},
    "Santiago Centro":   {"dts": 58,  "qsd": 0.052, "vol": 0.15, "trx": 75, "stk": 300, "cap_min": 0.053, "cap_max": 0.063, "icvu": 75, "ismt": 80, "ips": 25, "zona": "Centro",          "riesgo": "Bajo"},
    "Quilicura":         {"dts": 72,  "qsd": 0.072, "vol": 0.16, "trx": 35, "stk": 420, "cap_min": 0.057, "cap_max": 0.067, "icvu": 48, "ismt": 58, "ips": 42, "zona": "Norte",           "riesgo": "Medio-Alto"},
    "Estacion Central":  {"dts": 62,  "qsd": 0.058, "vol": 0.15, "trx": 55, "stk": 310, "cap_min": 0.054, "cap_max": 0.064, "icvu": 60, "ismt": 68, "ips": 32, "zona": "Poniente",        "riesgo": "Medio"},
    "Padre hurtado":     {"dts": 180, "qsd": 0.11,  "vol": 0.048,"trx": 13, "stk": 700, "cap_min": 0.042, "cap_max": 0.068, "icvu": 49, "ismt": 59, "ips": 63, "zona": "Poniente",        "riesgo": "Medio"},
}


# ============================================================
# FACTORES DE CICLO ECONÓMICO
# ============================================================
FACTOR_FASE = {
    "EXPANSION":       -0.10,
    "NORMAL":           0.00,
    "DESACELERACION":   0.15,
    "CONTRACCION":      0.30,
    "CRISIS":           0.60,
}

FACTOR_ESTACIONAL = {
    "Q1": -0.02,
    "Q2":  0.00,
    "Q3":  0.01,
    "Q4": -0.01,
}

AJUSTE_LIQUIDEZ_FASE = {
    "EXPANSION":       50,
    "NORMAL":           0,
    "DESACELERACION": -30,
    "CONTRACCION":    -50,
    "CRISIS":        -100,
}

AJUSTE_BANDA_FASE = {
    "EXPANSION":      -0.005,
    "NORMAL":          0.000,
    "DESACELERACION":  0.000,
    "CONTRACCION":     0.010,
    "CRISIS":          0.015,
}


# ============================================================
# UTILIDADES
# ============================================================
def _norm_cdf(x):
    """CDF de la distribución normal estándar. Equivale a NORM.DIST(x,0,1,TRUE)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _clamp(val, lo=0, hi=1000):
    return max(lo, min(hi, val))


def lookup_comuna(comuna):
    """Busca datos de mercado por comuna. Case-insensitive, strip spaces."""
    key = comuna.strip()
    if key in DATOS_MERCADO:
        return DATOS_MERCADO[key]
    # Buscar case-insensitive
    for k, v in DATOS_MERCADO.items():
        if k.strip().lower() == key.lower():
            return v
    return None


# ============================================================
# SCORING: LIQUIDEZ (40%)
# ============================================================
def _score_dts(dts):
    """DTS Score = MAX(0, 1000 × (1 - DTS/365))"""
    return max(0.0, 1000.0 * (1.0 - dts / 365.0))


def _score_qsd(qsd):
    """QSD Score = MAX(0, 1000 × (1 - QSD/0.3))"""
    return max(0.0, 1000.0 * (1.0 - qsd / 0.3))


def _score_market_depth(md):
    """Market Depth Score = MIN(1000, MD × 5000)"""
    return min(1000.0, md * 5000.0)


def _score_velocidad(vel_meses):
    """Velocidad Score = MAX(0, MIN(1000, 1000 × (1 - vel/24)))"""
    return _clamp(1000.0 * (1.0 - vel_meses / 24.0))


def _score_pbb(pbb_ajustado):
    """PBB Score — step function."""
    p = pbb_ajustado
    if p > 0.30:  return 0
    if p > 0.25:  return 200
    if p > 0.20:  return 400
    if p > 0.175: return 550
    if p > 0.15:  return 650
    if p > 0.125: return 700
    if p > 0.10:  return 750
    if p > 0.075: return 800
    if p > 0.05:  return 850
    return 950


def calcular_liquidez(mercado, precio, buffer_pct, fase, trimestre):
    """
    Calcula score de liquidez (0-1000).

    Returns: dict con score, sub-scores, PBB, y detalle.
    """
    dts = mercado["dts"]
    qsd = mercado["qsd"]
    vol = mercado["vol"]
    trx = mercado["trx"]
    stk = mercado["stk"]

    # Derivados
    market_depth = trx / stk if stk > 0 else 0
    velocidad_stock = stk / trx if trx > 0 else 999

    # PBB
    precio_quiebre = precio * (1.0 - buffer_pct)
    if vol > 0 and precio > 0 and precio_quiebre > 0:
        pbb_base = _norm_cdf(math.log(precio_quiebre / precio) / vol)
    else:
        pbb_base = 0.0

    factor_fase = FACTOR_FASE.get(fase, 0.0)
    factor_est = FACTOR_ESTACIONAL.get(trimestre, 0.0)
    factor_combinado = factor_fase + factor_est
    pbb_ajustado = min(0.99, pbb_base * (1.0 + factor_combinado))

    # Sub-scores
    s_dts = _score_dts(dts)
    s_qsd = _score_qsd(qsd)
    s_md = _score_market_depth(market_depth)
    s_vel = _score_velocidad(velocidad_stock)
    s_pbb = _score_pbb(pbb_ajustado)

    # Score base ponderado
    score_base = (s_dts * 0.20 + s_qsd * 0.20 + s_md * 0.15
                  + s_vel * 0.10 + s_pbb * 0.35)

    ajuste = AJUSTE_LIQUIDEZ_FASE.get(fase, 0)
    score_total = _clamp(score_base + ajuste)

    # Riesgo PBB
    if pbb_ajustado > 0.30:   riesgo_pbb = "CRITICO"
    elif pbb_ajustado > 0.20: riesgo_pbb = "ALTO"
    elif pbb_ajustado > 0.15: riesgo_pbb = "MEDIO"
    elif pbb_ajustado > 0.10: riesgo_pbb = "BAJO"
    else:                     riesgo_pbb = "MUY BAJO"

    return {
        "score": round(score_total, 2),
        "ponderado": round(score_total * 0.40, 2),
        "peso": 0.40,
        "sub_scores": {
            "dts": round(s_dts, 2),
            "qsd": round(s_qsd, 2),
            "market_depth": round(s_md, 2),
            "velocidad": round(s_vel, 2),
            "pbb": s_pbb,
        },
        "pbb_base": round(pbb_base, 10),
        "pbb_ajustado": round(pbb_ajustado, 10),
        "riesgo_pbb": riesgo_pbb,
        "market_depth": round(market_depth, 6),
        "velocidad_stock": round(velocidad_stock, 2),
        "precio_quiebre": round(precio_quiebre, 2),
        "factor_combinado": round(factor_combinado, 4),
    }


# ============================================================
# SCORING: CAP RATE (30%)
# ============================================================
def calcular_cap_rate(mercado, precio, noi_mensual, fase):
    """
    Calcula score de Cap Rate (0-1000).
    """
    cap_rate = (noi_mensual * 12.0) / precio if precio > 0 else 0
    yield_neto = cap_rate  # son iguales en esta versión

    banda_min = mercado["cap_min"]
    banda_max = mercado["cap_max"]
    ajuste = AJUSTE_BANDA_FASE.get(fase, 0.0)
    banda_min_adj = banda_min + ajuste
    banda_max_adj = banda_max + ajuste

    # Posición en banda
    if cap_rate < banda_min_adj:
        posicion = "BAJO"
    elif cap_rate > banda_max_adj:
        posicion = "ALTO"
    else:
        posicion = "DENTRO"

    # Score — step function
    if cap_rate >= banda_max_adj:
        score = 1000
    elif cap_rate >= (banda_min_adj + banda_max_adj) / 2:
        score = 900
    elif cap_rate >= banda_min_adj:
        score = 800
    elif cap_rate >= banda_min_adj * 0.95:
        score = 700
    elif cap_rate >= banda_min_adj * 0.90:
        score = 500
    elif cap_rate >= banda_min_adj * 0.85:
        score = 400
    else:
        score = 0

    return {
        "score": score,
        "ponderado": round(score * 0.30, 2),
        "peso": 0.30,
        "cap_rate": round(cap_rate, 10),
        "yield_neto": round(yield_neto, 10),
        "banda_min": banda_min,
        "banda_max": banda_max,
        "banda_min_adj": round(banda_min_adj, 6),
        "banda_max_adj": round(banda_max_adj, 6),
        "posicion": posicion,
    }


# ============================================================
# SCORING: ESTRUCTURAL (20%)
# ============================================================
def calcular_estructural(estado_fisico, cumplimiento_legal, riesgo_sismico, antiguedad_anos):
    """
    Score Estructural = AVERAGE(estado, legal, sísmico) × 100 × factor_antigüedad.
    Factor antigüedad = MAX(0.7, 1 - antigüedad/50).
    """
    factor_ant = max(0.7, 1.0 - antiguedad_anos / 50.0)
    score_base = ((estado_fisico + cumplimiento_legal + riesgo_sismico) / 3.0) * 100.0
    score_adj = score_base * factor_ant

    return {
        "score": round(score_adj, 2),
        "ponderado": round(score_adj * 0.20, 2),
        "peso": 0.20,
        "score_base": round(score_base, 2),
        "factor_antiguedad": round(factor_ant, 4),
        "inputs": {
            "estado_fisico": estado_fisico,
            "cumplimiento_legal": cumplimiento_legal,
            "riesgo_sismico": riesgo_sismico,
            "antiguedad_anos": antiguedad_anos,
        },
    }


# ============================================================
# SCORING: LOCACIÓN (5%)
# ============================================================
def calcular_locacion(mercado, conectividad, servicios):
    """
    Score Locación = ICVU×0.4 + ISMT×0.3 + (100-IPS)×0.2 + Conectividad×10×0.05 + Servicios×10×0.05
    Dashboard multiplica por 10 para escala 0-1000.
    """
    icvu = mercado["icvu"]
    ismt = mercado["ismt"]
    ips = mercado["ips"]

    score_base = (icvu * 0.40
                  + ismt * 0.30
                  + (100 - ips) * 0.20
                  + conectividad * 10 * 0.05
                  + servicios * 10 * 0.05)

    # Escala 0-1000 (Dashboard multiplica por 10)
    score_1000 = score_base * 10

    return {
        "score": round(score_1000, 2),
        "ponderado": round(score_1000 * 0.05, 2),
        "peso": 0.05,
        "score_base": round(score_base, 2),
        "inputs": {
            "icvu": icvu,
            "ismt": ismt,
            "ips": ips,
            "conectividad": conectividad,
            "servicios": servicios,
        },
    }


# ============================================================
# SCORING: TIPOLOGÍA (5%)
# ============================================================
def _score_asequibilidad(gasto_ingreso):
    """Score de asequibilidad — step function sobre ratio gasto/ingreso."""
    r = gasto_ingreso
    if r < 0.30:  return 950
    if r < 0.35:  return 850
    if r < 0.40:  return 700
    if r < 0.45:  return 500
    return 300


def calcular_tipologia(renta_mensual_uf, renta_cliente_uf, velocidad_absorcion, demanda_zona):
    """
    Score Tipología = Asequibilidad×0.6 + Velocidad×100×0.2 + Demanda×100×0.2
    """
    gasto_ingreso = renta_mensual_uf / renta_cliente_uf if renta_cliente_uf > 0 else 1.0
    s_aseq = _score_asequibilidad(gasto_ingreso)

    score = s_aseq * 0.60 + velocidad_absorcion * 100 * 0.20 + demanda_zona * 100 * 0.20

    return {
        "score": round(score, 2),
        "ponderado": round(score * 0.05, 2),
        "peso": 0.05,
        "gasto_ingreso": round(gasto_ingreso, 6),
        "score_asequibilidad": s_aseq,
        "inputs": {
            "renta_mensual_uf": renta_mensual_uf,
            "renta_cliente_uf": renta_cliente_uf,
            "velocidad_absorcion": velocidad_absorcion,
            "demanda_zona": demanda_zona,
        },
    }


# ============================================================
# GATEKEEPERS (criterios eliminatorios)
# ============================================================
def evaluar_gatekeepers(pbb_ajustado, cap_rate, cap_min_adj, noi_mensual):
    """
    4 criterios eliminatorios del Asset Score.
    """
    gates = {
        "pbb_ok":      pbb_ajustado < 0.30,
        "cap_rate_ok": cap_rate >= cap_min_adj * 0.90,
        "noi_ok":      noi_mensual > 0,
    }
    gates["all_pass"] = all(gates.values())

    detalle = []
    if not gates["pbb_ok"]:
        detalle.append(f"PBB {pbb_ajustado*100:.2f}% >= 30% — RIESGO CRÍTICO")
    if not gates["cap_rate_ok"]:
        detalle.append(f"Cap Rate {cap_rate*100:.2f}% < mínimo ajustado × 0.9 ({cap_min_adj*0.9*100:.2f}%)")
    if not gates["noi_ok"]:
        detalle.append(f"NOI {noi_mensual:.2f} UF <= 0 — FLUJO NEGATIVO")

    gates["detalle"] = detalle
    return gates


# ============================================================
# VEREDICTO Y ALERTAS
# ============================================================
def _decision(score):
    if score >= 750: return "APROBADO"
    if score >= 700: return "APROBADO CON CONDICIONES"
    if score >= 600: return "ANALISIS DETALLADO"
    return "RECHAZADO"


def _nivel_confianza(score):
    if score >= 800: return "MUY ALTO"
    if score >= 700: return "ALTO"
    if score >= 600: return "MEDIO"
    if score >= 500: return "BAJO"
    return "MUY BAJO"


def _percentil(score):
    if score > 800: return 95
    if score > 750: return 85
    if score > 700: return 70
    if score > 650: return 50
    if score > 600: return 30
    if score > 550: return 15
    return 5


def _alerta(pbb_ajustado, cap_rate, banda_min_adj, score_liquidez):
    if pbb_ajustado > 0.20:
        return "PBB ALTO: Revisar precio"
    if cap_rate < banda_min_adj:
        return "CAP RATE BAJO: Renegociar"
    if score_liquidez < 650:
        return "LIQUIDEZ LIMITADA"
    return "Sin alertas críticas"


def _recomendacion(score):
    if score >= 750: return "Proceder con adquisición"
    if score >= 600: return "Negociar mejores términos"
    if score >= 500: return "Buscar alternativas"
    return "No proceder"


def _precio_sugerido(score, precio):
    return round(precio * 0.9, 2) if score < 700 else precio


def _buffer_sugerido(pbb_ajustado):
    if pbb_ajustado > 0.15: return 0.20
    if pbb_ajustado > 0.10: return 0.15
    return 0.10


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def run_asset_score(activo):
    """
    Ejecuta el Asset Credit Score completo.

    Args:
        activo: dict con campos del activo (ver estructura en plan técnico)

    Returns:
        dict con score total, dimensiones, gatekeepers, veredicto, alertas, metadata.
        Retorna error si la comuna no se encuentra en DATOS_MERCADO.
    """
    # --- Lookup comuna ---
    mercado = lookup_comuna(activo["comuna"])
    if mercado is None:
        return {
            "error": f"Comuna '{activo['comuna']}' no encontrada en DATOS_MERCADO",
            "comunas_disponibles": list(DATOS_MERCADO.keys()),
        }

    # --- Inputs ---
    precio = activo["precio_uf"]
    buffer_pct = activo.get("buffer_pct", 0.15)
    renta = activo["renta_mensual_uf"]
    opex = activo["opex_mensual_uf"]
    fase = activo.get("fase_economica", "NORMAL")
    trimestre = activo.get("trimestre", "Q1")

    # Derivados
    precio_buffer = precio * (1.0 + buffer_pct)
    noi = renta - opex

    # --- 5 dimensiones ---
    liquidez = calcular_liquidez(mercado, precio, buffer_pct, fase, trimestre)
    cap_rate = calcular_cap_rate(mercado, precio, noi, fase)
    estructural = calcular_estructural(
        activo["estado_fisico"],
        activo["cumplimiento_legal"],
        activo["riesgo_sismico"],
        activo["antiguedad_anos"],
    )
    locacion = calcular_locacion(
        mercado,
        activo["conectividad"],
        activo["servicios"],
    )
    tipologia = calcular_tipologia(
        renta,
        activo["renta_cliente_uf"],
        activo["velocidad_absorcion"],
        activo["demanda_zona"],
    )

    # --- Score total ---
    score_total = (liquidez["ponderado"]
                   + cap_rate["ponderado"]
                   + estructural["ponderado"]
                   + locacion["ponderado"]
                   + tipologia["ponderado"])
    score_total = round(score_total, 2)

    # --- Gatekeepers ---
    gatekeepers = evaluar_gatekeepers(
        liquidez["pbb_ajustado"],
        cap_rate["cap_rate"],
        cap_rate["banda_min_adj"],
        noi,
    )

    # --- Veredicto ---
    decision = _decision(score_total)
    nivel = _nivel_confianza(score_total)
    percentil = _percentil(score_total)
    alerta = _alerta(
        liquidez["pbb_ajustado"],
        cap_rate["cap_rate"],
        cap_rate["banda_min_adj"],
        liquidez["score"],
    )
    recomendacion = _recomendacion(score_total)
    precio_sug = _precio_sugerido(score_total, precio)
    buffer_sug = _buffer_sugerido(liquidez["pbb_ajustado"])

    return {
        "total": score_total,
        "decision": decision,
        "nivel_confianza": nivel,
        "percentil": percentil,
        "gatekeepers": gatekeepers,
        "alerta": alerta,
        "recomendacion": recomendacion,
        "precio_sugerido_uf": precio_sug,
        "buffer_sugerido_pct": buffer_sug,
        "dimensiones": {
            "liquidez": liquidez,
            "cap_rate": cap_rate,
            "estructural": estructural,
            "locacion": locacion,
            "tipologia": tipologia,
        },
        "inputs_derivados": {
            "precio_con_buffer": round(precio_buffer, 2),
            "noi_mensual": round(noi, 2),
            "cap_rate_anual": cap_rate["cap_rate"],
        },
        "metadata": {
            "engine": "asset_credit_score_v2.2",
            "timestamp": datetime.now().isoformat(),
            "comuna": activo["comuna"],
            "fase_economica": fase,
            "trimestre": trimestre,
            "n_comunas_disponibles": len(DATOS_MERCADO),
        },
    }


# ============================================================
# VALIDACIÓN — CASO MONTECINOS
# ============================================================
if __name__ == "__main__":
    activo_montecinos = {
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

    resultado = run_asset_score(activo_montecinos)

    if "error" in resultado:
        print(f"ERROR: {resultado['error']}")
    else:
        print("=" * 70)
        print(f"ASSET CREDIT SCORE v2.2")
        print("=" * 70)
        print(f"Activo: {activo_montecinos['direccion']}, {activo_montecinos['comuna']}")
        print(f"Score Total: {resultado['total']}")
        print(f"Decisión: {resultado['decision']}")
        print(f"Confianza: {resultado['nivel_confianza']}")
        print(f"Percentil: {resultado['percentil']}")
        print()
        print("DIMENSIONES:")
        for dim, data in resultado["dimensiones"].items():
            print(f"  {dim:<14} Score: {data['score']:>7.2f}  Pond: {data['ponderado']:>7.2f}  ({data['peso']*100:.0f}%)")
        print()
        print("GATEKEEPERS:")
        for k, v in resultado["gatekeepers"].items():
            if k not in ("all_pass", "detalle"):
                print(f"  {k}: {'✓' if v else '✗'}")
        print(f"  → {'Todos PASS' if resultado['gatekeepers']['all_pass'] else '⚠ FALLA'}")
        print()
        print(f"Alerta: {resultado['alerta']}")
        print(f"Recomendación: {resultado['recomendacion']}")

        # Validación contra Excel
        print()
        print("=" * 70)
        print("VALIDACIÓN vs Excel Montecinos (Score esperado: 704.30)")
        print("=" * 70)
        diff = abs(resultado["total"] - 704.30)
        if diff < 1.0:
            print(f"✓ PASS — Score: {resultado['total']} (diff: {diff:.2f})")
        else:
            print(f"✗ FAIL — Score: {resultado['total']} vs esperado 704.30 (diff: {diff:.2f})")
            print("  Revisar sub-scores:")
            print(f"  Liquidez: {resultado['dimensiones']['liquidez']['score']} (esperado: ~574.47)")
            print(f"  Cap Rate: {resultado['dimensiones']['cap_rate']['score']} (esperado: 800)")
            print(f"  Estructural: {resultado['dimensiones']['estructural']['score']} (esperado: ~933.33)")
            print(f"  Locación: {resultado['dimensiones']['locacion']['score']} (esperado: ~497)")
            print(f"  Tipología: {resultado['dimensiones']['tipologia']['score']} (esperado: ~460)")
