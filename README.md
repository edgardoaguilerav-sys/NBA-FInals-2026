# NBA Finals Predictor

Modelo de machine learning para predecir el ganador de las NBA Finals dado que los dos finalistas son conocidos.

**Stack:** Python (nba_api, pandas) + R (glmnet, randomForest, xgboost)  
**Datos:** 21 ediciones de NBA Finals (2003-04 a 2023-24) extraídos de stats.nba.com  
**Validación:** Rolling window temporal — train 2004-2018, test 2019-2024

---

## Resultado principal

**Random Forest: 100% accuracy en test (5/5 Finals correctas).**  
Modelo simplificado de 2 features: también 100% (5/5).

---

## Hallazgos clave

- **Las pérdidas de balón en momentos decisivos** (últimos 5 min, partido cerrado) son la feature más predictiva (importancia RF: 10.5). El equipo con menor clutch turnover ganó el 76% de las 21 Finals.
- **El rendimiento individual de la estrella no entró al modelo.** LASSO lo descartó — los campeonatos los ganan sistemas colectivos.
- **Playoffs supera a temporada regular como predictor** desde 2019 (80% vs 60%), con un gap que crece ~0.027 pp/año por efecto del load management.
- **76% de los campeones llegaron sin historial reciente de Finals** — no existe "dynasty penalty".
- **Los dos únicos fallos del modelo** (CLE 2016, TOR 2019) correlacionan con lesiones graves de Golden State durante la serie — el único riesgo no modelable.

---

## Features seleccionadas (LASSO)

| Feature | Importancia RF | Descripción |
|---|---|---|
| `clutch_tov_z` | 10.5 | Pérdidas de balón en últimos 5 min con partido cerrado |
| `reg_diff_pg_z` | 4.1 | Diferencial de puntos en temporada regular |
| `playoff_tov_pct_z` | 2.8 | % posesiones que terminan en turnover (playoffs) |
| `win_pct_g4plus_z` | 0.6 | Win% en partidos 4-7 de cada serie (eliminación) |

---

## Estructura del proyecto

```
├── finals_config.py        ← Historial de Finals, team IDs, MVPs (hardcoded)
├── extract_raw.py          ← Extracción desde stats.nba.com (~30 min para 21 temporadas)
├── build_features.py       ← Construcción del dataset desde CSVs crudos
├── extract_2026_finals.py  ← Extracción de datos reales para Finals 2026
│
├── NBA_model.R             ← Pipeline principal: normalización, LASSO, 3 modelos, validación
├── NBA_predict_2026.R      ← Bootstrap de estabilidad + predicción Finals 2026
├── NBA_hypothesis_test.R   ← Test: temporada regular vs playoffs como predictor
├── NBA_rolling_window.R    ← Análisis temporal del poder predictivo por era
├── NBA_advanced_analysis.R ← Fatiga, Monte Carlo, dynasty, upsets, conferencia
├── NBA_bench_analysis.R    ← Análisis de jugadores de banca
│
└── data/
    └── features/           ← Dataset final (42 filas × 59 columnas)
        ├── finals_dataset.csv
        ├── finals_dataset_diff.csv
        └── finals_2026_features.csv
```

---

## Cómo reproducir

**Paso 1 — Extracción** (requiere Python local; stats.nba.com bloquea IPs de cloud):
```bash
# Instalar dependencias
pip install nba_api pandas

# Extraer datos crudos (~30 min para las 21 temporadas)
python extract_raw.py

# Construir dataset de features
python build_features.py
```

**Paso 2 — Modelado** (desde RStudio con working directory en la raíz del proyecto):
```r
# Instalar dependencias
install.packages(c("tidyverse", "glmnet", "randomForest", "xgboost", "caret"))

# Pipeline principal
source("NBA_model.R")

# Análisis adicionales
source("NBA_predict_2026.R")
source("NBA_rolling_window.R")
source("NBA_advanced_analysis.R")
```

---

## Predicción Finals 2026: Knicks vs Spurs

Datos reales extraídos de la API (mayo 2026):

| Métrica | Spurs | Knicks |
|---|---|---|
| Pérdidas decisivas por partido | 2.2 | **1.5** |
| % posesiones perdidas (playoffs) | 15.2% | **13.9%** |
| Diferencial puntos reg. season | **+8.3** | +6.4 |
| Diferencial puntos playoffs | +10.3 | **+19.3** |
| Partidos jugados pre-Finals | 18 | **14** |

**Modelo playoffs (más preciso en era moderna): Knicks ~57-65%**  
**Monte Carlo (100k simulaciones, con HCA): Knicks 64.7%**  
**Escenario más probable: Knicks ganan en 6 partidos (31.3%)**

---

## Documentación

- `NBA_Features_Guide.docx` — Guía completa de métricas y hallazgos
- `NBA_Guia_Divulgativa.docx` — Versión accesible para audiencia general
- `NBA_Nota_Metodologica.docx` — Nota técnica: selección de variables y modelos
- `LinkedIn_Post.md` — Post de divulgación del proyecto
