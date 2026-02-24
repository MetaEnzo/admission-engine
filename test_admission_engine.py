"""
Tests para propio_admission_engine.py v2.1
==========================================
Ejecutar: pytest test_admission_engine.py -v
"""

import math
import pytest

from propio_admission_engine import (
    normalize,
    normalize_cv,
    distance,
    similarity_pct,
    find_similares,
    evaluar_gates,
    generar_brief,
    crear_marcador,
    run_admission,
    PORTFOLIO,
    RANGES,
    WEIGHTS,
    MARCADOR_NIVELES,
)


# ============================================================
# normalize
# ============================================================
class TestNormalize:
    def test_dentro_de_rango(self):
        assert normalize(0.5, 0.0, 1.0) == 0.5

    def test_limite_inferior(self):
        assert normalize(0.0, 0.0, 1.0) == 0.0

    def test_limite_superior(self):
        assert normalize(1.0, 0.0, 1.0) == 1.0

    def test_clamp_arriba(self):
        """Valor sobre hi → clamped a 1.0"""
        assert normalize(2.0, 0.0, 1.0) == 1.0

    def test_clamp_abajo(self):
        """Valor bajo lo → clamped a 0.0"""
        assert normalize(-0.5, 0.0, 1.0) == 0.0

    def test_hi_igual_lo(self):
        """hi == lo → retorna 0.0 (sin division por cero)"""
        assert normalize(5.0, 5.0, 5.0) == 0.0

    def test_rango_pd(self):
        """PD 0.05 en rango [0, 0.85] ≈ 0.0588"""
        result = normalize(0.05, *RANGES["pd"])
        assert abs(result - 0.05 / 0.85) < 1e-6


# ============================================================
# normalize_cv
# ============================================================
class TestNormalizeCv:
    def test_dependiente_usa_rango_dep(self):
        """tipo=1 (dep) → rango cv_dep [0, 0.10]"""
        result = normalize_cv(0.05, tipo=1)
        expected = normalize(0.05, 0.0, 0.10)
        assert result == expected

    def test_independiente_usa_rango_ind(self):
        """tipo=0 (indep) → rango cv_ind [0, 0.60]"""
        result = normalize_cv(0.30, tipo=0)
        expected = normalize(0.30, 0.0, 0.60)
        assert result == expected

    def test_dep_cv_cero(self):
        assert normalize_cv(0.0, tipo=1) == 0.0

    def test_indep_cv_alto(self):
        """CV 0.60 para independiente = 1.0 (tope del rango)"""
        assert normalize_cv(0.60, tipo=0) == 1.0


# ============================================================
# distance
# ============================================================
class TestDistance:
    @pytest.fixture
    def postulante_base(self):
        return {
            "nombre": "Test",
            "pd": 0.05,
            "pie": 0.10,
            "ratio": 0.35,
            "tipo": 1,
            "cr_acido": 1.5,
            "cv": 0.006,
        }

    def test_identico_distancia_cero(self, postulante_base):
        """Mismo perfil → distancia ≈ 0"""
        cliente = postulante_base.copy()
        d = distance(postulante_base, cliente)
        assert d < 1e-6

    def test_distancia_no_negativa(self, postulante_base):
        for c in PORTFOLIO:
            d = distance(postulante_base, c)
            assert d >= 0

    def test_ratio_none_skip(self, postulante_base):
        """Si cliente tiene ratio=None, se salta esa dimension"""
        cliente_sin_ratio = postulante_base.copy()
        cliente_sin_ratio["ratio"] = None
        d = distance(postulante_base, cliente_sin_ratio)
        assert d >= 0  # no crashea

    def test_postulante_ratio_none(self, postulante_base):
        """Si postulante tiene ratio=None, se salta ratio"""
        postulante_base["ratio"] = None
        cliente = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 1, "cv": 0.006}
        d = distance(postulante_base, cliente)
        assert d >= 0

    def test_tipo_diferente_penaliza(self, postulante_base):
        """Dep vs Indep agrega penalización"""
        cliente_mismo_tipo = postulante_base.copy()
        cliente_otro_tipo = postulante_base.copy()
        cliente_otro_tipo["tipo"] = 0

        d_mismo = distance(postulante_base, cliente_mismo_tipo)
        d_otro = distance(postulante_base, cliente_otro_tipo)
        assert d_otro > d_mismo

    def test_simetria(self, postulante_base):
        """distance(A, B) ≈ distance(B, A)"""
        cliente = PORTFOLIO[0]
        d1 = distance(postulante_base, cliente)
        d2 = distance(cliente, postulante_base)
        assert abs(d1 - d2) < 1e-10


# ============================================================
# similarity_pct
# ============================================================
class TestSimilarityPct:
    def test_distancia_cero(self):
        assert similarity_pct(0.0) == 100.0

    def test_distancia_uno(self):
        assert similarity_pct(1.0) == 0.0

    def test_no_negativa(self):
        """Distancia > 1 → similarity clamped a 0"""
        assert similarity_pct(1.5) == 0

    def test_medio(self):
        assert similarity_pct(0.5) == 50.0


# ============================================================
# find_similares
# ============================================================
class TestFindSimilares:
    @pytest.fixture
    def montecinos(self):
        return {
            "nombre": "Andrés Montecinos",
            "pd": 0.05,
            "pie": 0.10,
            "ratio": 0.367,
            "tipo": 1,
            "cr_acido": 1.39,
            "cv": 0.006,
        }

    def test_retorna_top_n(self, montecinos):
        result = find_similares(montecinos, top_n=5)
        assert len(result) == 5

    def test_ordenado_por_distancia(self, montecinos):
        result = find_similares(montecinos, top_n=10)
        distancias = [s["distancia"] for s in result]
        assert distancias == sorted(distancias)

    def test_campos_completos(self, montecinos):
        result = find_similares(montecinos, top_n=1)
        campos = ["nombre", "pd", "pie", "ratio", "tipo", "cr_acido",
                   "cv", "outcome", "detalle", "distancia", "similaridad"]
        for campo in campos:
            assert campo in result[0]

    def test_outcomes_validos(self, montecinos):
        result = find_similares(montecinos, top_n=15)
        for s in result:
            assert s["outcome"] in ("exit", "activo", "problematico")

    def test_similaridad_rango(self, montecinos):
        result = find_similares(montecinos, top_n=15)
        for s in result:
            assert 0 <= s["similaridad"] <= 100

    def test_top_n_mayor_que_portfolio(self, montecinos):
        """Si pido más que el portfolio, retorna todo"""
        result = find_similares(montecinos, top_n=100)
        assert len(result) == len(PORTFOLIO)


# ============================================================
# evaluar_gates
# ============================================================
class TestEvaluarGates:
    def test_todo_pasa(self):
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 1.5, "cv": 0.006}
        gates = evaluar_gates(post)
        assert all(g["pass"] for g in gates)

    def test_cr_acido_falla(self):
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 0.8, "cv": 0.006}
        gates = evaluar_gates(post)
        cr_gate = next(g for g in gates if "Cobertura" in g["nombre"])
        assert cr_gate["pass"] is False

    def test_pd_falla(self):
        post = {"pd": 0.15, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 1.5, "cv": 0.006}
        gates = evaluar_gates(post)
        pd_gate = next(g for g in gates if "PD" in g["nombre"])
        assert pd_gate["pass"] is False

    def test_cv_dependiente_falla(self):
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 1.5, "cv": 0.12}
        gates = evaluar_gates(post)
        cv_gate = next(g for g in gates if "CV" in g["nombre"])
        assert cv_gate["pass"] is False

    def test_cv_independiente_siempre_pasa(self):
        """Independiente: CV es metadata/flag, no hard gate — siempre pasa"""
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 0,
                "cr_acido": 1.5, "cv": 0.478}
        gates = evaluar_gates(post)
        cv_gate = next(g for g in gates if "CV" in g["nombre"])
        assert cv_gate["pass"] is True
        assert cv_gate["threshold"] is None

    def test_pd_borderline(self):
        """PD exactamente 0.10 → FALLA (< 0.10, no <=)"""
        post = {"pd": 0.10, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 1.5, "cv": 0.006}
        gates = evaluar_gates(post)
        pd_gate = next(g for g in gates if "PD" in g["nombre"])
        assert pd_gate["pass"] is False

    def test_cr_borderline_pasa(self):
        """CR exactamente 1.0 → PASA (>= 1.0)"""
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 1.0, "cv": 0.006}
        gates = evaluar_gates(post)
        cr_gate = next(g for g in gates if "Cobertura" in g["nombre"])
        assert cr_gate["pass"] is True

    def test_retorna_3_gates_dependiente(self):
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 1,
                "cr_acido": 1.5, "cv": 0.006}
        gates = evaluar_gates(post)
        assert len(gates) == 3

    def test_retorna_3_gates_independiente(self):
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 0,
                "cr_acido": 1.5, "cv": 0.30}
        gates = evaluar_gates(post)
        assert len(gates) == 3


# ============================================================
# generar_brief
# ============================================================
class TestGenerarBrief:
    def test_3_exits_confianza_alta(self):
        similares = [
            {"nombre": "A", "outcome": "exit", "similaridad": 95, "detalle": "ok"},
            {"nombre": "B", "outcome": "exit", "similaridad": 90, "detalle": "ok"},
            {"nombre": "C", "outcome": "exit", "similaridad": 85, "detalle": "ok"},
            {"nombre": "D", "outcome": "activo", "similaridad": 80, "detalle": "ok"},
            {"nombre": "E", "outcome": "activo", "similaridad": 75, "detalle": "ok"},
        ]
        gates = [{"pass": True, "nombre": "CR", "detalle": "ok"}]
        brief = generar_brief("Test", similares, gates)
        assert "alta" in brief.lower()

    def test_gate_fail_señal_atencion(self):
        similares = [
            {"nombre": "A", "outcome": "exit", "similaridad": 95, "detalle": "ok"},
            {"nombre": "B", "outcome": "exit", "similaridad": 90, "detalle": "ok"},
            {"nombre": "C", "outcome": "exit", "similaridad": 85, "detalle": "ok"},
            {"nombre": "D", "outcome": "activo", "similaridad": 80, "detalle": "ok"},
            {"nombre": "E", "outcome": "activo", "similaridad": 75, "detalle": "ok"},
        ]
        gates = [{"pass": False, "nombre": "CR Ácida", "detalle": "CR = 0.56 < 1.0"}]
        brief = generar_brief("Test", similares, gates)
        assert "GATE FAIL" in brief
        assert "atención" in brief.lower()

    def test_sin_exits(self):
        similares = [
            {"nombre": "A", "outcome": "activo", "similaridad": 80, "detalle": "ok"},
            {"nombre": "B", "outcome": "activo", "similaridad": 75, "detalle": "ok"},
        ]
        gates = [{"pass": True, "nombre": "CR", "detalle": "ok"}]
        brief = generar_brief("Test", similares, gates)
        assert "sin precedentes" in brief.lower()

    def test_problematico_mencionado(self):
        similares = [
            {"nombre": "A", "outcome": "exit", "similaridad": 95, "detalle": "ok"},
            {"nombre": "Pablo", "outcome": "problematico", "similaridad": 60, "detalle": "CR<1"},
        ]
        gates = [{"pass": True, "nombre": "CR", "detalle": "ok"}]
        brief = generar_brief("Test", similares, gates)
        assert "Pablo" in brief
        assert "deterioro" in brief.lower()


# ============================================================
# crear_marcador
# ============================================================
class TestCrearMarcador:
    def test_m1_nivel_1(self):
        m = crear_marcador("M1", nivel=1, narrativa="Test narrativa")
        assert m["id"] == "M1"
        assert m["nivel"] == 1
        assert m["label"] == "RÍGIDO"
        assert m["trunca"] is False
        assert m["validado_por_operador"] is False

    def test_nivel_4_trunca(self):
        """Nivel 4 en cualquier marcador → trunca = True"""
        m = crear_marcador("M2", nivel=4, narrativa="Alto riesgo")
        assert m["trunca"] is True
        assert m["label"] == "ALTO"

    def test_m3_nivel_3(self):
        m = crear_marcador("M3", nivel=3, narrativa="Señales")
        assert m["label"] == "BANDERA AMARILLA"
        assert m["valor_politica"] == 0.66

    def test_datos_soporte(self):
        datos = {"empleador": "AES Andes", "sector": "Energía"}
        m = crear_marcador("M2", nivel=1, narrativa="N", datos_soporte=datos)
        assert m["datos_soporte"] == datos

    def test_sin_datos_soporte(self):
        m = crear_marcador("M1", nivel=2, narrativa="N")
        assert m["datos_soporte"] == {}

    def test_marcador_invalido_lanza_error(self):
        with pytest.raises(KeyError):
            crear_marcador("M99", nivel=1, narrativa="N")

    def test_nivel_invalido_lanza_error(self):
        with pytest.raises(KeyError):
            crear_marcador("M1", nivel=5, narrativa="N")


# ============================================================
# run_admission (integración)
# ============================================================
class TestRunAdmission:
    @pytest.fixture
    def montecinos(self):
        return {
            "nombre": "Andrés Montecinos",
            "pd": 0.05,
            "pie": 0.10,
            "ratio": 0.367,
            "tipo": 1,
            "cr_acido": 1.39,
            "cv": 0.006,
        }

    def test_estructura_resultado(self, montecinos):
        r = run_admission(montecinos)
        assert "postulante" in r
        assert "gates" in r
        assert "matching" in r
        assert "brief" in r
        assert "marcadores_semanticos" in r
        assert "metadata" in r

    def test_gates_all_pass(self, montecinos):
        r = run_admission(montecinos)
        assert r["gates"]["all_pass"] is True

    def test_top5_tiene_5(self, montecinos):
        r = run_admission(montecinos)
        assert len(r["matching"]["top5"]) == 5

    def test_ranking_completo(self, montecinos):
        r = run_admission(montecinos)
        assert len(r["matching"]["ranking_completo"]) == len(PORTFOLIO)

    def test_sin_marcadores(self, montecinos):
        r = run_admission(montecinos)
        assert r["marcadores_semanticos"]["marcadores"] == []
        assert r["marcadores_semanticos"]["politica_trunca"] is False

    def test_con_marcadores(self, montecinos):
        m1 = crear_marcador("M1", nivel=1, narrativa="Rígido")
        m2 = crear_marcador("M2", nivel=2, narrativa="Bajo")
        r = run_admission(montecinos, marcadores=[m1, m2])
        assert len(r["marcadores_semanticos"]["marcadores"]) == 2
        assert r["marcadores_semanticos"]["politica_trunca"] is False

    def test_politica_trunca_nivel_4(self, montecinos):
        m_trunca = crear_marcador("M1", nivel=4, narrativa="Volátil")
        r = run_admission(montecinos, marcadores=[m_trunca])
        assert r["marcadores_semanticos"]["politica_trunca"] is True

    def test_metadata(self, montecinos):
        r = run_admission(montecinos)
        assert r["metadata"]["engine"] == "propio_admission_v3.0"
        assert r["metadata"]["n_portfolio"] == len(PORTFOLIO)

    def test_caso_problematico(self):
        """Pablo Pérez profile → CR gate falla"""
        pablo = {
            "nombre": "Pablo Pérez",
            "pd": 0.83,
            "pie": 0.20,
            "ratio": 0.246,
            "tipo": 0,
            "cr_acido": 0.56,
            "cv": 0.478,
        }
        r = run_admission(pablo)
        assert r["gates"]["all_pass"] is False
        assert "GATE FAIL" in r["brief"]


# ============================================================
# PORTFOLIO — validaciones de integridad
# ============================================================
class TestPortfolio:
    def test_15_clientes(self):
        assert len(PORTFOLIO) == 15

    def test_outcomes_validos(self):
        for c in PORTFOLIO:
            assert c["outcome"] in ("exit", "activo", "problematico")

    def test_un_problematico(self):
        probs = [c for c in PORTFOLIO if c["outcome"] == "problematico"]
        assert len(probs) == 1
        assert probs[0]["nombre"] == "Pablo Pérez"

    def test_6_exits(self):
        exits = [c for c in PORTFOLIO if c["outcome"] == "exit"]
        assert len(exits) == 6

    def test_campos_requeridos(self):
        campos = ["nombre", "pd", "pie", "ratio", "tipo", "cr_acido", "cv", "outcome"]
        for c in PORTFOLIO:
            for campo in campos:
                assert campo in c, f"{c['nombre']} missing {campo}"


# ============================================================
# CREDIT SCORE — tests
# ============================================================
class TestCreditScore:
    """Tests para credit_score.py"""

    def test_import(self):
        from credit_score import run_credit_score, lookup_matrix
        assert callable(run_credit_score)
        assert callable(lookup_matrix)

    def test_renta_dependiente(self):
        from credit_score import calcular_renta_dependiente
        liqs = [
            {"total_haberes": 3_000_000},
            {"total_haberes": 3_100_000},
            {"total_haberes": 2_900_000},
        ]
        r = calcular_renta_dependiente(liqs)
        assert "renta_depurada" in r
        assert r["renta_depurada"] > 0
        assert r["variabilidad"] < 0.40

    def test_renta_insuficiente(self):
        from credit_score import calcular_renta_dependiente
        r = calcular_renta_dependiente([{"total_haberes": 1_000_000}])
        assert "error" in r

    def test_pd_ajustada_sin_rbi(self):
        from credit_score import calcular_pd_ajustada
        r = calcular_pd_ajustada(534, rbi=None)
        assert r["pd_ajustada"] == r["pd_base"]
        assert r["factor_rbi"] == 1.0

    def test_pd_ajustada_con_rbi(self):
        from credit_score import calcular_pd_ajustada
        r = calcular_pd_ajustada(534, rbi=95)
        assert r["pd_ajustada"] < r["pd_base"]  # RBI alto reduce PD
        assert r["factor_rbi"] < 1.0

    def test_run_credit_score_montecinos(self):
        from credit_score import run_credit_score
        c = {
            "pd_sinacofi": 0.05,
            "score_sinacofi": 534,
            "rbi": None,
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
                {"total_haberes": 3_410_985},
                {"total_haberes": 3_420_000},
                {"total_haberes": 3_402_000},
            ],
            "valor_prop_uf": 4487.22,
            "pie_pct": 0.10,
            "ltv": 0.90,
            "plazo_meses": 60,
            "tasa_anual": 0.065,
            "arriendo_uf": 22.0,
            "cuota_ingreso_ratio": 0.367,
        }
        r = run_credit_score(c)
        assert "credit_score" in r
        assert 250 <= r["credit_score"] <= 1000
        assert "verticales" in r
        assert len(r["verticales"]) == 4
        assert r["pd"]["pd_ajustada"] == 0.05  # Score 534 → PD 5%

    def test_lookup_matrix(self):
        from credit_score import lookup_matrix
        # Credit 875 (band 4) × Asset 704 (band 3) → AA, nivel 4
        r = lookup_matrix(875, 704)
        assert r["rating"] is not None
        assert r["nivel"] >= 1
        # Credit bajo × Asset bajo → nivel bajo
        r2 = lookup_matrix(300, 400)
        assert r2["nivel"] <= r["nivel"]

    def test_factor_renta_bracket(self):
        from credit_score import _get_factor_renta
        # Factor exists for different brackets
        f_low = _get_factor_renta(500_000)
        f_high = _get_factor_renta(5_000_000)
        assert 0 < f_low <= 1.0
        assert 0 < f_high <= 1.0

    def test_endeudamiento_cmf(self):
        from credit_score import calcular_endeudamiento_cmf
        r = calcular_endeudamiento_cmf(
            saldo_hipotecario=0,
            saldo_consumo=500_000,
            linea_credito=1_000_000,
            saldo_linea_credito=200_000,
        )
        assert "egreso_mensual_estimado" in r


# ============================================================
# PLUSVALOR ENGINE — tests
# ============================================================
class TestPlusvalorEngine:
    """Tests para plusvalor_engine.py"""

    def test_import(self):
        from plusvalor_engine import run_plusvalor, crear_motor
        assert callable(run_plusvalor)
        assert callable(crear_motor)

    def test_crear_motor(self):
        from plusvalor_engine import crear_motor
        m = crear_motor(
            pie=448.72,
            meta=897.44,
            cuota_propio=32.4,
            ingreso_uf=110.0,
        )
        assert m["alpha"] > 1.0
        assert m["alpha_viable"] is True
        assert m["arriendo"] > 0
        assert m["amort_flat"] > 0

    def test_calc_funciones_basicas(self):
        from plusvalor_engine import crear_motor, calc_plusvalia, calc_bono, calc_amort_mes, calc_cuota
        m = crear_motor(pie=448.72, meta=897.44, cuota_propio=32.4, ingreso_uf=110.0)
        # Plusvalía crece con IPV
        p0 = calc_plusvalia(4487.22, 0.0, 12)
        p3 = calc_plusvalia(4487.22, 0.03, 12)
        assert p0 == 0.0
        assert p3 > 0

        # Bono crece con t
        b1 = calc_bono(m, 1)
        b12 = calc_bono(m, 12)
        assert b12 > b1

        # Amort decrece
        a1 = calc_amort_mes(m, 1)
        a12 = calc_amort_mes(m, 12)
        assert a1 > a12  # amortización decreciente

        # Cuota decrece
        c1 = calc_cuota(m, 1)
        c12 = calc_cuota(m, 12)
        assert c1 > c12

    def test_find_exit_mes(self):
        from plusvalor_engine import crear_motor, find_exit_mes
        m = crear_motor(pie=448.72, meta=897.44, cuota_propio=32.4, ingreso_uf=110.0)
        # Con IPV alto, exit es antes
        exit_0 = find_exit_mes(m, 4487.22, 0.0)
        exit_5 = find_exit_mes(m, 4487.22, 0.05)
        assert exit_5 < exit_0

    def test_run_plusvalor_montecinos(self):
        from plusvalor_engine import run_plusvalor
        d = {
            "valor_activo": 4487.22,
            "pie_uf": 448.722,
            "meta_uf": 897.444,
            "cuota_propio": 32.4,
            "ingreso_uf": 110.0,
            "ipv": 0.03,
            "plazo_max": 60,
            "tasa_banco": 0.045,
            "plazo_hipotecario": 240,
        }
        r = run_plusvalor(d)
        assert "exit" in r
        assert "hipotecario" in r
        assert "sensibilidad_ipv" in r
        assert "motor" in r
        assert r["exit"]["mes"] < 60  # con IPV 3%, sale antes del plazo
        assert r["hipotecario"]["pass"] is True  # califica banco

    def test_sensibilidad_monotona(self):
        """Mayor IPV → exit más temprano"""
        from plusvalor_engine import run_plusvalor
        d = {
            "valor_activo": 4487.22,
            "pie_uf": 448.722,
            "meta_uf": 897.444,
            "cuota_propio": 32.4,
            "ingreso_uf": 110.0,
            "ipv": 0.03,
            "plazo_max": 60,
        }
        r = run_plusvalor(d)
        exits = [s["exit_mes"] for s in r["sensibilidad_ipv"]]
        # exit_mes should be non-increasing as IPV increases
        for i in range(len(exits) - 1):
            assert exits[i] >= exits[i + 1]


# ============================================================
# INTEGRACIÓN v3.0 — tests
# ============================================================
class TestIntegracionV3:
    """Tests de integración para engine v3.0 completo"""

    def test_run_admission_con_todos_los_modulos(self):
        postulante = {
            "nombre": "Test", "pd": 0.05, "pie": 0.10,
            "ratio": 0.35, "tipo": 1, "cr_acido": 1.5, "cv": 0.01,
        }
        cliente_credit = {
            "score_sinacofi": 534, "rbi": None,
            "tipo_contrato": "dependiente", "antiguedad_meses": 15,
            "historial_equifax_meses": 36, "morosidades_vigentes": 0,
            "protestos": 0, "deuda_total_clp": 0,
            "cuota_propio_clp": 1_000_000, "otros_creditos_clp": 0,
            "ingreso_bruto_clp": 3_000_000,
            "liquidaciones": [
                {"total_haberes": 3_000_000},
                {"total_haberes": 3_050_000},
                {"total_haberes": 2_950_000},
            ],
            "valor_prop_uf": 4500, "pie_pct": 0.10, "ltv": 0.90,
            "plazo_meses": 60, "tasa_anual": 0.065,
            "arriendo_uf": 22.0, "cuota_ingreso_ratio": 0.35,
        }
        activo = {
            "direccion": "Test 123", "comuna": "Padre hurtado",
            "precio_uf": 4500, "buffer_pct": 0.15,
            "renta_mensual_uf": 22.0, "opex_mensual_uf": 3.5,
            "antiguedad_anos": 5, "fase_economica": "NORMAL", "trimestre": "Q1",
            "estado_fisico": 8, "cumplimiento_legal": 10, "riesgo_sismico": 7,
            "conectividad": 7, "servicios": 7,
            "velocidad_absorcion": 7, "demanda_zona": 7,
            "renta_cliente_uf": 24.0,
        }
        datos_plusvalor = {
            "valor_activo": 4500, "pie_uf": 450, "meta_uf": 900,
            "cuota_propio": 32.0, "ingreso_uf": 100.0, "ipv": 0.03,
        }
        r = run_admission(
            postulante, activo=activo,
            cliente_credit=cliente_credit,
            datos_plusvalor=datos_plusvalor,
        )
        # Todos los módulos presentes
        assert r["credit_score"] is not None
        assert r["asset_score"] is not None
        assert r["matrix"] is not None
        assert r["plusvalor"] is not None
        assert r["gates"]["all_pass"] is True
        # Metadata refleja módulos activos
        mods = r["metadata"]["modules_enabled"]
        assert mods["credit_score"] is True
        assert mods["asset_score"] is True
        assert mods["matrix"] is True
        assert mods["plusvalor"] is True

    def test_run_admission_sin_modulos_opcionales(self):
        """Backward compatible: sin credit, asset, plusvalor, stress"""
        postulante = {
            "nombre": "Test", "pd": 0.05, "pie": 0.10,
            "ratio": 0.35, "tipo": 1, "cr_acido": 1.5, "cv": 0.01,
        }
        r = run_admission(postulante)
        assert r["credit_score"] is None
        assert r["asset_score"] is None
        assert r["matrix"] is None
        assert r["plusvalor"] is None
        assert r["stress_test"] is None
        # Gates y matching siguen funcionando
        assert len(r["gates"]["detalle"]) == 3
        assert len(r["matching"]["top5"]) == 5


class TestStressTest:
    """Tests para stress_test.py"""

    def test_import(self):
        from stress_test import run_stress_test, get_tramo, aplicar_haircut, ESCALA

    def test_get_tramo_bajo(self):
        from stress_test import get_tramo
        t = get_tramo(100)
        assert t["cuota_max"] == 0.20
        assert t["egreso_max"] == 0.55
        assert t["leverage_max"] == 60

    def test_get_tramo_medio(self):
        from stress_test import get_tramo
        t = get_tramo(534)
        assert t["cuota_max"] == 0.30
        assert t["score_min"] == 488
        assert t["score_max"] == 534

    def test_get_tramo_alto(self):
        from stress_test import get_tramo
        t = get_tramo(850)
        assert t["cuota_max"] == 0.40
        assert t["egreso_max"] == 0.65
        assert t["leverage_max"] == 65

    def test_get_tramo_fuera_rango(self):
        from stress_test import get_tramo
        t = get_tramo(0)
        assert t["cuota_max"] == 0.20  # más restrictivo

    def test_haircut_dependiente(self):
        from stress_test import aplicar_haircut
        resultado = aplicar_haircut(1_000_000, 1)
        assert resultado == 900_000  # -10%

    def test_haircut_independiente(self):
        from stress_test import aplicar_haircut
        resultado = aplicar_haircut(1_000_000, 0)
        assert resultado == 850_000  # -15%

    def test_montecinos_flag_comite(self):
        """Montecinos: score 534, C/I 33.9% > 30% tramo → flag, no rechazo"""
        from stress_test import run_stress_test
        r = run_stress_test(cuota=1_155_384, ingreso=3_410_985, score=534, tipo=1)
        assert r["decision"]["ci_en_tramo"] is False  # flag comité
        assert r["decision"]["hard_gate_stress"] is True  # pasa hard gate

    def test_montecinos_stress_bajo_45(self):
        """Montecinos estresado: 37.6% < 45%"""
        from stress_test import run_stress_test
        r = run_stress_test(cuota=1_155_384, ingreso=3_410_985, score=534, tipo=1)
        assert r["stress"]["ratio_ci_estresado"] < 0.45
        assert r["stress"]["pasa_hard_gate"] is True

    def test_pablo_flag_comite(self):
        """Pablo: score ~100, C/I 24.6% > 20% tramo → flag"""
        from stress_test import run_stress_test
        r = run_stress_test(cuota=246_000, ingreso=1_000_000, score=100, tipo=0)
        assert r["decision"]["ci_en_tramo"] is False

    def test_pablo_stress_pasa(self):
        """Pablo: estresado 28.9% < 45% (lo mata CR_ácido, no stress)"""
        from stress_test import run_stress_test
        r = run_stress_test(cuota=246_000, ingreso=1_000_000, score=100, tipo=0)
        assert r["stress"]["pasa_hard_gate"] is True

    def test_hard_gate_rechaza(self):
        """C/I muy alto + haircut → supera 45% → RECHAZADO"""
        from stress_test import run_stress_test
        # cuota/ingreso = 42%, post haircut indep = 42/0.85 = 49.4% > 45%
        r = run_stress_test(cuota=420_000, ingreso=1_000_000, score=500, tipo=0)
        assert r["stress"]["pasa_hard_gate"] is False
        assert "RECHAZADO" in r["decision"]["resumen"]

    def test_score_alto_cuota_baja_aprobado(self):
        """Score alto, C/I bajo: aprobado limpio"""
        from stress_test import run_stress_test
        r = run_stress_test(cuota=300_000, ingreso=1_000_000, score=850, tipo=1)
        assert r["decision"]["ci_en_tramo"] is True  # 30% ≤ 40%
        assert r["decision"]["hard_gate_stress"] is True
        assert "APROBADO" in r["decision"]["resumen"]

    def test_escala_graduada_monotona(self):
        """Cuota max crece con score (monotonía)"""
        from stress_test import ESCALA
        prev_max = 0
        for row in ESCALA:
            assert row[3] >= prev_max, f"Cuota max no es monótona en tramo {row[0]}-{row[1]}"
            prev_max = row[3]

    def test_egreso_incluido(self):
        """Si se pasa egreso_total, se evalúa contra tramo"""
        from stress_test import run_stress_test
        r = run_stress_test(
            cuota=300_000, ingreso=1_000_000, score=534, tipo=1,
            egreso_total=500_000,
        )
        assert r["pre_estres"]["egreso_tramo"] is not None
        assert r["pre_estres"]["egreso_tramo"]["ratio_egreso"] == 0.5

    def test_integracion_engine(self):
        """Stress test integrado en run_admission"""
        postulante = {
            "nombre": "Test", "pd": 0.05, "pie": 0.10,
            "ratio": 0.35, "tipo": 1, "cr_acido": 1.5, "cv": 0.01,
        }
        stress_input = {
            "cuota": 1_000_000, "ingreso": 3_000_000, "score": 534, "tipo": 1,
        }
        r = run_admission(postulante, stress_input=stress_input)
        assert r["stress_test"] is not None
        assert r["stress_test"]["decision"]["hard_gate_stress"] is True
        assert r["metadata"]["modules_enabled"]["stress_test"] is True

    def test_sin_stress_backward_compatible(self):
        """Sin stress_input → stress_test = None"""
        postulante = {
            "nombre": "Test", "pd": 0.05, "pie": 0.10,
            "ratio": 0.35, "tipo": 1, "cr_acido": 1.5, "cv": 0.01,
        }
        r = run_admission(postulante)
        assert r["stress_test"] is None
