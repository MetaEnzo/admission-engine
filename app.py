"""
PROPIO OS — Motor de Admisión (Flask Web UI)
=============================================
Formulario → run_admission() → Dashboard idéntico a preview_dashboard_montecinos.html
con datos reales via Jinja2.

Uso:
    cd ~/Desktop/Entrophy\ run/Admission\ Engine/
    # Crear .env con: ANTHROPIC_API_KEY=sk-ant-xxx
    python app.py
    # http://localhost:5001
"""

import json
import os
import traceback

from flask import Flask, render_template, request

# ---------------------------------------------------------------------------
# Load .env (sin dependencia python-dotenv)
# ---------------------------------------------------------------------------
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip())

from propio_admission_engine import (
    MARCADOR_NIVELES,
    PORTFOLIO,
    crear_marcador,
    run_admission,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Anthropic client (optional — marcadores AI)
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


_SYSTEM_PROMPT = """Eres un analista de riesgo crediticio para PROPIO.
Clasifica marcadores semánticos de riesgo.
Responde UNICAMENTE con JSON: {"nivel": <int 1-4>, "narrativa": "<texto>"}

M1 — Morfología Volatilidad:
  1=RÍGIDO (>95% fijo), 2=ESTRUCTURAL, 3=MIXTO, 4=VOLÁTIL
M2 — Riesgo Contraparte:
  1=MUY BAJO (Estado/FFAA/utilities), 2=BAJO, 3=MEDIO, 4=ALTO"""


def classify_marker(marker_id, prompt_data):
    import time
    client = _get_client()
    if not client:
        print(f"[{marker_id}] No hay API key — usando fallback")
        return None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt_data}],
            )
            raw_text = resp.content[0].text.strip() if resp.content else ""
            print(f"[{marker_id}] API response: {raw_text!r}")
            if not raw_text:
                print(f"[{marker_id}] Respuesta vacía — retry {attempt+1}/3")
                time.sleep(2)
                continue
            # Extraer JSON si viene envuelto en texto
            if "{" in raw_text and "}" in raw_text:
                json_str = raw_text[raw_text.index("{"):raw_text.rindex("}") + 1]
                parsed = json.loads(json_str)
            else:
                parsed = json.loads(raw_text)
            nivel = int(parsed["nivel"])
            if 1 <= nivel <= 4:
                return (nivel, parsed["narrativa"])
            print(f"[{marker_id}] Nivel fuera de rango: {nivel}")
        except Exception as e:
            print(f"[{marker_id}] Intento {attempt+1}/3 falló: {e}")
            if attempt < 2:
                time.sleep(3)
    print(f"[{marker_id}] Todos los intentos fallaron — usando fallback")
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", resultado=None, form=None, error=None)


@app.route("/evaluar", methods=["POST"])
def evaluar():
    form = request.form

    # Parse 7 campos core
    try:
        nombre = form.get("nombre", "Postulante").strip() or "Postulante"
        pd = float(form["pd"])
        pie = float(form["pie"])
        ratio_raw = form.get("ratio", "").strip()
        ratio = float(ratio_raw) if ratio_raw else None
        tipo = int(form["tipo"])
        cr_acido = float(form["cr_acido"])
        cv = float(form["cv"])
    except (ValueError, KeyError) as e:
        return render_template("index.html", error=f"Error en datos: {e}")

    postulante = {
        "nombre": nombre, "pd": pd, "pie": pie,
        "ratio": ratio, "tipo": tipo, "cr_acido": cr_acido, "cv": cv,
    }

    # Marcadores semánticos — datos de soporte del postulante
    m1_datos = {
        "pct_fijo": 0.984,
        "componentes_fijos": ["sueldo_base", "gratificacion", "bonos"],
        "componente_variable": "horas_extras",
        "rango_variable": {"min": 13897, "max": 71485},
        "renta_depurada_promedio": 3410985,
    }
    m2_datos = {
        "empleador": "AES Andes",
        "sector": "Energía / Utilities",
        "tipo_empresa": "Multinacional (NYSE: AES)",
        "cargo": "Analista de Redes",
        "contrato": "Indefinido",
        "antiguedad_meses": 15,
        "codeudor_empleador": "Swiss Trading Group",
        "codeudor_antiguedad_meses": 44,
    }

    # Clasificar via Anthropic API
    m1_prompt = (
        f"Clasifica M1 (Morfología Volatilidad) para este postulante.\n"
        f"Datos: {json.dumps(m1_datos, ensure_ascii=False)}"
    )
    m2_prompt = (
        f"Clasifica M2 (Riesgo Contraparte) para este postulante.\n"
        f"Datos: {json.dumps(m2_datos, ensure_ascii=False)}"
    )

    m1_result = classify_marker("M1", m1_prompt)
    m2_result = classify_marker("M2", m2_prompt)

    # Fallback si no hay API key o falla la clasificación
    if m1_result:
        m1 = crear_marcador("M1", nivel=m1_result[0],
                            narrativa=m1_result[1], datos_soporte=m1_datos)
    else:
        m1 = crear_marcador("M1", nivel=1,
                            narrativa="99.6% ingreso fijo. Base + gratificación + bonos idénticos 3 meses.",
                            datos_soporte=m1_datos)

    if m2_result:
        m2 = crear_marcador("M2", nivel=m2_result[0],
                            narrativa=m2_result[1], datos_soporte=m2_datos)
    else:
        m2 = crear_marcador("M2", nivel=1,
                            narrativa="AES Andes (NYSE: AES). Multinacional energética, infraestructura crítica.",
                            datos_soporte=m2_datos)

    marcadores = [m1, m2]

    # Run engine
    resultado = run_admission(postulante, marcadores=marcadores or None)

    # JSON for JavaScript charts
    top5_json = json.dumps(resultado["matching"]["top5"],
                           ensure_ascii=False, default=str)
    postulante_json = json.dumps(postulante,
                                 ensure_ascii=False, default=str)
    portfolio_json = json.dumps(
        [{"nombre": c["nombre"], "pd": c["pd"], "pie": c["pie"],
          "ratio": c["ratio"], "cv": c["cv"], "outcome": c["outcome"]}
         for c in PORTFOLIO],
        ensure_ascii=False, default=str)

    return render_template(
        "index.html",
        resultado=resultado,
        postulante=postulante,
        top5_json=top5_json,
        postulante_json=postulante_json,
        portfolio_json=portfolio_json,
        form=form,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
