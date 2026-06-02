# Post LinkedIn — NBA Finals Predictor

---

Construí un modelo para predecir el ganador de las NBA Finals. El resultado me sorprendió.

Partí de una pregunta simple: ¿qué estadísticas predicen mejor quién gana el campeonato? Usé datos de las 21 Finales entre 2004 y 2024, extraídos directamente de la API oficial de la NBA, y tres modelos — Regresión Logística con regularización LASSO, Random Forest y XGBoost — validados con un esquema de ventana temporal rodante (train: 2004-2018 / test: 2019-2024).

**El resultado: Random Forest con 100% de accuracy en el test (5/5 Finals correctas).**

Pero lo interesante no es el número. Es lo que el modelo encontró.

---

🔍 **Lo que predice quién gana las Finals — y lo que no**

LASSO seleccionó solo 4 variables de las 40 candidatas. Todas son métricas colectivas:

→ **Pérdidas de balón en momentos decisivos** (la más importante, importancia RF: 10.5). En basquetbol, cuando un equipo pierde el control del balón sin haber intentado anotar, el rival contraataca con ventaja y convierte en puntos el 60-70% de las veces. El modelo mide esto específicamente en los últimos 5 minutos de partido cuando la diferencia es de 5 puntos o menos — es decir, cuando el partido está completamente abierto y cualquier error cuesta caro. En las 21 Finales del dataset, el equipo con menos pérdidas en esos momentos ganó el 76% de las veces.

→ **Diferencial de puntos en temporada regular** (importancia: 4.1). Cuántos puntos más anotó el equipo que su rival en promedio durante los 82 partidos de la temporada. No si ganó o perdió, sino por cuánto — refleja superioridad real más allá del resultado.

→ **% de pérdidas de balón en toda la fase de playoffs** (importancia: 2.8). La misma lógica de pérdidas, pero medida sobre todos los partidos de playoffs previos a las Finals — captura consistencia.

→ **Win% en partidos tardíos de serie** (importancia: 0.6). En cada serie de playoffs se juegan entre 4 y 7 partidos. Los partidos 4, 5, 6 y 7 son los más tensos porque un equipo puede quedar eliminado. Esta variable mide qué tan bien rinde el equipo en esos momentos de presión máxima.

**El rendimiento individual del mejor jugador no entró al modelo.** LASSO lo descartó. Los campeonatos los ganan sistemas, no estrellas.

---

📊 **El hallazgo que más me llamó la atención: playoffs vs temporada regular**

Comparé modelos entrenados solo con estadísticas de temporada regular vs solo con estadísticas de playoffs. Los resultados en el período de test (2019-2024):

- Modelo temporada regular → 60% de accuracy (Random Forest)
- Modelo playoffs → 80% de accuracy (Random Forest)
- Modelo mixto → 100% de accuracy (Random Forest)

Para validar esto sin contaminar el test, usé una **ventana temporal rodante**: en lugar de un único corte fijo, para cada año evalué el modelo entrenando solo con las Finales anteriores a ese año y prediciendo ese año en particular. Es el equivalente a preguntarse "si yo hubiera tenido este modelo en 2015, ¿habría acertado?", y repetirlo para cada año desde 2011 hasta 2023. Así se evita que información futura "filtre" hacia el pasado.

El resultado: desde 2019, el gap entre el modelo de playoffs (más preciso) y el de temporada regular se amplía sostenidamente — ~0.027 puntos porcentuales por año. La causa más probable: el "descanso estratégico de estrellas" en temporada regular (en inglés, load management). Los equipos modernos hacen descansar a sus mejores jugadores en partidos que consideran poco relevantes, lo que infla artificialmente las estadísticas de ciertos rivales y subestima las del propio equipo. Resultado: los números de temporada regular son cada vez menos representativos del nivel real cuando llega el momento decisivo.

---

⚠️ **Lo que ningún modelo puede predecir**

Las dos únicas Finales donde el modelo falló completamente (Cleveland 2016, Toronto 2019) comparten una causa: Golden State perdió jugadores clave por lesión durante la serie (Bogut y Love en 2016; Durant y Klay en 2019). Los datos de partido a partido muestran el efecto en cadena: sin su creador de tiro, el equipo pasó de anotar de 2 puntos eficientemente a forzar triples de baja calidad, aumentaron las pérdidas de balón y terminaron perdiendo series que estadísticamente no debían perder.

Las lesiones en medio de la serie son el único riesgo no modelable.

---

🏀 **Predicción Finals 2026: Knicks vs Spurs**

Datos reales extraídos de la API para las dos métricas clave:

**Pérdidas de balón en momentos decisivos** (promedio por partido, en los últimos 5 minutos con diferencia ≤5 puntos):
- Knicks: 1.5 → pierden el balón 1.5 veces por partido cuando el marcador está cerrado al final
- Spurs: 2.2 → pierden el balón 2.2 veces en esos mismos momentos

**Porcentaje de posesiones que terminan en pérdida de balón en playoffs** (de cada 100 veces que el equipo tiene el balón, cuántas termina sin haber tirado al aro):
- Knicks: 13.9% → de cada 100 posesiones, pierden el balón en ~14
- Spurs: 15.2% → de cada 100 posesiones, pierden el balón en ~15

En ambas métricas los Knicks cuidan mejor el balón. La diferencia parece pequeña, pero en playoffs — donde los partidos se deciden por 5 o 6 puntos — perder una posesión de más por partido puede ser la diferencia entre ganar y perder la serie.

El modelo de playoffs (el más preciso en la era actual) da **Knicks ~57-65%**.
La simulación Monte Carlo en 100,000 iteraciones, con ventaja de cancha de los Spurs incorporada, da **Knicks 64.7%**.
El escenario más probable: **Knicks ganan en 6 partidos** (31.3% de las simulaciones).

El único factor que puede voltear este pronóstico: una lesión en serie. Es lo que la historia dice.

---

📁 El pipeline completo está en Python (nba_api, pandas) + R (glmnet, randomForest, xgboost). Extracción, feature engineering, modelado y validación temporal en tres scripts reproducibles.

¿Qué otras aplicaciones de ML en deportes les parecen interesantes?

#MachineLearning #DataScience #NBA #SportAnalytics #Python #R #RandomForest #LASSO #Prediccion
