"""
Test server: renderiza el dashboard con datos hardcoded de Montecinos
para verificar visualmente antes de deploy.
"""
from flask import Flask, render_template
from propio_admission_engine import run_admission

app = Flask(__name__)

@app.route("/")
def dashboard():
    postulante = {
        "nombre": "Andrés Montecinos",
        "pd": 0.05,
        "pie": 0.10,
        "ratio": 0.367,
        "tipo": "Dependiente",
        "cv": 0.006,
        "cr_acido": 1.39,
        "scoring_propio": 85,
    }

    datos_plusvalor = {
        "valor_activo": 4487,
        "pie_uf": 448.7,
        "meta_uf": 897.4,
        "cuota_propio": 32.40,
        "ingreso_uf": 88.3,
        "ipv": 0.03,
        "plazo_max": 60,
        "tasa_banco": 0.05,
    }

    stress_input = {
        "cuota": 32.40,
        "ingreso": 88.3,
        "score": 534,
        "tipo": "Dependiente",
    }

    resultado = run_admission(
        postulante,
        stress_input=stress_input,
        datos_plusvalor=datos_plusvalor,
    )

    return render_template(
        "evaluacion_comite.html",
        resultado=resultado,
        form={},
        m1_data=None,
        m2_data=None,
        m1_result=None,
        m2_result=None,
        has_api_key=False,
        error=None,
    )


if __name__ == "__main__":
    app.run(port=5050, debug=True)
