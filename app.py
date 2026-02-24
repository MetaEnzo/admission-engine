"""
PROPIO OS — Motor de Admision (Flask Web UI)
=============================================
Wrapper web para propio_admission_engine.py.
Corre SIN API key (marcadores AI deshabilitados).
Con ANTHROPIC_API_KEY en env, clasifica M1/M2 via Claude.

Uso:
    ANTHROPIC_API_KEY=sk-ant-xxx python app.py
    # http://localhost:5000
"""

import json
import os
import traceback

from flask import Flask, render_template, request

from propio_admission_engine import (
    MARCADOR_NIVELES,
    crear_marcador,
    run_admission,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Anthropic client (optional)
# ---------------------------------------------------------------------------
_anthropic_client = None

def _get_client():
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        _anthropic_client = anthropic.Anthropic()
        return _anthropic_client
    except Exception:
        return None


# ---------------------------------------------------------------------------
# M1 / M2 field parsing helpers
# ---------------------------------------------------------------------------
def parse_m1_fields(form):
    """Extract M1 (Volatilidad) fields from form, return dict or None."""
    pct_fijo = form.get("pct_fijo", "").strip()
    if not pct_fijo:
        return None
    try:
        data = {
            "pct_fijo": float(pct_fijo),
            "componentes_fijos": form.get("componentes_fijos", "").strip(),
            "componente_variable": form.get("componente_variable", "").strip(),
            "rango_min": form.get("rango_min", "").strip(),
            "rango_max": form.get("rango_max", "").strip(),
            "renta_depurada": form.get("renta_depurada", "").strip(),
        }
        return data
    except (ValueError, TypeError):
        return None


def parse_m2_fields(form):
    """Extract M2 (Contraparte) fields from form, return dict or None."""
    empleador = form.get("empleador", "").strip()
    if not empleador:
        return None
    try:
        data = {
            "empleador": empleador,
            "sector": form.get("sector", "").strip(),
            "tipo_empresa": form.get("tipo_empresa", "").strip(),
            "cargo": form.get("cargo", "").strip(),
            "contrato": form.get("contrato", "").strip(),
            "antiguedad_meses": form.get("antiguedad_meses", "").strip(),
            "codeudor_empleador": form.get("codeudor_empleador", "").strip(),
            "codeudor_antiguedad_meses": form.get("codeudor_antiguedad_meses", "").strip(),
        }
        return data
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# AI classification
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """Eres un analista de riesgo crediticio para PROPIO, una empresa fintech de credito hipotecario en Chile.
Tu tarea es clasificar marcadores semanticos de riesgo.

Debes responder UNICAMENTE con JSON valido: {"nivel": <int 1-4>, "narrativa": "<texto explicativo>"}

NIVELES MARCADOR M1 — Morfologia de la Volatilidad:
  Nivel 1 — RIGIDO: >95% ingreso fijo, varianza irrelevante
  Nivel 2 — ESTRUCTURAL: Variable predecible (bonos por ley, comisiones con piso)
  Nivel 3 — MIXTO: Componente variable significativo pero con base
  Nivel 4 — VOLATIL: Predominantemente variable, sin piso garantizado

NIVELES MARCADOR M2 — Riesgo de Contraparte:
  Nivel 1 — MUY BAJO: Estado, FFAA, utilities reguladas, universidades publicas
  Nivel 2 — BAJO: Empresa grande privada, sector estable, >3 anios
  Nivel 3 — MEDIO: Pyme establecida, sector ciclico
  Nivel 4 — ALTO: Startup, honorarios sin contrato, sector inestable

La narrativa debe ser concisa (2-4 oraciones) explicando POR QUE asignas ese nivel, citando los datos proporcionados."""


def classify_marker_m1(m1_data, cv_value):
    """Classify M1 via Anthropic API. Returns (nivel, narrativa) or None."""
    client = _get_client()
    if not client:
        return None
    prompt = f"""Clasifica el MARCADOR M1 (Morfologia de la Volatilidad) para este postulante:

- CV ingreso: {cv_value}
- % ingreso fijo: {m1_data.get('pct_fijo', 'N/A')}
- Componentes fijos: {m1_data.get('componentes_fijos', 'N/A')}
- Componente variable: {m1_data.get('componente_variable', 'N/A')}
- Rango variable: {m1_data.get('rango_min', 'N/A')} - {m1_data.get('rango_max', 'N/A')}
- Renta depurada promedio: {m1_data.get('renta_depurada', 'N/A')}

Responde SOLO con JSON: {{"nivel": <int>, "narrativa": "<texto>"}}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        parsed = json.loads(text)
        nivel = int(parsed["nivel"])
        if nivel < 1 or nivel > 4:
            return None
        return (nivel, parsed["narrativa"])
    except Exception:
        traceback.print_exc()
        return None


def classify_marker_m2(m2_data):
    """Classify M2 via Anthropic API. Returns (nivel, narrativa) or None."""
    client = _get_client()
    if not client:
        return None
    prompt = f"""Clasifica el MARCADOR M2 (Riesgo de Contraparte) para este postulante:

- Empleador: {m2_data.get('empleador', 'N/A')}
- Sector: {m2_data.get('sector', 'N/A')}
- Tipo empresa: {m2_data.get('tipo_empresa', 'N/A')}
- Cargo: {m2_data.get('cargo', 'N/A')}
- Contrato: {m2_data.get('contrato', 'N/A')}
- Antiguedad: {m2_data.get('antiguedad_meses', 'N/A')} meses
- Codeudor empleador: {m2_data.get('codeudor_empleador', 'N/A')}
- Codeudor antiguedad: {m2_data.get('codeudor_antiguedad_meses', 'N/A')} meses

Responde SOLO con JSON: {{"nivel": <int>, "narrativa": "<texto>"}}"""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        parsed = json.loads(text)
        nivel = int(parsed["nivel"])
        if nivel < 1 or nivel > 4:
            return None
        return (nivel, parsed["narrativa"])
    except Exception:
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("evaluacion_comite.html", resultado=None, form={})


def parse_activo_fields(form):
    """Extract asset fields from form. Returns dict or None if no asset data."""
    comuna = form.get("comuna", "").strip()
    precio_raw = form.get("precio_uf", "").strip()
    if not comuna or not precio_raw:
        return None
    try:
        activo = {
            "direccion": form.get("direccion", "").strip() or "N/A",
            "comuna": comuna,
            "precio_uf": float(precio_raw),
            "buffer_pct": float(form.get("buffer_pct", "0.15").strip() or "0.15"),
            "renta_mensual_uf": float(form.get("renta_mensual_uf", "0").strip() or "0"),
            "opex_mensual_uf": float(form.get("opex_mensual_uf", "0").strip() or "0"),
            "antiguedad_anos": float(form.get("antiguedad_anos", "0").strip() or "0"),
            "fase_economica": form.get("fase_economica", "NORMAL").strip() or "NORMAL",
            "trimestre": form.get("trimestre", "Q1").strip() or "Q1",
            "estado_fisico": float(form.get("estado_fisico", "5").strip() or "5"),
            "cumplimiento_legal": float(form.get("cumplimiento_legal", "5").strip() or "5"),
            "riesgo_sismico": float(form.get("riesgo_sismico", "5").strip() or "5"),
            "conectividad": float(form.get("conectividad", "5").strip() or "5"),
            "servicios": float(form.get("servicios", "5").strip() or "5"),
            "velocidad_absorcion": float(form.get("velocidad_absorcion", "5").strip() or "5"),
            "demanda_zona": float(form.get("demanda_zona", "5").strip() or "5"),
            "renta_cliente_uf": float(form.get("renta_cliente_uf", "0").strip() or "0"),
        }
        return activo
    except (ValueError, TypeError):
        return None


@app.route("/evaluar", methods=["POST"])
def evaluar():
    form = request.form

    # Parse core fields — ALL metrics are CALCULATED from raw data
    try:
        nombre = form.get("nombre", "Postulante").strip() or "Postulante"
        pd = float(form["pd"])
        pie = float(form["pie"])
        tipo = int(form["tipo"])

        # Raw inputs — financieros
        ingreso_bruto = float(form["ingreso_bruto"])
        cuota_mensual = float(form["cuota_mensual"])
        min_ingreso_raw = form.get("min_ingreso", "").strip()
        min_ingreso = float(min_ingreso_raw) if min_ingreso_raw else ingreso_bruto

        # Raw inputs — sueldos líquidos de liquidaciones (para CV)
        sueldos_raw = form.get("sueldos_liquidos", "").strip()
        if sueldos_raw:
            sueldos = [float(s.strip()) for s in sueldos_raw.split(",") if s.strip()]
        else:
            sueldos = []

        # CALCULATED: CV = std / mean de sueldos líquidos
        if len(sueldos) >= 2:
            mean_s = sum(sueldos) / len(sueldos)
            std_s = (sum((x - mean_s) ** 2 for x in sueldos) / len(sueldos)) ** 0.5
            cv = std_s / mean_s if mean_s > 0 else 0.0
        elif len(sueldos) == 1:
            cv = 0.0
        else:
            cv = 0.0  # sin liquidaciones → comité decide

        # CALCULATED: C/I y CR ácido
        ratio = cuota_mensual / ingreso_bruto if ingreso_bruto > 0 else None
        cr_acido = min_ingreso / cuota_mensual if cuota_mensual > 0 else 0.0

    except (ValueError, KeyError) as e:
        return render_template("evaluacion_comite.html", resultado=None, form=form,
                               error=f"Error en datos: {e}")

    postulante = {
        "nombre": nombre,
        "pd": pd,
        "pie": pie,
        "ratio": ratio,
        "tipo": tipo,
        "cr_acido": cr_acido,
        "cv": cv,
    }

    # Parse asset fields (optional)
    activo = parse_activo_fields(form)

    # Classify markers (if data and API key available)
    marcadores = []
    m1_result = None
    m2_result = None

    m1_data = parse_m1_fields(form)
    m2_data = parse_m2_fields(form)

    if m1_data:
        ai = classify_marker_m1(m1_data, cv)
        if ai:
            nivel, narrativa = ai
            m1 = crear_marcador("M1", nivel=nivel, narrativa=narrativa,
                                datos_soporte=m1_data)
            marcadores.append(m1)
            m1_result = m1

    if m2_data:
        ai = classify_marker_m2(m2_data)
        if ai:
            nivel, narrativa = ai
            m2 = crear_marcador("M2", nivel=nivel, narrativa=narrativa,
                                datos_soporte=m2_data)
            marcadores.append(m2)
            m2_result = m2

    # Run engine (with asset if provided)
    resultado = run_admission(postulante, marcadores=marcadores or None, activo=activo)

    # Check if API key is available (for template messaging)
    has_api_key = _get_client() is not None

    return render_template(
        "evaluacion_comite.html",
        resultado=resultado,
        form=form,
        m1_data=m1_data,
        m2_data=m2_data,
        m1_result=m1_result,
        m2_result=m2_result,
        has_api_key=has_api_key,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
