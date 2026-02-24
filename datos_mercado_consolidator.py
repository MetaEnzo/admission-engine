"""
PROPIO — DATOS_MERCADO Consolidator v1.0
=========================================
Consolida datos de múltiples tasaciones por comuna para generar/actualizar DATOS_MERCADO.

Pipeline:
  tasacion_extractor.py → [extractions per PDF] → consolidator → DATOS_MERCADO update

Lógica:
  - Agrupa extracciones por comuna
  - Promedia campos cuantitativos (QSD, Vol, Cap Rate, scores)
  - Cuenta acumulados (Trx total CBR, Stk total ofertas)
  - Marca campos con fuente insuficiente
  - Output: dict compatible con DATOS_MERCADO en asset_credit_score.py

Dependencias: tasacion_extractor.py
"""

import json
import math
import hashlib
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from tasacion_extractor import extract_tasacion


# ============================================================
# ZONA MAPPING (de texto/ubicación a zona DATOS_MERCADO)
# ============================================================
ZONA_POR_COMUNA = {
    "san bernardo": "Sur",
    "maipu": "Poniente",
    "maipú": "Poniente",
    "la florida": "Sur-Oriente",
    "puente alto": "Sur",
    "las condes": "Oriente",
    "providencia": "Centro-Oriente",
    "nunoa": "Centro-Oriente",
    "ñuñoa": "Centro-Oriente",
    "la reina": "Oriente",
    "vitacura": "Oriente",
    "santiago centro": "Centro",
    "santiago": "Centro",
    "quilicura": "Norte",
    "estacion central": "Poniente",
    "estación central": "Poniente",
    "padre hurtado": "Poniente",
    "independencia": "Norte",
    "maule": "Región",
    "iquique": "Norte Grande",
    "pudahuel": "Poniente",
    "renca": "Norte",
    "lo barnechea": "Oriente",
    "peñalolen": "Sur-Oriente",
    "peñalolén": "Sur-Oriente",
    "macul": "Sur-Oriente",
    "la cisterna": "Sur",
    "san miguel": "Sur",
    "cerrillos": "Poniente",
    "pedro aguirre cerda": "Sur",
    "lo espejo": "Sur",
    "la granja": "Sur",
    "el bosque": "Sur",
    "la pintana": "Sur",
    "san joaquin": "Sur",
    "san joaquín": "Sur",
    "recoleta": "Norte",
    "huechuraba": "Norte",
    "conchali": "Norte",
    "conchalí": "Norte",
    "cerro navia": "Poniente",
    "lo prado": "Poniente",
    "quinta normal": "Poniente",
}

# Riesgo por zona (default, puede ser overridden por tasación)
RIESGO_POR_ZONA = {
    "Oriente": "Muy Bajo",
    "Centro-Oriente": "Bajo",
    "Centro": "Bajo",
    "Poniente": "Medio",
    "Sur-Oriente": "Bajo",
    "Sur": "Medio",
    "Norte": "Medio-Alto",
    "Norte Grande": "Medio",
    "Región": "Medio",
}


def _safe_mean(values):
    """Media de valores no-None."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _safe_sum(values):
    """Suma de valores no-None."""
    valid = [v for v in values if v is not None]
    return sum(valid) if valid else 0


def consolidate_comuna(extractions):
    """
    Consolida múltiples extracciones de tasación para una comuna.

    Args:
        extractions: lista de dicts (output de extract_tasacion)

    Returns:
        dict compatible con DATOS_MERCADO format
    """
    if not extractions:
        return None

    n = len(extractions)
    comuna_raw = extractions[0]['identificacion'].get('comuna', 'Unknown')
    comuna_key = comuna_raw.lower().strip()

    # Recolectar valores por campo
    qsd_values = []
    vol_values = []
    cap_values = []
    trx_total = 0
    stk_total = 0

    # Scores cualitativos (promediados)
    scores = defaultdict(list)

    for ext in extractions:
        dm = ext.get('datos_mercado_derivados', {})

        if dm.get('qsd') is not None:
            qsd_values.append(dm['qsd'])
        if dm.get('vol') is not None:
            vol_values.append(dm['vol'])
        if dm.get('cap_rate') is not None:
            cap_values.append(dm['cap_rate'])

        # Trx y Stk: acumulados (cada tasación trae sus propias refs)
        refs = ext.get('referencias', {})
        trx_total += refs.get('n_referencias_cbr', 0)
        stk_total += refs.get('n_referencias_oferta', 0)

        # Scores
        for key in ['desarrollo_urbano', 'interes_sector', 'nivel_socioeconomico',
                     'accesibilidad', 'localizacion', 'estado_conservacion',
                     'grado_liquidez', 'oferta', 'demanda']:
            val = dm.get(key)
            if val is not None:
                scores[key].append(val)

    # Construir resultado
    qsd = round(_safe_mean(qsd_values), 4) if qsd_values else None
    vol = round(_safe_mean(vol_values), 4) if vol_values else None
    cap_mean = _safe_mean(cap_values)

    # Zona
    zona = ZONA_POR_COMUNA.get(comuna_key, "Desconocida")
    riesgo = RIESGO_POR_ZONA.get(zona, "Medio")

    # Cap rate min/max: si solo una tasación, usar ±10% del cap rate
    if cap_mean:
        cap_min = round(cap_mean * 0.9, 3)
        cap_max = round(cap_mean * 1.1, 3)
    else:
        cap_min = None
        cap_max = None

    # ICVU, ISMT, IPS: derivar de scores cualitativos
    # Escala 0-100. Mapeo: score 1-10 → 10-90
    def score_to_index(score_list, name):
        mean = _safe_mean(score_list)
        if mean is None:
            return None
        return int(round(mean * 10))

    icvu = score_to_index(
        scores.get('localizacion', []) + scores.get('desarrollo_urbano', []),
        'ICVU'
    )
    ismt = score_to_index(
        scores.get('accesibilidad', []) + scores.get('interes_sector', []),
        'ISMT'
    )
    ips = score_to_index(
        scores.get('nivel_socioeconomico', []),
        'IPS'
    )

    # Resultado formato DATOS_MERCADO
    datos_mercado = {
        "dts": None,  # Requiere fuente externa
        "qsd": qsd,
        "vol": vol,
        "trx": trx_total,
        "stk": stk_total,
        "cap_min": cap_min,
        "cap_max": cap_max,
        "icvu": icvu,
        "ismt": ismt,
        "ips": ips,
        "zona": zona,
        "riesgo": riesgo,
    }

    # Metadata de consolidación
    consolidation_meta = {
        "comuna": comuna_raw,
        "n_tasaciones": n,
        "campos_con_dato": sum(1 for v in datos_mercado.values() if v is not None),
        "campos_totales": len(datos_mercado),
        "campos_faltantes": [k for k, v in datos_mercado.items() if v is None],
        "scores_cualitativos": {k: round(_safe_mean(v), 1) for k, v in scores.items() if v},
        "timestamp": datetime.now().isoformat(),
    }

    return {
        "datos_mercado": datos_mercado,
        "consolidation_meta": consolidation_meta,
    }


def process_folder(folder_path, pattern="*.pdf"):
    """
    Procesa todos los PDFs de tasación en una carpeta.

    Args:
        folder_path: ruta a carpeta con PDFs
        pattern: glob pattern

    Returns:
        dict: {comuna: consolidation_result}
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"No es directorio: {folder}")

    pdfs = sorted(folder.glob(pattern))
    if not pdfs:
        print(f"No se encontraron PDFs en {folder}")
        return {}

    # Extraer cada PDF
    extractions_by_comuna = defaultdict(list)
    errors = []

    for pdf_path in pdfs:
        try:
            result = extract_tasacion(pdf_path)
            comuna = result['identificacion'].get('comuna', 'Unknown')
            extractions_by_comuna[comuna].append(result)
            print(f"  ✓ {pdf_path.name} → {comuna}")
        except Exception as e:
            errors.append({"file": str(pdf_path.name), "error": str(e)})
            print(f"  ✗ {pdf_path.name} → ERROR: {e}")

    # Consolidar por comuna
    results = {}
    for comuna, extractions in extractions_by_comuna.items():
        consolidated = consolidate_comuna(extractions)
        if consolidated:
            results[comuna] = consolidated
            meta = consolidated['consolidation_meta']
            dm = consolidated['datos_mercado']
            print(f"\n  {comuna}: {meta['n_tasaciones']} tasaciones → {meta['campos_con_dato']}/{meta['campos_totales']} campos")
            if meta['campos_faltantes']:
                print(f"    Faltantes: {', '.join(meta['campos_faltantes'])}")

    return {
        "comunas": results,
        "processing_meta": {
            "total_pdfs": len(pdfs),
            "total_comunas": len(results),
            "errors": errors,
            "timestamp": datetime.now().isoformat(),
        }
    }


def generate_datos_mercado_update(consolidated, existing_datos=None):
    """
    Genera el dict DATOS_MERCADO listo para actualizar asset_credit_score.py.

    Args:
        consolidated: output de process_folder
        existing_datos: DATOS_MERCADO dict existente (para merge)

    Returns:
        dict: DATOS_MERCADO actualizado + change log
    """
    updated = dict(existing_datos) if existing_datos else {}
    changes = []

    for comuna, data in consolidated.get('comunas', {}).items():
        dm = data['datos_mercado']
        comuna_lower = comuna.lower().strip()

        if comuna_lower in updated:
            # Actualizar campos con dato (no sobreescribir con None)
            old = updated[comuna_lower]
            for key, new_val in dm.items():
                if new_val is not None:
                    old_val = old.get(key)
                    if old_val != new_val:
                        changes.append({
                            "comuna": comuna,
                            "field": key,
                            "old": old_val,
                            "new": new_val,
                            "source": "tasación_pdf",
                        })
                    old[key] = new_val
        else:
            # Comuna nueva — insertar solo campos con dato
            new_entry = {k: v for k, v in dm.items() if v is not None}
            updated[comuna_lower] = new_entry
            changes.append({
                "comuna": comuna,
                "field": "NEW_COMUNA",
                "old": None,
                "new": new_entry,
                "source": "tasación_pdf",
            })

    return {
        "datos_mercado": updated,
        "changes": changes,
        "n_changes": len(changes),
    }


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Uso: python datos_mercado_consolidator.py <carpeta_pdfs> [output.json]")
        print("  Procesa todos los PDFs de tasación en la carpeta y genera DATOS_MERCADO consolidado")
        sys.exit(1)

    folder = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "datos_mercado_consolidated.json"

    print(f"Procesando PDFs en: {folder}")
    result = process_folder(folder)

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nResultado guardado en: {output}")
    print(f"Comunas procesadas: {result['processing_meta']['total_comunas']}")
    if result['processing_meta']['errors']:
        print(f"Errores: {len(result['processing_meta']['errors'])}")
