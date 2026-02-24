"""
PROPIO — Credit Score v3.0
==========================
Motor determinístico de scoring de cliente.
Fuente: Motor de Riesgo Cliente + Activo 19.12.xlsm

Componentes:
  1. Renta Depurada (Dependiente + Independiente)
  2. Score SINACOFI → PD + Factor RBI
  3. Endeudamiento CMF
  4. 4 Verticales (Política, Score, Capacidad de Pago, Producto)
  5. Credit Score = avg(4 verticales) × 250
  6. Matriz Credit × Asset → Nivel → Decisión

Dependencias: solo math + datetime (stdlib).
"""

import math
from datetime import datetime


# ============================================================
# TABLAS DE PARÁMETROS (Motor 19.12 → Parámetros Modelo)
# ============================================================

# Score SINACOFI → PD, Tasa, límites por tier
SCORE_PD_TABLE = [
    # (score_min, score_max, pd, tasa, cuota_max, egreso_lt3m, egreso_gt3m, leverage)
    (1,   124,  0.8316, 0.087, 0.15,   0.55, 0.60, 60),
    (125, 357,  0.2546, 0.086, 0.15,   0.55, 0.60, 60),
    (358, 487,  0.1001, 0.085, 0.15,   0.55, 0.60, 60),
    (488, 534,  0.0500, 0.084, 0.25,   0.55, 0.60, 60),
    (535, 620,  0.0500, 0.083, 0.25,   0.55, 0.60, 60),
    (621, 716,  0.0407, 0.082, 0.2925, 0.592, 0.621, 65),
    (717, 797,  0.0347, 0.081, 0.3299, 0.620, 0.635, 65),
    (798, 999,  0.0281, 0.080, 0.35,   0.65, 0.65, 65),
]

# Factor RBI → ajuste de PD
FACTOR_RBI_TABLE = [
    # (rbi_min, factor)
    (95, 0.85),
    (85, 0.90),
    (75, 0.95),
    (65, 1.00),
    (0,  1.15),
]

# Factor CLP para depuración de renta (dependientes)
# (clp_min, clp_max, factor)
FACTOR_RENTA_CLP = [
    (0,       938_816,   0.800),
    (938_817, 2_086_259, 0.788),
    (2_086_260, 3_477_099, 0.795),
    (3_477_100, 4_867_939, 0.822),
    (4_867_940, 6_258_779, 0.820),
    (6_258_780, 8_345_039, 0.799),
    (8_345_040, 999_999_999, 0.768),
]

# Castigos para independientes/rentistas
CASTIGO_BH = 0.20
CASTIGO_DEP_PLAZO = 0.20
CASTIGO_RETIROS_DAI = 0.20
CASTIGO_RENTA_ATRIBUIDA = 0.50

# Topes legales
MAX_COLACION = 100_000   # CLP
MAX_MOVILIZACION = 50_000  # CLP

# Umbrales variabilidad
UMBRAL_VARIABILIDAD = 0.40

# Endeudamiento CMF — factores de conversión saldo → egreso mensual
CMF_FACTOR_DIVIDENDO = 0.007
CMF_FACTOR_CONSUMO = 0.035
CMF_FACTOR_AJUSTE_LINEA = 0.35
CMF_FACTOR_EGRESO_LINEA = 0.035

# Montos crédito
MONTO_MIN_CREDITO = 1_000_000  # CLP
MONTO_MAX_CREDITO = 31_200_000  # CLP

# ============================================================
# UMBRALES DE ATRIBUCIÓN POR VERTICAL Y NIVEL
# Fuente: Motor 19.12 → Parámetros Modelo rows 70-95
#
# Estructura: {cod: {direction, thresholds: {lvl: valor}}}
# direction: "min" = valor debe ser >= threshold para pasar
#            "max" = valor debe ser <= threshold para pasar
#            "flag" = booleano especial (extranjero)
# ============================================================

POLITICA_CRITERIA = {
    "renta_min": {
        "direction": "min",
        "thresholds": {4: 1_500_000, 3: 1_200_000, 2: 0, 1: 0},
    },
    "extranjero_sin_residencia": {
        "direction": "flag_block",  # True = bloquea niveles 4 y 3
        "thresholds": {4: False, 3: False, 2: True, 1: True},
        # Si es extranjero sin residencia: lvl4=FAIL, lvl3=FAIL, lvl2=OK, lvl1=OK
    },
    "edad": {
        "direction": "range",  # min y max
        "thresholds": {
            4: {"min": 24, "max": 60},
            3: {"min": 24, "max": 65},
            2: {"min": 18, "max": 100},
            1: {"min": 18, "max": 100},
        },
    },
    "antiguedad_laboral_meses": {
        "direction": "min",
        "thresholds": {4: 12, 3: 12, 2: 6, 1: 0},
    },
    "deuda_vencida": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
    "deuda_castigada": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
    "mora_sf": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
    "protestos": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
    "mora_casas_comerciales": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
    "quiebras": {
        "direction": "max",
        "thresholds": {4: 0, 3: 0, 2: 1_000, 1: 1_000},
    },
    "infracciones_laborales": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
    "deterioro_propio": {
        "direction": "max",
        "thresholds": {4: 0, 3: 10_000, 2: 100_000_000, 1: 100_000_000},
    },
}

SCORE_CRITERIA = {
    "pd_ajustada": {
        "direction": "max",
        "thresholds": {4: 0.05, 3: 0.07, 2: 1.0, 1: 1.0},
    },
}

# Capacidad de Pago: depende de si renta < 3M o >= 3M
# Se selecciona el set correcto en runtime
CAPACIDAD_PAGO_CRITERIA_LT3M = {
    "egreso_renta": {
        "direction": "max",
        "thresholds": {4: 0.55, 3: 0.57, 2: 0.65, 1: 1.0},
    },
    "veces_renta": {
        "direction": "max",
        "thresholds": {4: 8, 3: 9, 2: 100, 1: 100},
    },
    "leverage": {
        "direction": "max",
        "thresholds": {4: 65, 3: 62, 2: 70, 1: 100},
    },
}

CAPACIDAD_PAGO_CRITERIA_GT3M = {
    "egreso_renta": {
        "direction": "max",
        "thresholds": {4: 0.60, 3: 0.62, 2: 0.65, 1: 1.0},
    },
    "veces_renta": {
        "direction": "max",
        "thresholds": {4: 8, 3: 9, 2: 100, 1: 100},
    },
    "leverage": {
        "direction": "max",
        "thresholds": {4: 65, 3: 62, 2: 70, 1: 100},
    },
}

PRODUCTO_CRITERIA_LT3M = {
    "valor_propiedad": {
        "direction": "min",
        "thresholds": {4: 60_000_000, 3: 48_000_000, 2: 0, 1: 0},
    },
    "pie_pct": {
        "direction": "min",
        "thresholds": {4: 0.07, 3: 0.06, 2: 0.0, 1: 0.0},
    },
    "edad_max_producto": {
        "direction": "max",
        "thresholds": {4: 60, 3: 65, 2: 100, 1: 100},
    },
}

PRODUCTO_CRITERIA_GT3M = {
    "valor_propiedad": {
        "direction": "min",
        "thresholds": {4: 60_000_000, 3: 48_000_000, 2: 0, 1: 0},
    },
    "pie_pct": {
        "direction": "min",
        "thresholds": {4: 0.07, 3: 0.06, 2: 0.0, 1: 0.0},
    },
    "edad_max_producto": {
        "direction": "max",
        "thresholds": {4: 60, 3: 65, 2: 100, 1: 100},
    },
}

# ============================================================
# MATRIZ: Asset Score × Credit Score → (Rating, Nivel)
# Fuente: Motor 19.12 → Tablas Ref
# Filas: Asset Score bands, Columnas: Credit Score bands
# ============================================================
MATRIX = {
    # (asset_band, credit_band): (rating, nivel)
    # asset_band: 4=>800, 3=700-800, 2=600-700, 1=500-600, 0=<500
    # credit_band: 4=>875, 3=750-875, 2=625-750, 1=500-625, 0=<500
    (4, 4): ("AAA", 4),
    (4, 3): ("AA+", 4),
    (4, 2): ("AA",  3),
    (4, 1): ("A+",  2),
    (4, 0): ("A",   1),
    (3, 4): ("AA+", 4),
    (3, 3): ("AA",  3),
    (3, 2): ("A+",  3),
    (3, 1): ("A",   2),
    (3, 0): ("BBB", 1),
    (2, 4): ("AA",  3),
    (2, 3): ("A+",  3),
    (2, 2): ("A",   2),
    (2, 1): ("BBB", 1),
    (2, 0): ("BB",  1),
    (1, 4): ("A+",  2),
    (1, 3): ("A",   2),
    (1, 2): ("BBB", 1),
    (1, 1): ("BB",  1),
    (1, 0): ("B",   0),
    (0, 4): ("A",   1),
    (0, 3): ("BBB", 1),
    (0, 2): ("BB",  0),
    (0, 1): ("B",   0),
    (0, 0): ("CC",  0),
}

NIVEL_DECISION = {
    4: "Aprobación Preferente",
    3: "Aprobación Estándar",
    2: "Aprobación con Condiciones",
    1: "Análisis Detallado",
    0: "Rechazo",
}


# ============================================================
# 1. RENTA DEPURADA
# ============================================================
def _get_factor_renta(total_haberes_clp):
    """Busca el factor de depuración según tramo CLP."""
    for lo, hi, factor in FACTOR_RENTA_CLP:
        if lo <= total_haberes_clp <= hi:
            return factor
    return FACTOR_RENTA_CLP[-1][2]  # fallback al último tramo


def calcular_renta_dependiente(liquidaciones):
    """
    Calcula renta depurada para dependientes.

    Args:
        liquidaciones: lista de 3 dicts, cada uno con:
            total_haberes: int (CLP)
            colacion: int (CLP, default 0)
            movilizacion: int (CLP, default 0)
            retencion_judicial: int (CLP, default 0)

    Returns:
        dict con renta_depurada, variabilidad, detalle por mes
    """
    if not liquidaciones or len(liquidaciones) < 3:
        return {"error": "Se requieren 3 liquidaciones", "renta_depurada": 0}

    rentas_mes = []
    retenciones = []
    detalle = []

    for i, liq in enumerate(liquidaciones[:3]):
        th = liq["total_haberes"]
        col = min(liq.get("colacion", 0), MAX_COLACION)
        mov = min(liq.get("movilizacion", 0), MAX_MOVILIZACION)
        ret = liq.get("retencion_judicial", 0)

        factor = _get_factor_renta(th)
        renta_dep_mes = th * factor + col + mov - ret

        rentas_mes.append(renta_dep_mes)
        retenciones.append(ret)
        detalle.append({
            "mes": i + 1,
            "total_haberes": th,
            "factor": factor,
            "colacion": col,
            "movilizacion": mov,
            "retencion_judicial": ret,
            "renta_depurada_mes": round(renta_dep_mes),
        })

    # Variabilidad
    sorted_rentas = sorted(rentas_mes)
    minimo = sorted_rentas[0]
    segundo_menor = sorted_rentas[1]
    maximo = sorted_rentas[2]

    prom_2_bajos = (minimo + segundo_menor) / 2.0
    variabilidad = (maximo / prom_2_bajos - 1.0) if prom_2_bajos > 0 else 0.0

    # Renta final
    if variabilidad < UMBRAL_VARIABILIDAD:
        renta_base = sum(rentas_mes) / 3.0
    else:
        renta_base = prom_2_bajos

    prom_retencion = sum(retenciones) / 3.0
    renta_final = renta_base - prom_retencion

    return {
        "renta_depurada": round(renta_final),
        "renta_base": round(renta_base),
        "variabilidad": round(variabilidad, 4),
        "variabilidad_alta": variabilidad >= UMBRAL_VARIABILIDAD,
        "metodo": "promedio_3" if variabilidad < UMBRAL_VARIABILIDAD else "promedio_2_bajos",
        "promedio_retencion": round(prom_retencion),
        "detalle_meses": detalle,
    }


def calcular_renta_independiente_bh(boletas):
    """
    Calcula renta depurada para independientes con boletas de honorarios.

    Args:
        boletas: lista de montos mensuales BH (CLP), idealmente 4+

    Returns:
        dict con renta_depurada_bh, castigo aplicado
    """
    if not boletas:
        return {"error": "Sin boletas", "renta_depurada_bh": 0}

    n = len(boletas)
    sorted_b = sorted(boletas)

    if n < 4:
        # Menos de 4 meses: usar promedio de lo que hay
        ingreso = sum(boletas) / n
        metodo = f"promedio_{n}_meses"
    else:
        prom_3_bajos = sum(sorted_b[:3]) / 3.0
        promedio = sum(boletas) / n
        maximo = sorted_b[-1]
        variabilidad = (maximo / prom_3_bajos - 1.0) if prom_3_bajos > 0 else 0.0

        if variabilidad < UMBRAL_VARIABILIDAD:
            ingreso = promedio
            metodo = "promedio"
        else:
            ingreso = prom_3_bajos
            metodo = "promedio_3_bajos"

    renta_bh = ingreso * (1.0 - CASTIGO_BH)

    return {
        "renta_depurada_bh": round(renta_bh),
        "ingreso_bruto": round(ingreso),
        "castigo_bh": CASTIGO_BH,
        "n_meses": n,
        "metodo": metodo,
    }


def calcular_renta_independiente_dai(cod110, cod850, cod617, cod304, cod158):
    """
    Calcula renta DAI desde declaración de impuestos.
    Fórmula: ((cod110 + cod850 - cod617) - (MAX(0, cod304) × ratio_158)) / 12

    Args:
        cod110: Honorarios brutos
        cod850: Otros ingresos
        cod617: Gastos deducibles
        cod304: Impuesto
        cod158: Base imponible
    """
    base = cod110 + cod850 - cod617
    ratio_158 = base / cod158 if cod158 > 0 else 0
    impuesto_proporcional = max(0, cod304) * ratio_158
    renta_anual = base - impuesto_proporcional
    renta_mensual = renta_anual / 12.0

    return {
        "renta_dai_mensual": round(renta_mensual),
        "renta_dai_anual": round(renta_anual),
    }


def merge_bh_dai(renta_bh, renta_dai):
    """
    Si DAI > 0 y BH/DAI > 1.4, promedia ambos.
    """
    if renta_dai <= 0:
        return renta_bh

    ratio = renta_bh / renta_dai if renta_dai > 0 else 999
    if ratio > 1.4:
        return round((renta_bh + renta_dai) / 2.0)
    return renta_bh


def calcular_renta_total(dep_liq=0, bh=0, ppm=0, renta_fija=0,
                         dep_plazo=0, retiros_dai=0, renta_atribuida=0):
    """
    Renta Total = Dep + max(BH, PPM) + Fija + DepPlazo×(1-cast) + Retiros×(1-cast) + Atribuida×(1-cast)
    """
    independiente = max(bh, ppm)
    dp_neto = dep_plazo * (1.0 - CASTIGO_DEP_PLAZO)
    ret_neto = retiros_dai * (1.0 - CASTIGO_RETIROS_DAI)
    attr_neto = renta_atribuida * (1.0 - CASTIGO_RENTA_ATRIBUIDA)

    total = dep_liq + independiente + renta_fija + dp_neto + ret_neto + attr_neto

    return {
        "renta_total": round(total),
        "componentes": {
            "dependiente": round(dep_liq),
            "independiente": round(independiente),
            "fuente_independiente": "BH" if bh >= ppm else "PPM",
            "renta_fija": round(renta_fija),
            "dep_plazo_neto": round(dp_neto),
            "retiros_dai_neto": round(ret_neto),
            "renta_atribuida_neta": round(attr_neto),
        },
    }


# ============================================================
# 2. SCORE SINACOFI → PD + FACTOR RBI
# ============================================================
def get_pd_from_score(score_sinacofi):
    """Mapea score SINACOFI a PD y parámetros del tier."""
    for s_min, s_max, pd, tasa, cuota_max, e_lt3m, e_gt3m, lev in SCORE_PD_TABLE:
        if s_min <= score_sinacofi <= s_max:
            return {
                "pd_base": pd,
                "tasa": tasa,
                "cuota_max_pct": cuota_max,
                "egreso_max_lt3m": e_lt3m,
                "egreso_max_gt3m": e_gt3m,
                "leverage_max": lev,
                "tier": f"{s_min}-{s_max}",
            }
    # Fuera de rango
    return {
        "pd_base": 0.8316,
        "tasa": 0.087,
        "cuota_max_pct": 0.15,
        "egreso_max_lt3m": 0.55,
        "egreso_max_gt3m": 0.60,
        "leverage_max": 60,
        "tier": "fuera_rango",
    }


def get_factor_rbi(rbi):
    """Retorna factor de ajuste según RBI."""
    if rbi is None or rbi == 0:
        return 1.0  # Sin RBI → sin ajuste
    for rbi_min, factor in FACTOR_RBI_TABLE:
        if rbi >= rbi_min:
            return factor
    return 1.15  # fallback


def calcular_pd_ajustada(score_sinacofi, rbi=0):
    """
    PD ajustada = PD_base × Factor_RBI
    Si RBI = 0 o None, no se ajusta.
    """
    tier = get_pd_from_score(score_sinacofi)
    rbi = rbi or 0
    factor = get_factor_rbi(rbi)
    pd_ajustada = tier["pd_base"] * factor if rbi > 0 else tier["pd_base"]

    return {
        "pd_base": tier["pd_base"],
        "factor_rbi": factor,
        "pd_ajustada": round(pd_ajustada, 6),
        "rbi": rbi,
        "score_sinacofi": score_sinacofi,
        "tier": tier["tier"],
        "tasa": tier["tasa"],
    }


# ============================================================
# 3. ENDEUDAMIENTO CMF
# ============================================================
def calcular_endeudamiento_cmf(saldo_hipotecario=0, saldo_consumo=0,
                                linea_credito=0, saldo_linea_credito=0):
    """
    Estima egreso mensual desde datos CMF.
    Egreso = Saldo_hip × 0.007 + Saldo_consumo × 0.035
             + Linea × 0.35 + Saldo_linea × 0.035
    """
    e_hip = saldo_hipotecario * CMF_FACTOR_DIVIDENDO
    e_consumo = saldo_consumo * CMF_FACTOR_CONSUMO
    e_ajuste_linea = linea_credito * CMF_FACTOR_AJUSTE_LINEA
    e_egreso_linea = saldo_linea_credito * CMF_FACTOR_EGRESO_LINEA

    total = e_hip + e_consumo + e_ajuste_linea + e_egreso_linea

    return {
        "egreso_mensual_estimado": round(total),
        "detalle": {
            "hipotecario": round(e_hip),
            "consumo": round(e_consumo),
            "ajuste_linea": round(e_ajuste_linea),
            "egreso_linea": round(e_egreso_linea),
        },
    }


# ============================================================
# 4. EVALUACIÓN DE VERTICALES
# ============================================================
def _evaluar_criterio_nivel(valor, criterio, nivel):
    """
    Evalúa si un valor pasa un criterio en un nivel dado.

    Returns: bool
    """
    direction = criterio["direction"]
    threshold = criterio["thresholds"].get(nivel)

    if threshold is None:
        return True  # sin umbral = pasa

    if direction == "min":
        return valor >= threshold
    elif direction == "max":
        return valor <= threshold
    elif direction == "flag_block":
        # True en thresholds = permite, False = bloquea
        # valor es True si es extranjero sin residencia
        if valor:  # es extranjero
            return threshold  # True=OK, False=bloqueado
        return True  # no es extranjero → siempre pasa
    elif direction == "range":
        return threshold["min"] <= valor <= threshold["max"]

    return False


def _calcular_vertical(criteria_def, valores):
    """
    Evalúa una vertical completa.
    Score = nivel más alto donde TODOS los criterios pasan.

    Args:
        criteria_def: dict de {nombre: {direction, thresholds}}
        valores: dict de {nombre: valor}

    Returns:
        dict con score (1-4), detalle por criterio y nivel
    """
    detalle = {}

    for nombre, criterio in criteria_def.items():
        valor = valores.get(nombre, 0)
        resultados_nivel = {}
        for lvl in [4, 3, 2, 1]:
            resultados_nivel[lvl] = _evaluar_criterio_nivel(valor, criterio, lvl)
        detalle[nombre] = {
            "valor": valor,
            "niveles": resultados_nivel,
        }

    # Score = nivel más alto donde ALL pasan
    score = 1  # mínimo garantizado (level 1 siempre pasa por diseño)
    for lvl in [4, 3, 2, 1]:
        all_pass = all(
            detalle[nombre]["niveles"][lvl]
            for nombre in criteria_def
        )
        if all_pass:
            score = lvl
            break

    return {
        "score": score,
        "detalle": detalle,
    }


def evaluar_politica(datos):
    """
    Vertical 1: Política (12 criterios).

    Args:
        datos: dict con renta_depurada (CLP), extranjero_sin_residencia (bool),
               edad, antiguedad_laboral_meses, deuda_vencida, deuda_castigada,
               mora_sf, protestos, mora_casas_comerciales, quiebras,
               infracciones_laborales, deterioro_propio
    """
    valores = {
        "renta_min": datos.get("renta_depurada", 0),
        "extranjero_sin_residencia": datos.get("extranjero_sin_residencia", False),
        "edad": datos.get("edad", 0),
        "antiguedad_laboral_meses": datos.get("antiguedad_laboral_meses", 0),
        "deuda_vencida": datos.get("deuda_vencida", 0),
        "deuda_castigada": datos.get("deuda_castigada", 0),
        "mora_sf": datos.get("mora_sf", 0),
        "protestos": datos.get("protestos", 0),
        "mora_casas_comerciales": datos.get("mora_casas_comerciales", 0),
        "quiebras": datos.get("quiebras", 0),
        "infracciones_laborales": datos.get("infracciones_laborales", 0),
        "deterioro_propio": datos.get("deterioro_propio", 0),
    }
    return _calcular_vertical(POLITICA_CRITERIA, valores)


def evaluar_score(pd_ajustada):
    """Vertical 2: Score SINACOFI (1 criterio: PD ajustada)."""
    return _calcular_vertical(SCORE_CRITERIA, {"pd_ajustada": pd_ajustada})


def evaluar_capacidad_pago(datos, renta_lt_3m=True):
    """
    Vertical 3: Capacidad de Pago (3 criterios).

    Args:
        datos: dict con egreso_renta, veces_renta, leverage
        renta_lt_3m: True si renta < 3M CLP
    """
    criteria = CAPACIDAD_PAGO_CRITERIA_LT3M if renta_lt_3m else CAPACIDAD_PAGO_CRITERIA_GT3M
    return _calcular_vertical(criteria, datos)


def evaluar_producto(datos, renta_lt_3m=True):
    """
    Vertical 4: Producto (3 criterios).

    Args:
        datos: dict con valor_propiedad (CLP), pie_pct, edad_max_producto
        renta_lt_3m: True si renta < 3M CLP
    """
    criteria = PRODUCTO_CRITERIA_LT3M if renta_lt_3m else PRODUCTO_CRITERIA_GT3M
    return _calcular_vertical(criteria, datos)


# ============================================================
# 5. CREDIT SCORE
# ============================================================
def calcular_credit_score(politica_score, score_score, cap_pago_score, producto_score):
    """
    Credit Score = avg(4 verticales) × 250
    Rango: 250 (peor) a 1000 (mejor)
    """
    promedio = (politica_score + score_score + cap_pago_score + producto_score) / 4.0
    credit_score = promedio * 250.0

    return {
        "credit_score": round(credit_score, 2),
        "promedio_verticales": round(promedio, 4),
        "verticales": {
            "politica": politica_score,
            "score": score_score,
            "capacidad_pago": cap_pago_score,
            "producto": producto_score,
        },
    }


# ============================================================
# 6. MATRIZ CREDIT × ASSET → NIVEL
# ============================================================
def _score_to_band(score, breakpoints):
    """Convierte un score numérico a banda (0-4)."""
    # breakpoints = [(threshold, band), ...] descendente
    for threshold, band in breakpoints:
        if score > threshold:
            return band
    return 0


def lookup_matrix(credit_score, asset_score):
    """
    Cruza Credit Score × Asset Score → Rating + Nivel + Decisión.

    Args:
        credit_score: 250-1000
        asset_score: 0-1000
    """
    credit_bands = [(875, 4), (750, 3), (625, 2), (500, 1)]
    asset_bands = [(800, 4), (700, 3), (600, 2), (500, 1)]

    credit_band = _score_to_band(credit_score, credit_bands)
    asset_band = _score_to_band(asset_score, asset_bands)

    rating, nivel = MATRIX.get((asset_band, credit_band), ("CC", 0))
    decision = NIVEL_DECISION.get(nivel, "Rechazo")

    return {
        "rating": rating,
        "nivel": nivel,
        "decision": decision,
        "credit_band": credit_band,
        "asset_band": asset_band,
        "credit_score": credit_score,
        "asset_score": asset_score,
    }


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def run_credit_score(cliente):
    """
    Ejecuta el Credit Score completo.

    Args:
        cliente: dict con:
            # Renta
            tipo_renta: "dependiente" | "independiente" | "mixto"
            liquidaciones: lista de 3 dicts (para dependiente)
            boletas_honorarios: lista de montos (para independiente)
            dai: dict con cod110, cod850, cod617, cod304, cod158 (opcional)
            renta_fija: int CLP (default 0)
            dep_plazo: int CLP (default 0)
            retiros_dai: int CLP (default 0)
            renta_atribuida: int CLP (default 0)

            # Sinacofi
            score_sinacofi: int (1-999)
            rbi: int (0-100, default 0)

            # Política
            edad: int
            extranjero_sin_residencia: bool (default False)
            antiguedad_laboral_meses: int
            deuda_vencida: int CLP
            deuda_castigada: int CLP
            mora_sf: int CLP
            protestos: int CLP
            mora_casas_comerciales: int CLP
            quiebras: int
            infracciones_laborales: int CLP
            deterioro_propio: int CLP

            # CMF
            saldo_hipotecario: int CLP (default 0)
            saldo_consumo: int CLP (default 0)
            linea_credito: int CLP (default 0)
            saldo_linea_credito: int CLP (default 0)

            # Producto
            valor_propiedad_clp: int (CLP)
            pie_pct: float (0-1)
            edad_max_producto: int (= edad del cliente)
            amortizacion_pct: float
            plazo_meses: int

    Returns:
        dict con credit_score, verticales, renta, pd, endeudamiento, metadata
    """
    # ── 1. Renta Depurada ──
    tipo = cliente.get("tipo_renta", "dependiente")
    renta_dep = 0
    renta_bh = 0
    renta_dep_detail = None
    renta_bh_detail = None

    if tipo in ("dependiente", "mixto"):
        renta_dep_detail = calcular_renta_dependiente(cliente.get("liquidaciones", []))
        renta_dep = renta_dep_detail.get("renta_depurada", 0)

    if tipo in ("independiente", "mixto"):
        renta_bh_detail = calcular_renta_independiente_bh(
            cliente.get("boletas_honorarios", [])
        )
        renta_bh = renta_bh_detail.get("renta_depurada_bh", 0)

        # Merge con DAI si existe
        dai = cliente.get("dai")
        if dai:
            dai_result = calcular_renta_independiente_dai(**dai)
            renta_bh = merge_bh_dai(renta_bh, dai_result["renta_dai_mensual"])

    renta_total = calcular_renta_total(
        dep_liq=renta_dep,
        bh=renta_bh,
        ppm=0,  # PPM se pasa explícitamente si aplica
        renta_fija=cliente.get("renta_fija", 0),
        dep_plazo=cliente.get("dep_plazo", 0),
        retiros_dai=cliente.get("retiros_dai", 0),
        renta_atribuida=cliente.get("renta_atribuida", 0),
    )
    renta_final = renta_total["renta_total"]
    renta_lt_3m = renta_final < 3_000_000

    # ── 2. PD ──
    pd_result = calcular_pd_ajustada(
        cliente.get("score_sinacofi", 1),
        cliente.get("rbi", 0),
    )

    # ── 3. Endeudamiento CMF ──
    cmf = calcular_endeudamiento_cmf(
        saldo_hipotecario=cliente.get("saldo_hipotecario", 0),
        saldo_consumo=cliente.get("saldo_consumo", 0),
        linea_credito=cliente.get("linea_credito", 0),
        saldo_linea_credito=cliente.get("saldo_linea_credito", 0),
    )

    # ── 4. Métricas derivadas para Capacidad de Pago ──
    valor_prop = cliente.get("valor_propiedad_clp", 0)
    cuota_propio_clp = cliente.get("cuota_propio_clp", 0)  # cuota mensual real del programa
    egreso_cmf = cmf["egreso_mensual_estimado"]

    # GG.Fin/Renta = (egresos CMF + cuota PROPIO) / renta
    egreso_renta = (egreso_cmf + cuota_propio_clp) / renta_final if renta_final > 0 else 999

    # Veces/Renta = valor_propiedad / renta
    veces_renta = valor_prop / renta_final if renta_final > 0 else 999

    # Leverage = (deuda_total + valor_propiedad) / (renta × 12)
    # Expresado como múltiplo de renta anual
    deuda_total = (cliente.get("saldo_hipotecario", 0)
                   + cliente.get("saldo_consumo", 0)
                   + cliente.get("saldo_linea_credito", 0))
    renta_anual = renta_final * 12
    leverage = (deuda_total + valor_prop) / renta_anual if renta_anual > 0 else 999

    # ── 5. Evaluar 4 Verticales ──
    v_politica = evaluar_politica({
        "renta_depurada": renta_final,
        "extranjero_sin_residencia": cliente.get("extranjero_sin_residencia", False),
        "edad": cliente.get("edad", 0),
        "antiguedad_laboral_meses": cliente.get("antiguedad_laboral_meses", 0),
        "deuda_vencida": cliente.get("deuda_vencida", 0),
        "deuda_castigada": cliente.get("deuda_castigada", 0),
        "mora_sf": cliente.get("mora_sf", 0),
        "protestos": cliente.get("protestos", 0),
        "mora_casas_comerciales": cliente.get("mora_casas_comerciales", 0),
        "quiebras": cliente.get("quiebras", 0),
        "infracciones_laborales": cliente.get("infracciones_laborales", 0),
        "deterioro_propio": cliente.get("deterioro_propio", 0),
    })

    v_score = evaluar_score(pd_result["pd_ajustada"])

    v_cap_pago = evaluar_capacidad_pago({
        "egreso_renta": egreso_renta,
        "veces_renta": veces_renta,
        "leverage": leverage,
    }, renta_lt_3m=renta_lt_3m)

    v_producto = evaluar_producto({
        "valor_propiedad": valor_prop,
        "pie_pct": cliente.get("pie_pct", 0),
        "edad_max_producto": cliente.get("edad", 0),
    }, renta_lt_3m=renta_lt_3m)

    # ── 6. Credit Score ──
    cs = calcular_credit_score(
        v_politica["score"],
        v_score["score"],
        v_cap_pago["score"],
        v_producto["score"],
    )

    return {
        "credit_score": cs["credit_score"],
        "verticales": {
            "politica": {"score": v_politica["score"], "detalle": v_politica["detalle"]},
            "score_sinacofi": {"score": v_score["score"], "detalle": v_score["detalle"]},
            "capacidad_pago": {"score": v_cap_pago["score"], "detalle": v_cap_pago["detalle"]},
            "producto": {"score": v_producto["score"], "detalle": v_producto["detalle"]},
        },
        "promedio_verticales": cs["promedio_verticales"],
        "renta": {
            "renta_total": renta_final,
            "renta_lt_3m": renta_lt_3m,
            "tipo_renta": tipo,
            "dependiente": renta_dep_detail,
            "independiente": renta_bh_detail,
            "composicion": renta_total["componentes"],
        },
        "pd": pd_result,
        "endeudamiento": {
            "cmf": cmf,
            "egreso_renta": round(egreso_renta, 4),
            "veces_renta": round(veces_renta, 2),
            "leverage": round(leverage, 2),
        },
        "metadata": {
            "engine": "credit_score_v3.0",
            "timestamp": datetime.now().isoformat(),
            "fuente_parametros": "Motor de Riesgo Cliente + Activo 19.12.xlsm",
        },
    }


# ============================================================
# VALIDACIÓN — CASO MONTECINOS
# ============================================================
if __name__ == "__main__":
    montecinos = {
        "tipo_renta": "dependiente",
        "liquidaciones": [
            {"total_haberes": 3_929_177, "colacion": 0, "movilizacion": 0, "retencion_judicial": 0},
            {"total_haberes": 3_881_890, "colacion": 0, "movilizacion": 0, "retencion_judicial": 0},
            {"total_haberes": 3_420_985, "colacion": 0, "movilizacion": 0, "retencion_judicial": 0},
        ],
        "score_sinacofi": 534,
        "rbi": 0,  # nuevo, sin historial PROPIO
        "edad": 30,
        "extranjero_sin_residencia": False,
        "antiguedad_laboral_meses": 15,
        "deuda_vencida": 0,
        "deuda_castigada": 0,
        "mora_sf": 0,
        "protestos": 0,
        "mora_casas_comerciales": 0,
        "quiebras": 0,
        "infracciones_laborales": 0,
        "deterioro_propio": 0,
        "saldo_hipotecario": 0,
        "saldo_consumo": 0,
        "linea_credito": 0,
        "saldo_linea_credito": 0,
        "valor_propiedad_clp": 160_000_000,  # ~4487 UF × ~35,660 CLP/UF
        "cuota_propio_clp": 1_155_384,     # 32.4 UF × 35,660 CLP/UF
        "pie_pct": 0.10,
        "plazo_meses": 60,
    }

    r = run_credit_score(montecinos)

    print("=" * 70)
    print("PROPIO — Credit Score v3.0")
    print("=" * 70)
    print(f"\nCredit Score: {r['credit_score']}")
    print(f"Promedio verticales: {r['promedio_verticales']}")

    for v_name, v_data in r["verticales"].items():
        print(f"\n  {v_name}: Nivel {v_data['score']}")

    print(f"\nRenta depurada: ${r['renta']['renta_total']:,.0f} CLP")
    print(f"  Tipo: {r['renta']['tipo_renta']}")
    print(f"  < 3M: {r['renta']['renta_lt_3m']}")

    print(f"\nPD: {r['pd']['pd_ajustada']*100:.2f}% (base: {r['pd']['pd_base']*100:.2f}%, RBI: {r['pd']['rbi']})")

    print(f"\nEndeudamiento:")
    print(f"  Egreso/Renta: {r['endeudamiento']['egreso_renta']*100:.1f}%")
    print(f"  Veces/Renta:  {r['endeudamiento']['veces_renta']:.1f}")
    print(f"  Leverage:     {r['endeudamiento']['leverage']:.1f}")

    # Ejemplo de matriz
    print(f"\n{'─' * 70}")
    print("EJEMPLO MATRIZ (con Asset Score hipotético de 704)")
    matrix = lookup_matrix(r["credit_score"], 704)
    print(f"  Rating: {matrix['rating']}")
    print(f"  Nivel:  {matrix['nivel']} — {matrix['decision']}")
    print(f"  Bandas: Credit={matrix['credit_band']}, Asset={matrix['asset_band']}")
