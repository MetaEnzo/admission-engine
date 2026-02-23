"""
Tests para asset_credit_score.py v2.2
======================================
Ejecutar: pytest test_asset_credit_score.py -v
"""

import math
import pytest

from asset_credit_score import (
    _norm_cdf,
    _clamp,
    lookup_comuna,
    _score_dts,
    _score_qsd,
    _score_market_depth,
    _score_velocidad,
    _score_pbb,
    _score_asequibilidad,
    calcular_liquidez,
    calcular_cap_rate,
    calcular_estructural,
    calcular_locacion,
    calcular_tipologia,
    evaluar_gatekeepers,
    _decision,
    _nivel_confianza,
    _percentil,
    _alerta,
    _recomendacion,
    _precio_sugerido,
    _buffer_sugerido,
    run_asset_score,
    DATOS_MERCADO,
    FACTOR_FASE,
    FACTOR_ESTACIONAL,
    AJUSTE_LIQUIDEZ_FASE,
    AJUSTE_BANDA_FASE,
)


# ============================================================
# _norm_cdf
# ============================================================
class TestNormCdf:
    def test_cdf_cero(self):
        """CDF(0) = 0.5"""
        assert abs(_norm_cdf(0.0) - 0.5) < 1e-10

    def test_cdf_positivo_grande(self):
        """CDF(5) ≈ 1.0"""
        assert _norm_cdf(5.0) > 0.999999

    def test_cdf_negativo_grande(self):
        """CDF(-5) ≈ 0.0"""
        assert _norm_cdf(-5.0) < 1e-6

    def test_cdf_simetria(self):
        """CDF(x) + CDF(-x) = 1"""
        for x in [0.5, 1.0, 1.96, 2.5]:
            assert abs(_norm_cdf(x) + _norm_cdf(-x) - 1.0) < 1e-10

    def test_cdf_1_96(self):
        """CDF(1.96) ≈ 0.975"""
        assert abs(_norm_cdf(1.96) - 0.975) < 0.001


# ============================================================
# _clamp
# ============================================================
class TestClamp:
    def test_dentro_rango(self):
        assert _clamp(500) == 500

    def test_abajo(self):
        assert _clamp(-50) == 0

    def test_arriba(self):
        assert _clamp(1500) == 1000

    def test_exacto_limites(self):
        assert _clamp(0) == 0
        assert _clamp(1000) == 1000

    def test_custom_range(self):
        assert _clamp(5, 1, 10) == 5
        assert _clamp(0, 1, 10) == 1
        assert _clamp(15, 1, 10) == 10


# ============================================================
# lookup_comuna
# ============================================================
class TestLookupComuna:
    def test_exact_match(self):
        r = lookup_comuna("Maipu")
        assert r is not None
        assert r["dts"] == 65

    def test_case_insensitive(self):
        r = lookup_comuna("maipu")
        assert r is not None
        assert r["dts"] == 65

    def test_con_espacios(self):
        r = lookup_comuna("  Maipu  ")
        assert r is not None

    def test_comuna_inexistente(self):
        assert lookup_comuna("Rancagua") is None

    def test_padre_hurtado(self):
        """Caso Montecinos"""
        r = lookup_comuna("Padre hurtado")
        assert r is not None
        assert r["dts"] == 180

    def test_13_comunas(self):
        assert len(DATOS_MERCADO) == 13


# ============================================================
# Sub-scores individuales
# ============================================================
class TestSubScores:
    # DTS
    def test_dts_cero(self):
        """DTS=0 → score=1000"""
        assert _score_dts(0) == 1000.0

    def test_dts_365(self):
        """DTS=365 → score=0"""
        assert _score_dts(365) == 0.0

    def test_dts_mayor_365(self):
        """DTS>365 → clamped a 0"""
        assert _score_dts(500) == 0.0

    def test_dts_medio(self):
        """DTS=70 → 1000*(1-70/365) ≈ 808.22"""
        expected = 1000.0 * (1.0 - 70.0 / 365.0)
        assert abs(_score_dts(70) - expected) < 0.01

    # QSD
    def test_qsd_cero(self):
        assert _score_qsd(0) == 1000.0

    def test_qsd_0_3(self):
        assert _score_qsd(0.3) == 0.0

    def test_qsd_mayor_0_3(self):
        assert _score_qsd(0.5) == 0.0

    def test_qsd_medio(self):
        expected = 1000.0 * (1.0 - 0.07 / 0.3)
        assert abs(_score_qsd(0.07) - expected) < 0.01

    # Market Depth
    def test_md_cero(self):
        assert _score_market_depth(0) == 0.0

    def test_md_clamp_arriba(self):
        assert _score_market_depth(1.0) == 1000.0

    def test_md_normal(self):
        assert _score_market_depth(0.1) == 500.0

    # Velocidad
    def test_vel_cero_meses(self):
        assert _score_velocidad(0) == 1000.0

    def test_vel_24_meses(self):
        assert _score_velocidad(24) == 0.0

    def test_vel_mayor_24(self):
        assert _score_velocidad(30) == 0.0

    # PBB Score (step function)
    def test_pbb_mayor_0_30(self):
        assert _score_pbb(0.35) == 0

    def test_pbb_menor_0_05(self):
        assert _score_pbb(0.03) == 950

    def test_pbb_entre_0_10_0_125(self):
        assert _score_pbb(0.11) == 750

    def test_pbb_entre_0_20_0_25(self):
        assert _score_pbb(0.22) == 400

    # Asequibilidad
    def test_aseq_bajo_30(self):
        assert _score_asequibilidad(0.25) == 950

    def test_aseq_entre_35_40(self):
        assert _score_asequibilidad(0.37) == 700

    def test_aseq_sobre_45(self):
        assert _score_asequibilidad(0.50) == 300


# ============================================================
# calcular_liquidez
# ============================================================
class TestCalcularLiquidez:
    @pytest.fixture
    def mercado_ph(self):
        return lookup_comuna("Padre hurtado")

    def test_retorna_score(self, mercado_ph):
        r = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        assert "score" in r
        assert 0 <= r["score"] <= 1000

    def test_peso_040(self, mercado_ph):
        r = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        assert r["peso"] == 0.40
        assert abs(r["ponderado"] - r["score"] * 0.40) < 0.01

    def test_sub_scores_presentes(self, mercado_ph):
        r = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        for k in ["dts", "qsd", "market_depth", "velocidad", "pbb"]:
            assert k in r["sub_scores"]

    def test_pbb_ajustado(self, mercado_ph):
        r = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        assert r["pbb_ajustado"] >= 0
        assert r["pbb_ajustado"] <= 0.99

    def test_crisis_baja_score(self, mercado_ph):
        """Crisis debe bajar score vs Normal"""
        r_normal = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        r_crisis = calcular_liquidez(mercado_ph, 4487.22, 0.15, "CRISIS", "Q3")
        assert r_crisis["score"] < r_normal["score"]

    def test_expansion_sube_score(self, mercado_ph):
        r_normal = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        r_exp = calcular_liquidez(mercado_ph, 4487.22, 0.15, "EXPANSION", "Q3")
        assert r_exp["score"] >= r_normal["score"]

    def test_riesgo_pbb_clasificacion(self, mercado_ph):
        r = calcular_liquidez(mercado_ph, 4487.22, 0.15, "NORMAL", "Q3")
        assert r["riesgo_pbb"] in ["CRITICO", "ALTO", "MEDIO", "BAJO", "MUY BAJO"]


# ============================================================
# calcular_cap_rate
# ============================================================
class TestCalcularCapRate:
    @pytest.fixture
    def mercado_ph(self):
        return lookup_comuna("Padre hurtado")

    def test_retorna_score(self, mercado_ph):
        noi = 22.0 - 3.55  # renta - opex
        r = calcular_cap_rate(mercado_ph, 4487.22, noi, "NORMAL")
        assert "score" in r
        assert r["score"] in [0, 200, 400, 500, 700, 800, 900, 1000]

    def test_peso_030(self, mercado_ph):
        noi = 22.0 - 3.55
        r = calcular_cap_rate(mercado_ph, 4487.22, noi, "NORMAL")
        assert r["peso"] == 0.30

    def test_posicion_presente(self, mercado_ph):
        noi = 22.0 - 3.55
        r = calcular_cap_rate(mercado_ph, 4487.22, noi, "NORMAL")
        assert r["posicion"] in ["BAJO", "DENTRO", "ALTO"]

    def test_precio_cero(self, mercado_ph):
        r = calcular_cap_rate(mercado_ph, 0, 10, "NORMAL")
        assert r["cap_rate"] == 0
        assert r["score"] == 0

    def test_cap_rate_alto(self, mercado_ph):
        """NOI muy alto → cap rate alto → score 1000"""
        r = calcular_cap_rate(mercado_ph, 1000, 100, "NORMAL")
        assert r["score"] == 1000

    def test_contraccion_sube_banda(self, mercado_ph):
        """CONTRACCION sube banda min, haciendo más difícil aprobar"""
        noi = 22.0 - 3.55
        r_normal = calcular_cap_rate(mercado_ph, 4487.22, noi, "NORMAL")
        r_contra = calcular_cap_rate(mercado_ph, 4487.22, noi, "CONTRACCION")
        assert r_contra["banda_min_adj"] > r_normal["banda_min_adj"]


# ============================================================
# calcular_estructural
# ============================================================
class TestCalcularEstructural:
    def test_perfecto(self):
        r = calcular_estructural(10, 10, 10, 0)
        assert r["score"] == 1000.0

    def test_peso_020(self):
        r = calcular_estructural(10, 10, 10, 0)
        assert r["peso"] == 0.20
        assert abs(r["ponderado"] - r["score"] * 0.20) < 0.01

    def test_factor_antiguedad_max(self):
        """Antigüedad >= 15 años → factor = 0.7 (mínimo)"""
        r = calcular_estructural(10, 10, 10, 50)
        assert r["factor_antiguedad"] == 0.7

    def test_factor_antiguedad_0(self):
        """Antigüedad 0 → factor = 1.0"""
        r = calcular_estructural(10, 10, 10, 0)
        assert r["factor_antiguedad"] == 1.0

    def test_factor_antiguedad_10(self):
        """Antigüedad 10 → factor = MAX(0.7, 1-10/50) = 0.8"""
        r = calcular_estructural(10, 10, 10, 10)
        assert abs(r["factor_antiguedad"] - 0.8) < 0.001

    def test_score_con_antiguedad(self):
        """Score base 1000 × 0.8 = 800"""
        r = calcular_estructural(10, 10, 10, 10)
        assert abs(r["score"] - 800.0) < 0.01

    def test_scores_bajos(self):
        """estado=5, legal=5, sísmico=5 → base=(5+5+5)/3*100=500"""
        r = calcular_estructural(5, 5, 5, 0)
        assert abs(r["score"] - 500.0) < 0.01


# ============================================================
# calcular_locacion
# ============================================================
class TestCalcularLocacion:
    @pytest.fixture
    def mercado_lc(self):
        return lookup_comuna("Las Condes")

    def test_retorna_score_1000(self, mercado_lc):
        r = calcular_locacion(mercado_lc, 5, 5)
        assert "score" in r
        assert r["score"] >= 0

    def test_peso_005(self, mercado_lc):
        r = calcular_locacion(mercado_lc, 5, 5)
        assert r["peso"] == 0.05

    def test_formula(self, mercado_lc):
        """Verifica fórmula: ICVU×0.4 + ISMT×0.3 + (100-IPS)×0.2 + Con×10×0.05 + Serv×10×0.05, × 10"""
        con, serv = 5, 5
        expected_base = (85 * 0.40 + 90 * 0.30 + (100 - 15) * 0.20
                         + 5 * 10 * 0.05 + 5 * 10 * 0.05)
        expected = expected_base * 10
        r = calcular_locacion(mercado_lc, con, serv)
        assert abs(r["score"] - expected) < 0.01

    def test_padre_hurtado(self):
        """Padre Hurtado con conectividad=4, servicios=6"""
        mercado = lookup_comuna("Padre hurtado")
        r = calcular_locacion(mercado, 4, 6)
        assert r["score"] > 0


# ============================================================
# calcular_tipologia
# ============================================================
class TestCalcularTipologia:
    def test_retorna_score(self):
        r = calcular_tipologia(22.0, 24.0, 6, 8)
        assert "score" in r

    def test_peso_005(self):
        r = calcular_tipologia(22.0, 24.0, 6, 8)
        assert r["peso"] == 0.05

    def test_ratio_gasto_ingreso(self):
        r = calcular_tipologia(22.0, 24.0, 6, 8)
        assert abs(r["gasto_ingreso"] - 22.0 / 24.0) < 0.0001

    def test_renta_cliente_cero(self):
        """Sin ingreso → ratio = 1.0"""
        r = calcular_tipologia(22.0, 0, 5, 5)
        assert r["gasto_ingreso"] == 1.0

    def test_score_formula(self):
        """Verificar fórmula: aseq×0.6 + vel×100×0.2 + dem×100×0.2"""
        renta, cliente = 22.0, 24.0
        vel, dem = 6, 8
        ratio = renta / cliente  # 0.9167 → aseq = 300 (>0.45? no, 0.9167>0.45 → 300)
        expected = 300 * 0.60 + 6 * 100 * 0.20 + 8 * 100 * 0.20
        r = calcular_tipologia(renta, cliente, vel, dem)
        assert abs(r["score"] - expected) < 0.01


# ============================================================
# evaluar_gatekeepers
# ============================================================
class TestEvaluarGatekeepers:
    def test_all_pass(self):
        g = evaluar_gatekeepers(0.10, 0.06, 0.05, 10)
        assert g["all_pass"] is True
        assert g["pbb_ok"] is True
        assert g["cap_rate_ok"] is True
        assert g["noi_ok"] is True

    def test_pbb_falla(self):
        g = evaluar_gatekeepers(0.35, 0.06, 0.05, 10)
        assert g["pbb_ok"] is False
        assert g["all_pass"] is False

    def test_cap_rate_falla(self):
        """cap_rate < cap_min_adj × 0.9"""
        g = evaluar_gatekeepers(0.10, 0.01, 0.05, 10)
        assert g["cap_rate_ok"] is False
        assert g["all_pass"] is False

    def test_noi_falla(self):
        g = evaluar_gatekeepers(0.10, 0.06, 0.05, -5)
        assert g["noi_ok"] is False
        assert g["all_pass"] is False

    def test_noi_cero_falla(self):
        g = evaluar_gatekeepers(0.10, 0.06, 0.05, 0)
        assert g["noi_ok"] is False

    def test_pbb_exacto_0_30_pasa(self):
        """PBB < 0.30 (estricto)"""
        g = evaluar_gatekeepers(0.30, 0.06, 0.05, 10)
        assert g["pbb_ok"] is False  # >= 0.30 falla

    def test_detalle_vacio_si_pasa(self):
        g = evaluar_gatekeepers(0.10, 0.06, 0.05, 10)
        assert len(g["detalle"]) == 0

    def test_detalle_con_mensajes_si_falla(self):
        g = evaluar_gatekeepers(0.35, 0.01, 0.05, -5)
        assert len(g["detalle"]) == 3


# ============================================================
# Funciones de veredicto
# ============================================================
class TestVeredicto:
    def test_decision_aprobado(self):
        assert _decision(800) == "APROBADO"
        assert _decision(750) == "APROBADO"

    def test_decision_con_condiciones(self):
        assert _decision(730) == "APROBADO CON CONDICIONES"
        assert _decision(700) == "APROBADO CON CONDICIONES"

    def test_decision_analisis(self):
        assert _decision(650) == "ANALISIS DETALLADO"
        assert _decision(600) == "ANALISIS DETALLADO"

    def test_decision_rechazado(self):
        assert _decision(500) == "RECHAZADO"
        assert _decision(0) == "RECHAZADO"

    def test_nivel_confianza(self):
        assert _nivel_confianza(900) == "MUY ALTO"
        assert _nivel_confianza(750) == "ALTO"
        assert _nivel_confianza(650) == "MEDIO"
        assert _nivel_confianza(550) == "BAJO"
        assert _nivel_confianza(400) == "MUY BAJO"

    def test_percentil(self):
        assert _percentil(850) == 95
        assert _percentil(760) == 85
        assert _percentil(710) == 70
        assert _percentil(560) == 15
        assert _percentil(400) == 5

    def test_recomendacion(self):
        assert _recomendacion(800) == "Proceder con adquisición"
        assert _recomendacion(650) == "Negociar mejores términos"
        assert _recomendacion(550) == "Buscar alternativas"
        assert _recomendacion(400) == "No proceder"

    def test_precio_sugerido_score_bajo(self):
        assert _precio_sugerido(600, 1000) == 900.0

    def test_precio_sugerido_score_alto(self):
        assert _precio_sugerido(750, 1000) == 1000

    def test_buffer_sugerido(self):
        assert _buffer_sugerido(0.20) == 0.20
        assert _buffer_sugerido(0.12) == 0.15
        assert _buffer_sugerido(0.05) == 0.10


# ============================================================
# _alerta
# ============================================================
class TestAlerta:
    def test_pbb_alto(self):
        assert "PBB" in _alerta(0.25, 0.06, 0.05, 800)

    def test_cap_rate_bajo(self):
        assert "CAP RATE" in _alerta(0.10, 0.03, 0.05, 800)

    def test_liquidez_limitada(self):
        assert "LIQUIDEZ" in _alerta(0.10, 0.06, 0.05, 600)

    def test_sin_alertas(self):
        assert "Sin alertas" in _alerta(0.10, 0.06, 0.05, 700)


# ============================================================
# run_asset_score — integración
# ============================================================
class TestRunAssetScore:
    @pytest.fixture
    def montecinos(self):
        return {
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

    def test_montecinos_score_704(self, montecinos):
        """Validación contra Excel: score debe ser ~704.30"""
        r = run_asset_score(montecinos)
        assert "error" not in r
        assert abs(r["total"] - 704.30) < 1.0

    def test_montecinos_decision(self, montecinos):
        r = run_asset_score(montecinos)
        assert r["decision"] == "APROBADO CON CONDICIONES"

    def test_estructura_resultado(self, montecinos):
        r = run_asset_score(montecinos)
        assert "total" in r
        assert "decision" in r
        assert "gatekeepers" in r
        assert "dimensiones" in r
        assert "metadata" in r
        assert "alerta" in r
        assert "recomendacion" in r

    def test_5_dimensiones(self, montecinos):
        r = run_asset_score(montecinos)
        dims = r["dimensiones"]
        for d in ["liquidez", "cap_rate", "estructural", "locacion", "tipologia"]:
            assert d in dims
            assert "score" in dims[d]
            assert "ponderado" in dims[d]
            assert "peso" in dims[d]

    def test_pesos_suman_1(self, montecinos):
        r = run_asset_score(montecinos)
        dims = r["dimensiones"]
        total_peso = sum(dims[d]["peso"] for d in dims)
        assert abs(total_peso - 1.0) < 0.001

    def test_ponderados_suman_score(self, montecinos):
        r = run_asset_score(montecinos)
        dims = r["dimensiones"]
        total_pond = sum(dims[d]["ponderado"] for d in dims)
        assert abs(total_pond - r["total"]) < 0.01

    def test_gatekeepers_montecinos_pass(self, montecinos):
        r = run_asset_score(montecinos)
        assert r["gatekeepers"]["all_pass"] is True

    def test_metadata(self, montecinos):
        r = run_asset_score(montecinos)
        m = r["metadata"]
        assert m["engine"] == "asset_credit_score_v2.2"
        assert m["comuna"] == "Padre hurtado"
        assert m["fase_economica"] == "NORMAL"
        assert m["trimestre"] == "Q3"
        assert m["n_comunas_disponibles"] == 13

    def test_comuna_invalida(self):
        activo = {"comuna": "Rancagua", "precio_uf": 1000}
        r = run_asset_score(activo)
        assert "error" in r
        assert "comunas_disponibles" in r

    def test_inputs_derivados(self, montecinos):
        r = run_asset_score(montecinos)
        assert "inputs_derivados" in r
        assert abs(r["inputs_derivados"]["noi_mensual"] - 18.45) < 0.01
        assert abs(r["inputs_derivados"]["precio_con_buffer"] - 4487.22 * 1.15) < 0.01


# ============================================================
# Datos de mercado — integridad
# ============================================================
class TestDatosMercado:
    def test_13_comunas(self):
        assert len(DATOS_MERCADO) == 13

    def test_campos_requeridos(self):
        campos = ["dts", "qsd", "vol", "trx", "stk", "cap_min", "cap_max",
                   "icvu", "ismt", "ips", "zona", "riesgo"]
        for comuna, data in DATOS_MERCADO.items():
            for c in campos:
                assert c in data, f"Campo '{c}' falta en {comuna}"

    def test_cap_min_menor_cap_max(self):
        for comuna, data in DATOS_MERCADO.items():
            assert data["cap_min"] < data["cap_max"], f"{comuna}: cap_min >= cap_max"

    def test_dts_positivo(self):
        for comuna, data in DATOS_MERCADO.items():
            assert data["dts"] > 0, f"{comuna}: DTS <= 0"


# ============================================================
# Factores de ciclo — integridad
# ============================================================
class TestFactores:
    def test_5_fases(self):
        fases = ["EXPANSION", "NORMAL", "DESACELERACION", "CONTRACCION", "CRISIS"]
        for f in fases:
            assert f in FACTOR_FASE
            assert f in AJUSTE_LIQUIDEZ_FASE
            assert f in AJUSTE_BANDA_FASE

    def test_4_trimestres(self):
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            assert q in FACTOR_ESTACIONAL

    def test_normal_neutro(self):
        assert FACTOR_FASE["NORMAL"] == 0.0
        assert AJUSTE_LIQUIDEZ_FASE["NORMAL"] == 0
        assert AJUSTE_BANDA_FASE["NORMAL"] == 0.0

    def test_crisis_mas_severa(self):
        """Crisis debe tener factores más severos que Normal"""
        assert FACTOR_FASE["CRISIS"] > FACTOR_FASE["NORMAL"]
        assert AJUSTE_LIQUIDEZ_FASE["CRISIS"] < AJUSTE_LIQUIDEZ_FASE["NORMAL"]
        assert AJUSTE_BANDA_FASE["CRISIS"] > AJUSTE_BANDA_FASE["NORMAL"]


# ============================================================
# Stress tests
# ============================================================
class TestStress:
    @pytest.fixture
    def activo_base(self):
        return {
            "comuna": "Las Condes",
            "precio_uf": 5000,
            "buffer_pct": 0.15,
            "renta_mensual_uf": 25.0,
            "opex_mensual_uf": 5.0,
            "antiguedad_anos": 5,
            "fase_economica": "NORMAL",
            "trimestre": "Q2",
            "estado_fisico": 8,
            "cumplimiento_legal": 9,
            "riesgo_sismico": 7,
            "conectividad": 7,
            "servicios": 8,
            "velocidad_absorcion": 7,
            "demanda_zona": 8,
            "renta_cliente_uf": 30.0,
        }

    def test_score_entre_0_y_1000(self, activo_base):
        r = run_asset_score(activo_base)
        assert 0 <= r["total"] <= 1000

    def test_crisis_baja_score(self, activo_base):
        activo_base["fase_economica"] = "CRISIS"
        r_crisis = run_asset_score(activo_base)
        activo_base["fase_economica"] = "NORMAL"
        r_normal = run_asset_score(activo_base)
        assert r_crisis["total"] < r_normal["total"]

    def test_noi_negativo_falla_gate(self, activo_base):
        activo_base["opex_mensual_uf"] = 50  # opex > renta → NOI negativo
        r = run_asset_score(activo_base)
        assert r["gatekeepers"]["noi_ok"] is False

    def test_todas_comunas(self, activo_base):
        """Ejecutar en las 13 comunas sin errores"""
        for comuna in DATOS_MERCADO.keys():
            activo_base["comuna"] = comuna
            r = run_asset_score(activo_base)
            assert "error" not in r
            assert 0 <= r["total"] <= 1000
