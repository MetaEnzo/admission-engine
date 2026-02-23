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
        """Independiente no tiene gate duro de CV"""
        post = {"pd": 0.05, "pie": 0.10, "ratio": 0.35, "tipo": 0,
                "cr_acido": 1.5, "cv": 0.50}
        gates = evaluar_gates(post)
        cv_gate = next(g for g in gates if "CV" in g["nombre"])
        assert cv_gate["pass"] is True

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
        assert r["metadata"]["engine"] == "propio_admission_v2.2"
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
