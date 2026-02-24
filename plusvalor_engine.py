"""
PROPIO — Motor de Plusvalía & Exit v1.0
=======================================
Motor determinístico de análisis de plusvalía, amortización decreciente
y simulación hipotecaria para evaluación de exit.

Replica la lógica del dashboard PROPIO_OS_Evaluacion_v2.html (JS → Python).

Dependencias: solo math + datetime (stdlib).

Fórmulas core:
  Plusvalía(ipv, t) = Valor × ((1 + ipv)^(t/12) - 1)
  Amort(t) = α × a_flat − β × (t − 1)
  Bono(t) = Pie + α × a_flat × t − β × t(t−1)/2
  Exit = primer t donde Bono(t) + Plusvalía(t) ≥ Meta
  α_req = 1 + (N × arriendo × (T−1)) / (a_flat × T(T−1)/2)
  β = 2(α−1) × a_flat / (T−1)
"""

import math
from datetime import datetime


# ============================================================
# MOTOR DE AMORTIZACIÓN DECRECIENTE
# ============================================================
def crear_motor(pie, meta, cuota_propio, ingreso_uf,
                umbral_admision=0.40, n_buffer=2, plazo_max=60):
    """
    Inicializa el motor de amortización decreciente paramétrico.

    Args:
        pie: Pie inicial en UF
        meta: Meta de equity (20% del valor, típicamente) en UF
        cuota_propio: Cuota contractual total del programa en UF
        ingreso_uf: Ingreso mensual del cliente en UF
        umbral_admision: Umbral máximo cuota/ingreso (default 0.40)
        n_buffer: Meses de buffer por estrés (default 2)
        plazo_max: Plazo máximo del programa en meses (default 60)

    Returns:
        dict con parámetros del motor derivados
    """
    T = plazo_max
    amort_flat = (meta - pie) / T  # amortización plana base
    arriendo = cuota_propio - amort_flat  # componente consumo (derivado)

    # α_req: factor de sobre-amortización para generar buffer
    # Derivado de: buffer(T/2) = N × arriendo
    alpha = 1.0 + (n_buffer * arriendo * (T - 1)) / (amort_flat * (T * (T - 1) / 2))

    # α_max: máximo permitido por umbral de admisión (sobre ingreso nominal)
    alpha_max = (umbral_admision * ingreso_uf - arriendo) / amort_flat if amort_flat > 0 else 0

    # β: tasa de decaimiento de amortización (UF/mes)
    b_decay = 2.0 * (alpha - 1.0) * amort_flat / (T - 1) if T > 1 else 0

    # Cuota pico (mes 1)
    cuota_pico = arriendo + alpha * amort_flat

    # Cuota valle (mes T)
    cuota_valle = arriendo + alpha * amort_flat - b_decay * (T - 1)

    return {
        "pie": pie,
        "meta": meta,
        "amort_flat": round(amort_flat, 4),
        "arriendo": round(arriendo, 4),
        "cuota_propio": cuota_propio,
        "alpha": alpha,
        "alpha_max": alpha_max,
        "b_decay": b_decay,
        "n_buffer": n_buffer,
        "plazo_max": T,
        "ingreso_uf": ingreso_uf,
        "umbral_admision": umbral_admision,
        "cuota_pico": round(cuota_pico, 2),
        "cuota_valle": round(cuota_valle, 2),
        "alpha_viable": alpha <= alpha_max,
    }


# ============================================================
# FUNCIONES DE CÁLCULO (mes t, 1-indexed)
# ============================================================
def calc_amort_mes(motor, t):
    """Amortización marginal en mes t."""
    return motor["alpha"] * motor["amort_flat"] - motor["b_decay"] * (t - 1)


def calc_bono(motor, t):
    """Bono acumulado (pie + amortización acumulada) al mes t."""
    a = motor["alpha"]
    af = motor["amort_flat"]
    bd = motor["b_decay"]
    cum_amort = a * af * t - bd * t * (t - 1) / 2.0
    return motor["pie"] + cum_amort


def calc_cuota(motor, t):
    """Cuota total en mes t = arriendo + amortización(t)."""
    return motor["arriendo"] + calc_amort_mes(motor, t)


def calc_buffer(motor, t):
    """Buffer acumulado (exceso sobre trayectoria plana) al mes t."""
    T = motor["plazo_max"]
    return (motor["alpha"] - 1.0) * motor["amort_flat"] * t * (T - t) / (T - 1) if T > 1 else 0


# ============================================================
# PLUSVALÍA
# ============================================================
def calc_plusvalia(valor_activo, ipv, t):
    """
    Plusvalía al mes t.
    Plusvalía = Valor × ((1 + IPV)^(t/12) - 1)

    Args:
        valor_activo: Valor del activo en UF (strike, precio fijado en t0)
        ipv: Índice de Plusvalía anual (decimal, ej: 0.03 = 3%)
        t: Mes (1-indexed)
    """
    if ipv <= 0:
        return 0.0
    return valor_activo * (math.pow(1.0 + ipv, t / 12.0) - 1.0)


def calc_valor_estimado(valor_activo, ipv, t):
    """Valor estimado del activo al mes t con IPV."""
    return valor_activo * math.pow(1.0 + ipv, t / 12.0)


# ============================================================
# EXIT
# ============================================================
def find_exit_mes(motor, valor_activo, ipv):
    """
    Encuentra el primer mes donde Bono(t) + Plusvalía(t) >= Meta.

    Returns:
        int: mes de exit (1 a plazo_max)
    """
    T = motor["plazo_max"]
    meta = motor["meta"]
    for m in range(1, T + 1):
        bono = calc_bono(motor, m)
        plusv = calc_plusvalia(valor_activo, ipv, m)
        if bono + plusv >= meta:
            return m
    return T  # sin plusvalía suficiente, cierra al plazo máximo


# ============================================================
# SIMULACIÓN HIPOTECARIA (post-exit)
# ============================================================
def simular_hipotecario(valor_estimado, pie_acumulado, ingreso_uf,
                        tasa_anual=0.05, plazo_meses=360, umbral=0.25):
    """
    Simula condiciones hipotecarias post-exit PROPIO.

    Args:
        valor_estimado: Valor del activo al momento del exit (con plusvalía)
        pie_acumulado: Total acumulado (bono + plusvalía) como pie para banco
        ingreso_uf: Ingreso mensual en UF
        tasa_anual: Tasa hipotecaria anual (default 5%)
        plazo_meses: Plazo hipotecario en meses (default 360 = 30 años)
        umbral: Ratio máximo dividendo/ingreso para calificar (default 25%)

    Returns:
        dict con saldo, dividendo, ratio, pass/fail
    """
    pie_real = min(pie_acumulado, valor_estimado)
    saldo = max(valor_estimado - pie_real, 0)

    if saldo <= 0:
        return {
            "saldo_uf": 0,
            "dividendo_uf": 0,
            "ratio_dividendo_ingreso": 0,
            "pass": True,
            "pie_pct_valor": 1.0,
        }

    r = tasa_anual / 12.0
    if r > 0:
        dividendo = saldo * r / (1.0 - math.pow(1.0 + r, -plazo_meses))
    else:
        dividendo = saldo / plazo_meses

    ratio = dividendo / ingreso_uf if ingreso_uf > 0 else 999.0
    pie_pct = pie_real / valor_estimado if valor_estimado > 0 else 0

    return {
        "saldo_uf": round(saldo, 2),
        "dividendo_uf": round(dividendo, 2),
        "ratio_dividendo_ingreso": round(ratio, 4),
        "pass": ratio <= umbral,
        "pie_pct_valor": round(pie_pct, 4),
    }


# ============================================================
# CURVA DE EQUITY
# ============================================================
def generar_curva_equity(motor, valor_activo, ipv, checkpoints=None):
    """
    Genera la curva de equity con checkpoints estándar + mes de exit.

    Returns:
        list of dicts con bono, plusvalía, total, %meta por checkpoint
    """
    exit_mes = find_exit_mes(motor, valor_activo, ipv)
    T = motor["plazo_max"]
    meta = motor["meta"]

    if checkpoints is None:
        checkpoints = [12, 24, 36, exit_mes, T]

    puntos = sorted(set(checkpoints))
    curva = []

    for m in puntos:
        if m < 1 or m > T:
            continue
        bono = calc_bono(motor, m)
        plusv = calc_plusvalia(valor_activo, ipv, m)
        total = bono + plusv
        curva.append({
            "mes": m,
            "bono_uf": round(bono, 2),
            "plusvalia_uf": round(plusv, 2),
            "total_uf": round(total, 2),
            "pct_meta": round(total / meta * 100, 1) if meta > 0 else 0,
            "cumple_meta": total >= meta,
            "is_exit": m == exit_mes,
        })

    return curva


# ============================================================
# TRAYECTORIA DE CUOTAS
# ============================================================
def generar_trayectoria_cuotas(motor, meses=None):
    """
    Genera trayectoria de cuotas, amortización y buffer.

    Returns:
        list of dicts por mes
    """
    T = motor["plazo_max"]
    if meses is None:
        meses = list(range(1, T + 1))

    trayectoria = []
    for m in meses:
        cuota = calc_cuota(motor, m)
        amort = calc_amort_mes(motor, m)
        buffer = calc_buffer(motor, m)
        ratio = cuota / motor["ingreso_uf"] if motor["ingreso_uf"] > 0 else 0
        trayectoria.append({
            "mes": m,
            "cuota_uf": round(cuota, 2),
            "amortizacion_uf": round(amort, 2),
            "arriendo_uf": round(motor["arriendo"], 2),
            "buffer_uf": round(buffer, 2),
            "ratio_cuota_ingreso": round(ratio, 4),
        })

    return trayectoria


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
def run_plusvalor(datos):
    """
    Ejecuta el análisis completo de plusvalía y exit.

    Args:
        datos: dict con:
            valor_activo: Valor del activo en UF (strike t0)
            pie_uf: Pie inicial en UF
            meta_uf: Meta de equity en UF (típicamente 20% del valor)
            cuota_propio: Cuota contractual PROPIO en UF
            ingreso_uf: Ingreso mensual en UF
            ipv: IPV anual (decimal, ej: 0.03)
            --- opcionales ---
            plazo_max: Plazo máximo (default 60)
            n_buffer: Meses buffer (default 2)
            umbral_admision: Umbral cuota/ingreso (default 0.40)
            tasa_banco: Tasa hipotecaria anual (default 0.05)
            plazo_hipotecario: Meses hipoteca (default 360)
            umbral_banco: Ratio máximo banco (default 0.25)

    Returns:
        dict con análisis completo: exit, equity, hipotecario, motor, curva
    """
    # --- Motor ---
    motor = crear_motor(
        pie=datos["pie_uf"],
        meta=datos["meta_uf"],
        cuota_propio=datos["cuota_propio"],
        ingreso_uf=datos["ingreso_uf"],
        umbral_admision=datos.get("umbral_admision", 0.40),
        n_buffer=datos.get("n_buffer", 2),
        plazo_max=datos.get("plazo_max", 60),
    )

    valor = datos["valor_activo"]
    ipv = datos["ipv"]
    T = motor["plazo_max"]

    # --- Exit ---
    exit_mes = find_exit_mes(motor, valor, ipv)
    bono_exit = calc_bono(motor, exit_mes)
    plusv_exit = calc_plusvalia(valor, ipv, exit_mes)
    total_exit = bono_exit + plusv_exit
    valor_estimado = calc_valor_estimado(valor, ipv, exit_mes)

    # --- Descomposición del equity ---
    cuotas_acum = bono_exit - motor["pie"]  # amortización neta acumulada

    # --- Sin plusvalía (referencia) ---
    bono_60 = calc_bono(motor, T)
    exit_sin_plusv = T  # sin plusvalía, cierra al plazo máximo

    # --- Hipotecario ---
    pie_banco = min(total_exit, valor_estimado)
    hip = simular_hipotecario(
        valor_estimado=valor_estimado,
        pie_acumulado=pie_banco,
        ingreso_uf=datos["ingreso_uf"],
        tasa_anual=datos.get("tasa_banco", 0.05),
        plazo_meses=datos.get("plazo_hipotecario", 360),
        umbral=datos.get("umbral_banco", 0.25),
    )

    # --- Curva de equity ---
    curva = generar_curva_equity(motor, valor, ipv)

    # --- Trayectoria de cuotas (resumen) ---
    meses_resumen = [1, 6, 12, 24, 36, exit_mes, T]
    trayectoria = generar_trayectoria_cuotas(motor, sorted(set(meses_resumen)))

    # --- Análisis de sensibilidad IPV ---
    sensibilidad = []
    for ipv_test in [0.0, 0.01, 0.02, 0.03, 0.04, 0.05]:
        exit_t = find_exit_mes(motor, valor, ipv_test)
        plusv_t = calc_plusvalia(valor, ipv_test, exit_t)
        sensibilidad.append({
            "ipv": ipv_test,
            "exit_mes": exit_t,
            "plusvalia_uf": round(plusv_t, 2),
            "ahorro_meses": T - exit_t,
        })

    return {
        "exit": {
            "mes": exit_mes,
            "anos": round(exit_mes / 12.0, 1),
            "ahorro_meses": T - exit_mes,
            "sin_plusvalia_mes": exit_sin_plusv,
        },
        "equity_at_exit": {
            "pie_uf": round(motor["pie"], 2),
            "cuotas_acumuladas_uf": round(cuotas_acum, 2),
            "plusvalia_uf": round(plusv_exit, 2),
            "total_uf": round(total_exit, 2),
            "meta_uf": motor["meta"],
            "pct_meta": round(total_exit / motor["meta"] * 100, 1) if motor["meta"] > 0 else 0,
            "cumple": total_exit >= motor["meta"],
        },
        "valoracion": {
            "strike_uf": valor,
            "ipv": ipv,
            "valor_estimado_exit_uf": round(valor_estimado, 2),
            "plusvalia_bruta_uf": round(valor_estimado - valor, 2),
            "plusvalia_aplicada_uf": round(plusv_exit, 2),
        },
        "referencia_sin_plusvalia": {
            "bono_mes_60_uf": round(bono_60, 2),
            "pct_meta_60": round(bono_60 / motor["meta"] * 100, 1) if motor["meta"] > 0 else 0,
        },
        "hipotecario": {
            **hip,
            "cuota_propio_uf": datos["cuota_propio"],
            "ingreso_uf": datos["ingreso_uf"],
        },
        "curva_equity": curva,
        "trayectoria_cuotas": trayectoria,
        "sensibilidad_ipv": sensibilidad,
        "motor": {
            "alpha": round(motor["alpha"], 6),
            "alpha_max": round(motor["alpha_max"], 6),
            "alpha_viable": motor["alpha_viable"],
            "b_decay": round(motor["b_decay"], 6),
            "amort_flat_uf": motor["amort_flat"],
            "arriendo_uf": motor["arriendo"],
            "cuota_pico_uf": motor["cuota_pico"],
            "cuota_valle_uf": motor["cuota_valle"],
        },
        "metadata": {
            "engine": "plusvalor_v1.0",
            "timestamp": datetime.now().isoformat(),
            "ipv_input": ipv,
            "plazo_max": T,
            "n_buffer": motor["n_buffer"],
        },
    }


# ============================================================
# VALIDACIÓN — CASO MONTECINOS
# ============================================================
if __name__ == "__main__":
    datos_montecinos = {
        "valor_activo": 4487.22,
        "pie_uf": 107,        # ~10% × 20% meta ≈ UF 107
        "meta_uf": 897,        # 20% de 4487
        "cuota_propio": 32.40,
        "ingreso_uf": 88.3,    # ~$3.300.000 / UF
        "ipv": 0.03,           # 3% anual Padre Hurtado
        # opcionales
        "plazo_max": 60,
        "n_buffer": 2,
        "umbral_admision": 0.40,
        "tasa_banco": 0.05,
        "plazo_hipotecario": 360,
        "umbral_banco": 0.25,
    }

    r = run_plusvalor(datos_montecinos)

    print("=" * 70)
    print("PROPIO — Motor de Plusvalía & Exit v1.0")
    print("=" * 70)

    e = r["exit"]
    print(f"\nExit: Mes {e['mes']} ({e['anos']} años)")
    print(f"  Sin plusvalía: Mes {e['sin_plusvalia_mes']}")
    print(f"  Ahorro: {e['ahorro_meses']} meses")

    eq = r["equity_at_exit"]
    print(f"\nEquity al Exit:")
    print(f"  Pie:        UF {eq['pie_uf']}")
    print(f"  Cuotas:     UF {eq['cuotas_acumuladas_uf']}")
    print(f"  Plusvalía:  UF {eq['plusvalia_uf']}")
    print(f"  Total:      UF {eq['total_uf']} / {eq['meta_uf']} ({eq['pct_meta']}%)")
    print(f"  {'✓ Cumple meta' if eq['cumple'] else '✗ No cumple'}")

    v = r["valoracion"]
    print(f"\nValoración:")
    print(f"  Strike (t0): UF {v['strike_uf']}")
    print(f"  IPV:         {v['ipv']*100:.1f}% anual")
    print(f"  Valor exit:  UF {v['valor_estimado_exit_uf']}")
    print(f"  Plusvalía:   UF {v['plusvalia_aplicada_uf']}")

    h = r["hipotecario"]
    print(f"\nSimulación Hipotecaria:")
    print(f"  Saldo:       UF {h['saldo_uf']}")
    print(f"  Dividendo:   UF {h['dividendo_uf']}/mes")
    print(f"  Ratio D/I:   {h['ratio_dividendo_ingreso']*100:.1f}%")
    print(f"  Banco:       {'✓ CALIFICA' if h['pass'] else '⚠ CONDICIONAL'}")

    m = r["motor"]
    print(f"\nMotor:")
    print(f"  α = {m['alpha']:.4f}  (máx: {m['alpha_max']:.4f})  {'✓' if m['alpha_viable'] else '⚠ excede'}")
    print(f"  Cuota pico: UF {m['cuota_pico_uf']}  Valle: UF {m['cuota_valle_uf']}")

    print(f"\nCurva de Equity:")
    print(f"{'Mes':>5} {'Bono':>10} {'Plusv':>10} {'Total':>10} {'%Meta':>8}")
    for p in r["curva_equity"]:
        mark = " ← EXIT" if p["is_exit"] else ""
        print(f"{p['mes']:>5} {p['bono_uf']:>10.2f} {p['plusvalia_uf']:>10.2f} {p['total_uf']:>10.2f} {p['pct_meta']:>7.1f}%{mark}")

    print(f"\nSensibilidad IPV:")
    for s in r["sensibilidad_ipv"]:
        print(f"  IPV {s['ipv']*100:.0f}%: Exit mes {s['exit_mes']}, plusv UF {s['plusvalia_uf']}, ahorro {s['ahorro_meses']}m")
