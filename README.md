# PROPIO — Motor de Admisión v2.1

## Qué es
Motor de evaluación de riesgo para admisión R2O. 4 capas: Gates binarios → Similarity Matching (5D) → Brief determinístico → Marcadores Semánticos (AI).

## Ejecutar

```bash
python propio_admission_engine.py
```

Requisitos: Python 3.9+. Sin dependencias externas.

Output: resultado en consola + `admission_output_montecinos.json`.

## Evaluar un nuevo postulante

Editar `propio_admission_engine.py`, sección `if __name__ == "__main__":`. Cambiar el dict `postulante` con los datos del nuevo caso:

```python
postulante = {
    "nombre": "Nombre Completo",
    "pd": 0.05,        # PD Sinacofi (decimal)
    "pie": 0.10,        # Pie como proporción
    "ratio": 0.367,     # Cuota / Ingreso
    "tipo": 1,          # 1=Dependiente, 0=Independiente
    "cr_acido": 1.39,   # min(sueldo líquido) / cuota
    "cv": 0.006,        # CV de liquidaciones (3+ meses)
}
```

Para marcadores semánticos, crear con `crear_marcador("M1", nivel=1, narrativa="...")`.

## Archivos

| Archivo | Qué es |
|---------|--------|
| `propio_admission_engine.py` | Motor completo ejecutable. Portfolio, gates, matching, brief, marcadores. |
| `similarity_matching_v2.py` | Prototipo original del matching (referencia). |
| `similarity_matching_v2_montecinos.html` | Dashboard visual para comité. Abrir en browser. |
| `admission_output_montecinos.json` | Output JSON del caso Montecinos (auditable). |
| `Proceso_Riesgo_Admision_PROPIO_v1.pdf` | Documento formal del proceso completo. |

## Gates

| Gate | Fórmula | Threshold |
|------|---------|-----------|
| CR ácido | min(ingreso_recurrente) / cuota | ≥ 1.0 |
| CV (dependiente) | σ/μ sueldo líquido | < 0.08 |
| PD Sinacofi | Probabilidad de default | < 10% |

## Vector de matching (5D)

```
PD × 3.0 + Pie × 1.0 + Cuota/Ingreso × 1.5 + Tipo × 1.0 + CV_norm × 0.5
```

CR ácido es gate only — no participa en distancia.

## Portfolio: 15 clientes (6 exits, 8 activos, 1 problemático)

Ossian Leiva removido (error operativo en admisión). Oscar Paduro agregado (exit #6).

## Marcadores Semánticos (Capa 4 — Vertical Política)

- **M1**: Morfología de Volatilidad (4 niveles: Rígido → Volátil)
- **M2**: Riesgo de Contraparte (4 niveles: Muy Bajo → Alto)
- **M3**: Huellas de Comportamiento (NO IMPLEMENTADO — requiere cartolas)

Nivel 4 en cualquier marcador = Política trunca (no aprueba).

## Versión
- Motor: v2.1
- Documento: v1.0
- Fecha: 22 Feb 2026
- Autores: Enzo (MetaEnzo) | Claude (Anthropic)
