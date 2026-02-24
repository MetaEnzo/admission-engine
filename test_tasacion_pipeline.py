"""
Tests para tasacion_extractor.py y datos_mercado_consolidator.py
================================================================
Usa el PDF de referencia: Tasación Pudahuel (Transsa format)
"""

import pytest
import math
import os
from pathlib import Path

from tasacion_extractor import (
    extract_tasacion, _to_float, _normalize,
    ESTADO_CONSERVACION, CALIDAD_MATERIAL, DESARROLLO_URBANO,
    INTERES_SECTOR, NIVEL_SOCIOECONOMICO, ACCESIBILIDAD, LOCALIZACION,
    GRADO_LIQUIDEZ, CALIDAD_GARANTIA, OFERTA_DEMANDA,
)
from datos_mercado_consolidator import (
    consolidate_comuna, generate_datos_mercado_update,
    ZONA_POR_COMUNA, RIESGO_POR_ZONA,
)


# ============================================================
# _to_float — formato numérico chileno
# ============================================================
class TestToFloat:
    """Formato numérico chileno: puntos como miles, comas como decimales."""

    def test_multiples_puntos_miles(self):
        assert _to_float("290.392.385") == 290392385

    def test_un_punto_tres_digitos_miles(self):
        """7.725 → 7725 (separador de miles, no decimal)"""
        assert _to_float("7.725") == 7725

    def test_700_mil(self):
        assert _to_float("700.000") == 700000

    def test_7_mil(self):
        assert _to_float("7.000") == 7000

    def test_coma_decimal(self):
        assert abs(_to_float("99,13") - 99.13) < 0.01

    def test_coma_decimal_dos_digitos(self):
        assert abs(_to_float("14,00") - 14.0) < 0.01

    def test_cero_punto_decimal(self):
        """0.048 → 0.048 (decimal, no miles porque empieza con 0)"""
        assert abs(_to_float("0.048") - 0.048) < 0.001

    def test_punto_y_coma_mixto(self):
        """37.593,51 → 37593.51"""
        assert abs(_to_float("37.593,51") - 37593.51) < 0.01

    def test_none(self):
        assert _to_float(None) is None

    def test_empty(self):
        assert _to_float("") is None

    def test_whitespace(self):
        assert _to_float("  ") is None

    def test_text(self):
        assert _to_float("abc") is None

    def test_negative(self):
        assert _to_float("-5.000") == -5000

    def test_simple_decimal(self):
        assert abs(_to_float("14.5") - 14.5) < 0.01


# ============================================================
# _normalize
# ============================================================
class TestNormalize:
    def test_basic(self):
        assert _normalize("  Muy Bueno  ") == "muy bueno"

    def test_none(self):
        assert _normalize(None) == ""

    def test_extra_spaces(self):
        assert _normalize("  medio   alto  ") == "medio alto"


# ============================================================
# Mapeos cualitativos
# ============================================================
class TestQualitativeMappings:
    """Verifica que los mapeos cubren los valores comunes de Transsa."""

    def test_estado_conservacion_covers_transsa(self):
        assert "muy bueno" in ESTADO_CONSERVACION
        assert "bueno" in ESTADO_CONSERVACION
        assert "regular" in ESTADO_CONSERVACION
        assert "nuevo" in ESTADO_CONSERVACION

    def test_calidad_material_covers_transsa(self):
        assert "superior" in CALIDAD_MATERIAL
        assert "buena" in CALIDAD_MATERIAL
        assert "media" in CALIDAD_MATERIAL

    def test_desarrollo_urbano_covers_transsa(self):
        assert "consolidado" in DESARROLLO_URBANO
        assert "creciente" in DESARROLLO_URBANO
        assert "incipiente" in DESARROLLO_URBANO

    def test_scores_range_1_10(self):
        for mapping in [ESTADO_CONSERVACION, CALIDAD_MATERIAL, DESARROLLO_URBANO,
                        INTERES_SECTOR, NIVEL_SOCIOECONOMICO, ACCESIBILIDAD,
                        LOCALIZACION, GRADO_LIQUIDEZ, CALIDAD_GARANTIA, OFERTA_DEMANDA]:
            for key, val in mapping.items():
                assert 1 <= val <= 10, f"{key}: {val} fuera de rango"


# ============================================================
# Extractor — requiere PDF de referencia
# ============================================================
# Path al PDF de test (se busca en uploads o en carpeta de test)
TEST_PDF = None
for candidate in [
    "/sessions/charming-awesome-ramanujan/mnt/uploads/Tasación_L15008-24-13_COT254L-24.pdf",
    "test_data/tasacion_pudahuel.pdf",
]:
    if Path(candidate).exists():
        TEST_PDF = candidate
        break


@pytest.mark.skipif(TEST_PDF is None, reason="PDF de referencia no encontrado")
class TestExtractor:
    """Tests contra el PDF de referencia de Pudahuel."""

    @pytest.fixture(scope="class")
    def extraction(self):
        return extract_tasacion(TEST_PDF)

    # --- Identificación ---
    def test_comuna(self, extraction):
        assert extraction['identificacion']['comuna'] == 'Pudahuel'

    def test_tipo_propiedad(self, extraction):
        assert 'Casa' in extraction['identificacion']['tipo_propiedad']

    def test_ano_construccion(self, extraction):
        assert extraction['identificacion']['ano_construccion'] == 2024

    def test_vida_util(self, extraction):
        assert extraction['identificacion']['vida_util_remanente'] == 80

    def test_region(self, extraction):
        assert 'Metropolitana' in extraction['identificacion']['region']

    # --- Sinopsis ---
    def test_calidad_garantia(self, extraction):
        assert extraction['sinopsis']['calidad_garantia'] == 'aceptable'
        assert extraction['sinopsis']['calidad_garantia_score'] == 7

    def test_grado_liquidez(self, extraction):
        assert extraction['sinopsis']['grado_liquidez'] == 'alto'
        assert extraction['sinopsis']['grado_liquidez_score'] == 8

    def test_tasacion_pesos(self, extraction):
        assert extraction['sinopsis']['tasacion_pesos'] == 290392385.0

    def test_tasacion_uf(self, extraction):
        assert extraction['sinopsis']['tasacion_uf'] == 7725.0

    def test_arriendo(self, extraction):
        assert extraction['sinopsis']['arriendo_mensual'] == 700000.0

    # --- Referencias ---
    def test_cbr_refs_positive(self, extraction):
        assert extraction['referencias']['n_referencias_cbr'] >= 1

    def test_oferta_refs_positive(self, extraction):
        assert extraction['referencias']['n_referencias_oferta'] >= 1

    def test_qsd_range(self, extraction):
        qsd = extraction['referencias']['qsd_estimado']
        assert 0.05 <= qsd <= 0.15, f"QSD {qsd} fuera de rango esperado"

    def test_promedio_cbr_exists(self, extraction):
        assert extraction['referencias']['promedio_cbr']
        assert extraction['referencias']['promedio_cbr']['uf_m2_terreno'] > 0

    def test_promedio_oferta_exists(self, extraction):
        assert extraction['referencias']['promedio_oferta']

    # --- Valorización ---
    def test_superficie_terreno(self, extraction):
        assert abs(extraction['valorizacion']['superficie_terreno'] - 261.35) < 1.0

    def test_uf_m2_construccion(self, extraction):
        assert abs(extraction['valorizacion']['uf_m2_construccion'] - 39.5) < 0.5

    # --- Construcción ---
    def test_estado_conservacion(self, extraction):
        assert extraction['construccion']['estado_conservacion'] in ['muy bueno', 'bueno']
        assert extraction['construccion']['estado_conservacion_score'] >= 7

    def test_calidad_material(self, extraction):
        assert extraction['construccion']['calidad_material'] == 'superior'
        assert extraction['construccion']['calidad_material_score'] == 9

    def test_estructura_principal(self, extraction):
        assert 'Albañilería' in extraction['construccion']['estructura_principal']

    def test_materialidad_solida(self, extraction):
        assert extraction['construccion']['materialidad'] == 'Sólida'

    # --- Sector ---
    def test_desarrollo_urbano(self, extraction):
        assert extraction['sector']['desarrollo_urbano'] == 'creciente'
        assert extraction['sector']['desarrollo_urbano_score'] == 7

    def test_interes_sector(self, extraction):
        assert extraction['sector']['interes_sector'] == 'alto'
        assert extraction['sector']['interes_sector_score'] == 8

    def test_nivel_socioeconomico(self, extraction):
        assert extraction['sector']['nivel_socioeconomico'] == 'medio-alto'
        assert extraction['sector']['nivel_socioeconomico_score'] == 7

    def test_accesibilidad(self, extraction):
        assert extraction['sector']['accesibilidad'] == 'muy buena'
        assert extraction['sector']['accesibilidad_score'] == 9

    def test_localizacion(self, extraction):
        assert extraction['sector']['localizacion'] == 'muy buena'

    def test_edad_media_sector(self, extraction):
        assert extraction['sector']['edad_media_sector'] == 10

    def test_tipo_area_urbana(self, extraction):
        assert extraction['sector']['tipo_area'] == 'Urbana'

    # --- Terreno ---
    def test_terreno_superficie(self, extraction):
        assert abs(extraction['terreno']['superficie_terreno'] - 261.35) < 1.0

    def test_terreno_topografia(self, extraction):
        assert extraction['terreno']['topografia'] == 'Plana'

    def test_terreno_forma(self, extraction):
        assert extraction['terreno']['forma_terreno'] == 'Regular'

    # --- DATOS_MERCADO derivados ---
    def test_dm_comuna(self, extraction):
        assert extraction['datos_mercado_derivados']['comuna'] == 'Pudahuel'

    def test_dm_qsd(self, extraction):
        qsd = extraction['datos_mercado_derivados']['qsd']
        assert 0.05 <= qsd <= 0.15

    def test_dm_cap_rate(self, extraction):
        cap = extraction['datos_mercado_derivados']['cap_rate']
        assert cap is not None
        assert 0.01 < cap < 0.10

    def test_dm_dts_missing(self, extraction):
        assert extraction['datos_mercado_derivados']['dts'] is None

    def test_dm_scores_populated(self, extraction):
        dm = extraction['datos_mercado_derivados']
        for key in ['desarrollo_urbano', 'interes_sector', 'nivel_socioeconomico',
                     'accesibilidad', 'localizacion', 'estado_conservacion']:
            assert dm[key] is not None, f"{key} should not be None"
            assert 1 <= dm[key] <= 10

    # --- Metadata ---
    def test_metadata_version(self, extraction):
        assert extraction['metadata']['extractor_version'] == 'tasacion_extractor_v1.0'

    def test_metadata_format(self, extraction):
        assert extraction['metadata']['formato'] == 'Transsa'

    def test_metadata_hash(self, extraction):
        assert len(extraction['metadata']['input_hash']) == 16

    def test_metadata_cobertura(self, extraction):
        assert extraction['metadata']['cobertura'] >= 0.80

    # --- Confianza ---
    def test_confianza_no_missing_critical(self, extraction):
        """Los campos críticos deben estar extraídos."""
        conf = extraction['confianza']
        assert conf['qsd'] != 'MISSING'
        assert conf['estado_conservacion'] != 'MISSING'
        assert conf['grado_liquidez'] != 'MISSING'


# ============================================================
# Consolidator
# ============================================================
class TestConsolidator:
    """Tests del consolidador de comunas."""

    def _make_extraction(self, comuna="TestComuna", qsd=0.07, vol=0.05,
                         cap_rate=0.05, trx=3, stk=5, scores=None):
        """Helper para crear extracciones mock."""
        s = scores or {}
        return {
            'identificacion': {'comuna': comuna},
            'sinopsis': {},
            'referencias': {
                'n_referencias_cbr': trx,
                'n_referencias_oferta': stk,
            },
            'datos_mercado_derivados': {
                'qsd': qsd,
                'vol': vol,
                'cap_rate': cap_rate,
                'desarrollo_urbano': s.get('desarrollo_urbano', 7),
                'interes_sector': s.get('interes_sector', 7),
                'nivel_socioeconomico': s.get('nivel_socioeconomico', 5),
                'accesibilidad': s.get('accesibilidad', 7),
                'localizacion': s.get('localizacion', 7),
                'estado_conservacion': s.get('estado_conservacion', 7),
                'grado_liquidez': s.get('grado_liquidez', 7),
                'oferta': s.get('oferta', 5),
                'demanda': s.get('demanda', 5),
            },
        }

    def test_single_extraction(self):
        ext = self._make_extraction(qsd=0.065)
        result = consolidate_comuna([ext])
        assert result is not None
        assert result['datos_mercado']['qsd'] == 0.065

    def test_multiple_extractions_average_qsd(self):
        ext1 = self._make_extraction(qsd=0.06)
        ext2 = self._make_extraction(qsd=0.08)
        result = consolidate_comuna([ext1, ext2])
        assert abs(result['datos_mercado']['qsd'] - 0.07) < 0.001

    def test_trx_accumulated(self):
        ext1 = self._make_extraction(trx=3)
        ext2 = self._make_extraction(trx=5)
        result = consolidate_comuna([ext1, ext2])
        assert result['datos_mercado']['trx'] == 8

    def test_stk_accumulated(self):
        ext1 = self._make_extraction(stk=5)
        ext2 = self._make_extraction(stk=10)
        result = consolidate_comuna([ext1, ext2])
        assert result['datos_mercado']['stk'] == 15

    def test_cap_rate_range(self):
        ext = self._make_extraction(cap_rate=0.055)
        result = consolidate_comuna([ext])
        dm = result['datos_mercado']
        assert dm['cap_min'] < dm['cap_max']
        assert dm['cap_min'] == round(0.055 * 0.9, 3)
        assert dm['cap_max'] == round(0.055 * 1.1, 3)

    def test_dts_always_none(self):
        """DTS no se puede derivar de tasaciones."""
        ext = self._make_extraction()
        result = consolidate_comuna([ext])
        assert result['datos_mercado']['dts'] is None

    def test_zona_mapping(self):
        ext = self._make_extraction(comuna="Pudahuel")
        result = consolidate_comuna([ext])
        assert result['datos_mercado']['zona'] == 'Poniente'

    def test_riesgo_mapping(self):
        ext = self._make_extraction(comuna="Pudahuel")
        result = consolidate_comuna([ext])
        assert result['datos_mercado']['riesgo'] == 'Medio'

    def test_empty_list(self):
        assert consolidate_comuna([]) is None

    def test_meta_n_tasaciones(self):
        ext1 = self._make_extraction()
        ext2 = self._make_extraction()
        result = consolidate_comuna([ext1, ext2])
        assert result['consolidation_meta']['n_tasaciones'] == 2

    def test_none_values_not_overwrite(self):
        ext = self._make_extraction(cap_rate=None)
        result = consolidate_comuna([ext])
        assert result['datos_mercado']['cap_min'] is None
        assert result['datos_mercado']['cap_max'] is None


# ============================================================
# generate_datos_mercado_update
# ============================================================
class TestDatosMercadoUpdate:

    def test_new_comuna(self):
        consolidated = {
            'comunas': {
                'NuevaComuna': {
                    'datos_mercado': {
                        'qsd': 0.07, 'vol': 0.05, 'trx': 3, 'stk': 5,
                        'cap_min': 0.05, 'cap_max': 0.06,
                        'icvu': 50, 'ismt': 60, 'ips': 40,
                        'zona': 'Sur', 'riesgo': 'Medio', 'dts': None,
                    }
                }
            }
        }
        result = generate_datos_mercado_update(consolidated, {})
        assert 'nuevacomuna' in result['datos_mercado']
        assert result['n_changes'] == 1

    def test_update_existing(self):
        existing = {
            'pudahuel': {'qsd': 0.065, 'vol': 0.018, 'trx': 10}
        }
        consolidated = {
            'comunas': {
                'Pudahuel': {
                    'datos_mercado': {'qsd': 0.075, 'vol': None, 'trx': 3,
                                     'dts': None, 'stk': 5,
                                     'cap_min': None, 'cap_max': None,
                                     'icvu': None, 'ismt': None, 'ips': None,
                                     'zona': None, 'riesgo': None}
                }
            }
        }
        result = generate_datos_mercado_update(consolidated, existing)
        dm = result['datos_mercado']['pudahuel']
        # QSD updated
        assert dm['qsd'] == 0.075
        # Vol NOT overwritten (new is None)
        assert dm['vol'] == 0.018
        # Trx updated
        assert dm['trx'] == 3

    def test_no_overwrite_with_none(self):
        existing = {'test': {'dts': 65, 'qsd': 0.07}}
        consolidated = {
            'comunas': {
                'Test': {
                    'datos_mercado': {'dts': None, 'qsd': 0.08,
                                     'vol': None, 'trx': None, 'stk': None,
                                     'cap_min': None, 'cap_max': None,
                                     'icvu': None, 'ismt': None, 'ips': None,
                                     'zona': None, 'riesgo': None}
                }
            }
        }
        result = generate_datos_mercado_update(consolidated, existing)
        assert result['datos_mercado']['test']['dts'] == 65  # Preserved


# ============================================================
# Zona mapping completeness
# ============================================================
class TestZonaMapping:
    def test_all_existing_comunas_have_zona(self):
        from asset_credit_score import DATOS_MERCADO
        for comuna in DATOS_MERCADO:
            assert comuna.lower() in ZONA_POR_COMUNA, f"Comuna {comuna} sin zona mapping"

    def test_zona_risk_mapping_complete(self):
        zones_used = set(ZONA_POR_COMUNA.values())
        for zona in zones_used:
            assert zona in RIESGO_POR_ZONA, f"Zona {zona} sin riesgo mapping"
