"""
PROPIO — Tasación PDF Extractor v1.0
=====================================
Extrae campos de tasaciones en formato Transsa para alimentar DATOS_MERCADO.

Pipeline:
  1. pdfplumber extrae tablas + texto (determinístico)
  2. Campos cuantitativos → directos
  3. Campos cualitativos → mapeo determinístico a escala numérica
  4. Output: dict con todos los campos + metadata + confianza

Formato soportado: Transsa (8 páginas estándar)
Dependencias: pdfplumber
"""

import re
import math
import json
import hashlib
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    raise ImportError("pdfplumber requerido: pip install pdfplumber --break-system-packages")


# ============================================================
# MAPEOS CUALITATIVOS → NUMÉRICOS
# Escala 1-10 alineada con asset_credit_score.py
# ============================================================

ESTADO_CONSERVACION = {
    "muy bueno": 9, "bueno": 7, "regular": 5,
    "malo": 3, "muy malo": 1, "nuevo": 10,
}

CALIDAD_MATERIAL = {
    "superior": 9, "buena": 7, "media": 5, "economica": 3,
    "económica": 3, "muy buena": 8, "regular": 5,
}

DESARROLLO_URBANO = {
    "consolidado": 9, "creciente": 7, "incipiente": 5,
    "estancado": 3, "en deterioro": 1,
}

INTERES_SECTOR = {
    "muy alto": 10, "alto": 8, "medio": 5, "bajo": 3, "muy bajo": 1,
}

NIVEL_SOCIOECONOMICO = {
    "alto": 9, "medio-alto": 7, "medio": 5, "medio-bajo": 3, "bajo": 1,
}

ACCESIBILIDAD = {
    "muy buena": 9, "buena": 7, "media": 5, "regular": 4,
    "mala": 2, "muy mala": 1,
}

LOCALIZACION = {
    "muy buena": 9, "buena": 7, "media": 5, "regular": 4,
    "mala": 2, "muy mala": 1,
}

GRADO_LIQUIDEZ = {
    "muy alto": 10, "alto": 8, "medio": 5, "bajo": 3, "muy bajo": 1,
}

CALIDAD_GARANTIA = {
    "excelente": 10, "muy buena": 9, "aceptable": 7,
    "regular": 5, "deficiente": 3, "inaceptable": 1,
}

OFERTA_DEMANDA = {
    "muy alta": 10, "alta": 8, "mediana": 5, "media": 5,
    "baja": 3, "muy baja": 1,
}


def _normalize(text):
    """Normaliza texto: lowercase, strip, elimina acentos comunes."""
    if not text:
        return ""
    t = text.strip().lower()
    # Remover caracteres no-ASCII comunes en PDFs mal parseados
    t = re.sub(r'\s+', ' ', t)
    return t


def _to_float(text):
    """Convierte texto a float, maneja formatos chilenos (puntos como miles, comas como decimales).

    Formato chileno:
      290.392.385 → 290392385  (múltiples puntos = separador miles)
      7.725       → 7725       (1 punto + 3 dígitos después = separador miles)
      99,13       → 99.13      (coma = decimal)
      700.000     → 700000     (1 punto + 3 dígitos = separador miles)
      14,00       → 14.0       (coma = decimal)
      0,065       → 0.065      (coma = decimal)
    """
    if not text:
        return None
    t = text.strip().replace(' ', '')
    if not t:
        return None

    # Caso: tiene coma y punto → punto es miles, coma es decimal
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.')
    # Caso: solo coma → decimal
    elif ',' in t:
        t = t.replace(',', '.')
    # Caso: múltiples puntos → todos son miles
    elif t.count('.') > 1:
        t = t.replace('.', '')
    # Caso: exactamente 1 punto → ¿miles o decimal?
    elif t.count('.') == 1:
        parts = t.split('.')
        # Si la parte después del punto tiene exactamente 3 dígitos → separador de miles
        # Ej: "7.725" → 7725, "700.000" → 700000
        # Excepto si la parte antes es "0" → "0.065" es decimal
        if len(parts[1]) == 3 and parts[0] != '0' and parts[0].lstrip('-').isdigit():
            t = t.replace('.', '')
        # Si no, es decimal normal: "14.5" → 14.5

    try:
        return float(t)
    except (ValueError, TypeError):
        return None


def _find_cell(tables, pattern, offset_col=None, offset_row=None):
    """Busca un patrón en las tablas y retorna celdas adyacentes."""
    pat = re.compile(pattern, re.IGNORECASE)
    for table in tables:
        for i, row in enumerate(table):
            for j, cell in enumerate(row):
                if cell and pat.search(cell.strip()):
                    if offset_col is not None:
                        target_j = j + offset_col
                        if 0 <= target_j < len(row) and row[target_j]:
                            return row[target_j].strip()
                    if offset_row is not None:
                        target_i = i + offset_row
                        if 0 <= target_i < len(table) and j < len(table[target_i]):
                            return table[target_i][j].strip() if table[target_i][j] else None
                    return cell.strip()
    return None


def _extract_all_tables(pdf):
    """Extrae tablas de todas las páginas relevantes (1-4)."""
    all_tables = {}
    for page_num in range(min(4, len(pdf.pages))):
        tables = pdf.pages[page_num].extract_tables()
        all_tables[page_num] = tables if tables else []
    return all_tables


# ============================================================
# EXTRACTORES POR SECCIÓN
# ============================================================

def extract_identificacion(tables_p2):
    """Página 2: datos de identificación del inmueble."""
    data = {}

    # Comuna
    for table in tables_p2:
        for row in table:
            for j, cell in enumerate(row):
                if cell and 'Comuna' in cell:
                    # Siguiente celda no vacía
                    for k in range(j + 1, len(row)):
                        if row[k] and row[k].strip():
                            data['comuna'] = row[k].strip()
                            break
                if cell and 'Tipo Propiedad' in cell:
                    for k in range(j + 1, len(row)):
                        if row[k] and row[k].strip() and 'Objetivo' not in row[k]:
                            data['tipo_propiedad'] = row[k].strip()
                            break
                if cell and 'Año Construcción' in cell:
                    for k in range(j + 1, len(row)):
                        if row[k] and row[k].strip():
                            val = _to_float(row[k].strip())
                            if val and val > 1900:
                                data['ano_construccion'] = int(val)
                            break
                if cell and 'Vida' in cell and 'Rem' in str(row):
                    # Vida útil remanente - buscar número en la fila
                    for k in range(len(row)):
                        val = _to_float(row[k]) if row[k] else None
                        if val and 1 <= val <= 200:
                            data['vida_util_remanente'] = int(val)
                if cell and 'Región' in cell and 'XIII' not in str(cell):
                    for k in range(j + 1, len(row)):
                        if row[k] and row[k].strip():
                            data['region'] = row[k].strip()
                            break

    return data


def extract_sinopsis(tables_p2):
    """Página 2: sinopsis y valores globales."""
    data = {}

    for table in tables_p2:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])

            # Calidad de la Garantía
            if 'Calidad de la Garant' in row_str:
                for cell in row:
                    c = _normalize(cell)
                    if c in CALIDAD_GARANTIA:
                        data['calidad_garantia'] = c
                        data['calidad_garantia_score'] = CALIDAD_GARANTIA[c]

            # Grado de Liquidez
            if 'Grado de Liquidez' in row_str or 'Liquidez' in row_str:
                for cell in row:
                    c = _normalize(cell)
                    if c in GRADO_LIQUIDEZ:
                        data['grado_liquidez'] = c
                        data['grado_liquidez_score'] = GRADO_LIQUIDEZ[c]

            # Oferta
            if 'Oferta' in row_str and 'Demanda' in row_str:
                found_oferta = False
                for cell in row:
                    c = _normalize(cell)
                    if c in OFERTA_DEMANDA:
                        if not found_oferta and 'oferta' not in data:
                            data['oferta'] = c
                            data['oferta_score'] = OFERTA_DEMANDA[c]
                            found_oferta = True
                        elif found_oferta:
                            data['demanda'] = c
                            data['demanda_score'] = OFERTA_DEMANDA[c]

    # Valor de tasación (UF + pesos) — tabla dedicada "VALOR DE TASACIÓN"
    for table in tables_p2:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])
            if 'VALOR DE TASACI' in row_str or 'Valor de Tasaci' in row_str:
                nums = [_to_float(c) for c in row if _to_float(c) is not None]
                for val in nums:
                    if 100 < val < 100000:
                        data['tasacion_uf'] = val
                    elif val > 1000000:
                        data['tasacion_pesos'] = val

    # Arriendo mensual — puede venir con formato "700.000" (punto como miles)
    for table in tables_p2:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])
            if 'Arriendo' in row_str:
                for cell in row:
                    if not cell:
                        continue
                    val = _to_float(cell)
                    if val and 50000 < val < 10000000:
                        data['arriendo_mensual'] = val

    # Valor UF del día
    for table in tables_p2:
        for row in table:
            for j, cell in enumerate(row):
                if cell and 'UF' in cell and j + 1 < len(row):
                    val = _to_float(row[j + 1]) if row[j + 1] else None
                    if val and 30000 < val < 50000:
                        data['valor_uf_dia'] = val

    return data


def extract_referencias(tables_p3):
    """Página 3: referencias de mercado (CBR + ofertas publicadas)."""
    data = {
        'referencias_cbr': [],
        'referencias_oferta': [],
        'promedio_cbr': {},
        'promedio_oferta': {},
    }

    current_section = None

    for table in tables_p3:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])

            # Detectar sección
            if 'Promedio de las referencias de venta' in row_str:
                current_section = 'cbr_promedio'
            elif 'Promedio de las referencias de oferta' in row_str:
                current_section = 'oferta_promedio'
            elif 'Valor tasaci' in row_str and 'valoriz' in row_str.lower():
                current_section = 'valor_tasacion'

            # Extraer promedios
            if current_section == 'cbr_promedio':
                nums = [_to_float(c) for c in row if _to_float(c) is not None]
                nums = [n for n in nums if n > 0]
                if len(nums) >= 3:
                    data['promedio_cbr'] = {
                        'm2_terreno': nums[0] if nums[0] > 50 else None,
                        'm2_construido': nums[1] if len(nums) > 1 and nums[1] > 10 else None,
                        'uf_m2_terreno': nums[2] if len(nums) > 2 and nums[2] < 100 else None,
                        'uf_m2_construido': nums[3] if len(nums) > 3 and nums[3] < 200 else None,
                        'uf_total': nums[-1] if nums[-1] > 1000 else None,
                    }
                current_section = None

            elif current_section == 'oferta_promedio':
                nums = [_to_float(c) for c in row if _to_float(c) is not None]
                nums = [n for n in nums if n > 0]
                if len(nums) >= 3:
                    data['promedio_oferta'] = {
                        'm2_terreno': nums[0] if nums[0] > 50 else None,
                        'm2_construido': nums[1] if len(nums) > 1 and nums[1] > 10 else None,
                        'uf_m2_terreno': nums[2] if len(nums) > 2 and nums[2] < 100 else None,
                        'uf_m2_construido': nums[3] if len(nums) > 3 and nums[3] < 200 else None,
                        'uf_total': nums[-1] if nums[-1] > 1000 else None,
                    }
                current_section = None

    # Contar referencias — filas de datos con UF total > 1000
    # CBR refs: Foja/Nro pattern (\d+-\d+) o fecha corta (abr. 23)
    # Ofertas: "Portal Inmobiliario", "Yapo", "Link" + datos numéricos
    cbr_count = 0
    oferta_count = 0
    uf_m2_construido = []  # Solo UF/m2 construcción para volatilidad

    in_cbr_section = False
    in_oferta_section = False

    for table in tables_p3:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])
            clean_cells = [c.strip() if c else '' for c in row]

            # Headers de sección
            if re.search(r'Foja.*UF', row_str) or re.search(r'Direcci.*Comuna.*Tipo.*Foja', row_str):
                in_cbr_section = True
                in_oferta_section = False
                continue
            if re.search(r'Fuente.*Ref', row_str) or re.search(r'Direcci.*Link.*Comuna.*Tipo.*Fuente', row_str):
                in_cbr_section = False
                in_oferta_section = True
                continue
            if 'Promedio' in row_str or 'Valor tasaci' in row_str:
                in_cbr_section = False
                in_oferta_section = False
                continue

            # Detectar filas de datos: tienen UF total > 1000
            nums = [_to_float(c) for c in clean_cells if _to_float(c) is not None]
            has_uf_total = any(n and n > 1000 for n in nums)

            if not has_uf_total:
                continue

            # Extraer UF/m2 construido (rango 25-80)
            uf_constr_candidates = [n for n in nums if n and 25 < n < 80]

            if in_cbr_section:
                cbr_count += 1
                if uf_constr_candidates:
                    uf_m2_construido.append(uf_constr_candidates[-1])
            elif in_oferta_section:
                oferta_count += 1
                if uf_constr_candidates:
                    uf_m2_construido.append(uf_constr_candidates[-1])
            else:
                # Fallback: clasificar por patterns
                if re.search(r'\d{3,5}-\d{3,5}', row_str):
                    cbr_count += 1
                elif 'Portal' in row_str or 'Yapo' in row_str or 'Link' in row_str:
                    oferta_count += 1
                if uf_constr_candidates:
                    uf_m2_construido.append(uf_constr_candidates[-1])

    # Si no detectamos section headers pero hay promedio, inferir de promedio
    if cbr_count == 0 and data.get('promedio_cbr'):
        cbr_count = 3  # Transsa estándar = 3 CBR refs
    if oferta_count == 0 and data.get('promedio_oferta'):
        oferta_count = 5  # Transsa estándar = 5 ofertas

    data['n_referencias_cbr'] = cbr_count
    data['n_referencias_oferta'] = oferta_count

    # Volatilidad: CV de UF/m2 construido
    if len(uf_m2_construido) >= 2:
        mean_uf = sum(uf_m2_construido) / len(uf_m2_construido)
        if mean_uf > 0:
            variance = sum((x - mean_uf) ** 2 for x in uf_m2_construido) / len(uf_m2_construido)
            data['volatilidad_precios'] = round(math.sqrt(variance) / mean_uf, 4)
            data['uf_m2_construido_refs'] = uf_m2_construido

    # Descuento oferta (del texto de mercado)
    for table in tables_p3:
        for row in table:
            for cell in row:
                if cell and 'descuento' in cell.lower():
                    # Buscar rango tipo "5% y un 10%"
                    pcts = re.findall(r'(\d+)\s*%', cell)
                    if len(pcts) >= 2:
                        data['descuento_min'] = int(pcts[0]) / 100
                        data['descuento_max'] = int(pcts[1]) / 100
                        data['qsd_estimado'] = (data['descuento_min'] + data['descuento_max']) / 2

    return data


def extract_valorizacion(tables_p3):
    """Página 3: desglose de valorización (terreno + construcción)."""
    data = {}

    for table in tables_p3:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])

            if 'Construcci' in row_str and 'Original' in row_str:
                # Fila de construcción: buscar m², UF/m², material, estado
                for cell in row:
                    c = cell.strip() if cell else ''
                    val = _to_float(c)
                    if c.startswith('C -') or c.startswith('A -') or 'Alb' in c:
                        data['materialidad_code'] = c
                    if val and 50 < val < 500:
                        data['superficie_construida'] = val
                    if val and 20 < val < 100 and 'superficie_construida' in data:
                        data['uf_m2_construccion'] = val
                    ec = _normalize(c)
                    if ec in ESTADO_CONSERVACION:
                        data['estado_conservacion'] = ec
                        data['estado_conservacion_score'] = ESTADO_CONSERVACION[ec]

            if 'Terreno' in row_str and 'Subtotal' not in row_str and 'Total' not in row_str:
                nums = [_to_float(c) for c in row if _to_float(c) is not None]
                # Superficie terreno: 100-2000 m2 (no confundir con UF totales > 3000)
                for val in nums:
                    if 50 < val < 2000 and 'superficie_terreno' not in data:
                        data['superficie_terreno'] = val
                    elif 5 < val < 100 and 'superficie_terreno' in data and 'uf_m2_terreno' not in data:
                        data['uf_m2_terreno'] = val

    return data


def extract_construccion(tables_p4):
    """Página 4: detalles de construcción."""
    data = {}

    for table in tables_p4:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])

            # Estado Conservación General
            if 'Estado Conservaci' in row_str and 'General' in row_str:
                for cell in row:
                    ec = _normalize(cell)
                    if ec in ESTADO_CONSERVACION:
                        data['estado_conservacion'] = ec
                        data['estado_conservacion_score'] = ESTADO_CONSERVACION[ec]

            # Calidad del Material
            if 'Calidad del Material' in row_str:
                for cell in row:
                    cm = _normalize(cell)
                    if cm in CALIDAD_MATERIAL:
                        data['calidad_material'] = cm
                        data['calidad_material_score'] = CALIDAD_MATERIAL[cm]

            # Materialidad
            if 'Materialidad' in row_str and 'Solida' in row_str:
                data['materialidad'] = 'Sólida'
            elif 'Materialidad' in row_str and 'Mixta' in row_str:
                data['materialidad'] = 'Mixta'

            # Estructura Principal — buscar en fila que dice "Estructura Ppal." explícitamente
            if 'Estructura Ppal' in row_str and 'Sec' not in row_str:
                for cell in row:
                    c = cell.strip() if cell else ''
                    if c and c not in ['Estructura Ppal.', 'Estructura Ppal', ''] and len(c) > 3:
                        data['estructura_principal'] = c
                        break

    return data


def extract_sector(tables_p4):
    """Página 4: datos del sector (la más rica para DATOS_MERCADO)."""
    data = {}

    for table in tables_p4:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])

            # Desarrollo Urbano
            if 'Desarrollo Urbano' in row_str:
                for cell in row:
                    du = _normalize(cell)
                    if du in DESARROLLO_URBANO:
                        data['desarrollo_urbano'] = du
                        data['desarrollo_urbano_score'] = DESARROLLO_URBANO[du]

            # Interés por el Sector
            if 'Inter' in row_str and 'Sector' in row_str:
                for cell in row:
                    ints = _normalize(cell)
                    if ints in INTERES_SECTOR:
                        data['interes_sector'] = ints
                        data['interes_sector_score'] = INTERES_SECTOR[ints]

            # Nivel Socioeconómico
            if 'Nivel Socioecon' in row_str:
                for cell in row:
                    nse = _normalize(cell)
                    if nse in NIVEL_SOCIOECONOMICO:
                        data['nivel_socioeconomico'] = nse
                        data['nivel_socioeconomico_score'] = NIVEL_SOCIOECONOMICO[nse]

            # Accesibilidad
            if 'Accesibilidad' in row_str:
                for cell in row:
                    acc = _normalize(cell)
                    if acc in ACCESIBILIDAD:
                        data['accesibilidad'] = acc
                        data['accesibilidad_score'] = ACCESIBILIDAD[acc]

            # Localización
            if 'Localizaci' in row_str:
                for cell in row:
                    loc = _normalize(cell)
                    if loc in LOCALIZACION:
                        data['localizacion'] = loc
                        data['localizacion_score'] = LOCALIZACION[loc]

            # Edad Media Sector
            if 'Edad Media Sector' in row_str:
                for cell in row:
                    val = _to_float(cell)
                    if val and 0 < val < 200:
                        data['edad_media_sector'] = int(val)

            # Tipo Área (Urbana/Rural)
            if 'Tipo' in row_str and 'rea' in row_str and ('Urbana' in row_str or 'Rural' in row_str):
                data['tipo_area'] = 'Urbana' if 'Urbana' in row_str else 'Rural'

            # Densidad
            if 'Densidad' in row_str:
                for cell in row:
                    val = _to_float(cell)
                    if val and 10 < val < 10000:
                        data['densidad_hab_ha'] = int(val)

    return data


def extract_terreno(tables_p4):
    """Página 4: datos del terreno."""
    data = {}

    for table in tables_p4:
        for row in table:
            row_str = ' '.join([c.strip() if c else '' for c in row])

            if 'Superficie Terreno' in row_str:
                for cell in row:
                    val = _to_float(cell)
                    if val and 10 < val < 100000:
                        data['superficie_terreno'] = val

            if 'Topograf' in row_str:
                for cell in row:
                    if cell and cell.strip() in ['Plana', 'Inclinada', 'Ondulada', 'Irregular']:
                        data['topografia'] = cell.strip()

            if 'Forma' in row_str and 'Regular' in row_str:
                data['forma_terreno'] = 'Regular'
            elif 'Forma' in row_str and 'Irregular' in row_str:
                data['forma_terreno'] = 'Irregular'

    return data


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def extract_tasacion(pdf_path):
    """
    Extrae todos los campos de una tasación PDF formato Transsa.

    Args:
        pdf_path: ruta al PDF

    Returns:
        dict con:
            - identificacion: datos del inmueble
            - sinopsis: valores y calificaciones globales
            - referencias: datos de mercado
            - valorizacion: desglose de valor
            - construccion: estado físico
            - sector: datos del entorno
            - terreno: datos del terreno
            - datos_mercado_derivados: campos mapeados a DATOS_MERCADO
            - metadata: trazabilidad
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    # Hash del input
    with open(pdf_path, 'rb') as f:
        input_hash = hashlib.sha256(f.read()).hexdigest()[:16]

    pdf = pdfplumber.open(str(pdf_path))
    all_tables = _extract_all_tables(pdf)

    # Extraer por sección
    identificacion = extract_identificacion(all_tables.get(1, []))
    sinopsis = extract_sinopsis(all_tables.get(1, []))
    referencias = extract_referencias(all_tables.get(2, []))
    valorizacion = extract_valorizacion(all_tables.get(2, []))
    construccion = extract_construccion(all_tables.get(3, []))
    sector = extract_sector(all_tables.get(3, []))
    terreno = extract_terreno(all_tables.get(3, []))

    pdf.close()

    # ============================================================
    # DERIVAR CAMPOS DATOS_MERCADO
    # ============================================================
    dm = {}
    comuna = identificacion.get('comuna', '').lower()
    dm['comuna'] = identificacion.get('comuna', '')

    # Trx: número de referencias CBR (transacciones reales)
    dm['trx'] = referencias.get('n_referencias_cbr', 0)
    dm['trx_source'] = 'CBR references count'

    # Stk: número de ofertas publicadas (proxy de stock)
    dm['stk'] = referencias.get('n_referencias_oferta', 0)
    dm['stk_source'] = 'Portal offers count (single tasación — multiply by coverage factor for market estimate)'

    # QSD: descuento oferta-cierre (Quick Sale Discount)
    if 'qsd_estimado' in referencias:
        dm['qsd'] = referencias['qsd_estimado']
        dm['qsd_source'] = 'Tasador text: descuento range'
    else:
        dm['qsd'] = None
        dm['qsd_source'] = 'Not found in PDF'

    # Vol: volatilidad de precios (dispersión UF/m2 entre referencias)
    if 'volatilidad_precios' in referencias:
        dm['vol'] = referencias['volatilidad_precios']
        dm['vol_source'] = f"CV of UF/m2 across {len(referencias.get('uf_m2_values', []))} refs"
    else:
        dm['vol'] = None
        dm['vol_source'] = 'Insufficient references for volatility calc'

    # DTS: Days to Sell — NO disponible en tasación, requiere fuente externa
    dm['dts'] = None
    dm['dts_source'] = 'Not available in tasación PDF — requires external source'

    # Cap Rate: derivable si tenemos arriendo y tasación
    arriendo = sinopsis.get('arriendo_mensual')
    tasacion_pesos = sinopsis.get('tasacion_pesos')
    if arriendo and tasacion_pesos and tasacion_pesos > 0:
        dm['cap_rate'] = round((arriendo * 12) / tasacion_pesos, 4)
        dm['cap_rate_source'] = 'Arriendo mensual × 12 / Tasación $'
    else:
        dm['cap_rate'] = None
        dm['cap_rate_source'] = 'Missing arriendo or tasación value'

    # Scores cualitativos del sector
    dm['desarrollo_urbano'] = sector.get('desarrollo_urbano_score')
    dm['interes_sector'] = sector.get('interes_sector_score')
    dm['nivel_socioeconomico'] = sector.get('nivel_socioeconomico_score')
    dm['accesibilidad'] = sector.get('accesibilidad_score')
    dm['localizacion'] = sector.get('localizacion_score')

    # Estado físico
    dm['estado_conservacion'] = construccion.get('estado_conservacion_score',
                                                  valorizacion.get('estado_conservacion_score'))

    # Liquidez cualitativa
    dm['grado_liquidez'] = sinopsis.get('grado_liquidez_score')
    dm['oferta'] = sinopsis.get('oferta_score')
    dm['demanda'] = sinopsis.get('demanda_score')

    # Confianza por campo
    confianza = {}
    for key in ['trx', 'stk', 'qsd', 'vol', 'dts', 'cap_rate']:
        if dm.get(key) is not None:
            confianza[key] = 'EXTRACTED'
        else:
            confianza[key] = 'MISSING'

    for key in ['desarrollo_urbano', 'interes_sector', 'nivel_socioeconomico',
                'accesibilidad', 'localizacion', 'estado_conservacion',
                'grado_liquidez', 'oferta', 'demanda']:
        if dm.get(key) is not None:
            confianza[key] = 'MAPPED'
        else:
            confianza[key] = 'MISSING'

    n_extracted = sum(1 for v in confianza.values() if v != 'MISSING')
    n_total = len(confianza)

    result = {
        'identificacion': identificacion,
        'sinopsis': sinopsis,
        'referencias': {k: v for k, v in referencias.items() if k != 'uf_m2_values'},
        'valorizacion': valorizacion,
        'construccion': construccion,
        'sector': sector,
        'terreno': terreno,
        'datos_mercado_derivados': dm,
        'confianza': confianza,
        'metadata': {
            'extractor_version': 'tasacion_extractor_v1.0',
            'formato': 'Transsa',
            'input_file': str(pdf_path.name),
            'input_hash': input_hash,
            'timestamp': datetime.now().isoformat(),
            'campos_extraidos': n_extracted,
            'campos_totales': n_total,
            'cobertura': round(n_extracted / n_total, 2) if n_total > 0 else 0,
        },
    }

    return result


# ============================================================
# CLI
# ============================================================
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python tasacion_extractor.py <ruta_pdf>")
        sys.exit(1)

    result = extract_tasacion(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
