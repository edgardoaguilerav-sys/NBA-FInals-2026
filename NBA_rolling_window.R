# =============================================================================
# NBA_rolling_window.R
# Análisis temporal: expanding window leave-one-out
# Para cada Finals desde 2011, entrena con TODAS las anteriores y predice esa.
# Compara poder predictivo de Temporada Regular vs Playoffs año por año.
# =============================================================================

source("NBA_model.R")

library(tidyverse)
library(glmnet)
library(randomForest)

cat("============================================================\n")
cat("  ANÁLISIS TEMPORAL: ¿Cuándo cambió el poder predictivo?\n")
cat("  Expanding window leave-one-out (2011-2024)\n")
cat("============================================================\n\n")

# Features por grupo (solo las disponibles)
reg_feats     <- intersect(c("reg_diff_pg_z","reg_net_rating_z","reg_win_pct_z",
                              "playoff_seed_z","reg_pace_z"), clean_features)
playoff_feats <- intersect(c("playoff_net_rating_z","playoff_tov_pct_z",
                              "clutch_tov_z","win_pct_g4plus_z",
                              "pre_finals_win_pct_z","avg_point_diff_pre_z",
                              "playoff_pie_z","clutch_win_pct_z"), clean_features)
mixed_feats   <- selected_features  # del NBA_model.R

# Dataset completo normalizado (todas las temporadas)
df_full <- df %>%
  mutate(year = as.integer(substr(season, 1, 4))) %>%
  arrange(year)

# Construir matrices completas con las features _z
all_X <- df_full %>% select(all_of(clean_features)) %>% as.matrix()
all_y <- as.integer(df_full$won_finals) - 1

# Vector de años por fila (42 filas: 2 por Finals)
years_all    <- df_full %>% pull(year)
finals_years <- unique(years_all)

# Minimum training window: 8 Finals (16 obs) para tener modelo estable
MIN_TRAIN_FINALS <- 8
test_years <- finals_years[(MIN_TRAIN_FINALS + 1):length(finals_years)]

cat(sprintf("Primeras %d Finals para warm-up (train inicial): %d-%d\n",
            MIN_TRAIN_FINALS, finals_years[1], finals_years[MIN_TRAIN_FINALS]))
cat(sprintf("Finals evaluadas: %d (%d a %d)\n\n",
            length(test_years), min(test_years), max(test_years)))

# ---------------------------------------------------------------------------
# Función: predice una Finals con expanding window
# ---------------------------------------------------------------------------
predict_year <- function(test_year, features) {
  train_idx <- which(years_all < test_year)
  test_idx  <- which(years_all == test_year)

  if (length(train_idx) < 10 || length(test_idx) != 2) return(NULL)

  Xtr <- all_X[train_idx, features, drop = FALSE]
  ytr <- all_y[train_idx]
  Xte <- all_X[test_idx,  features, drop = FALSE]
  yte <- all_y[test_idx]

  # Manejar features con varianza cero en train
  vars <- apply(Xtr, 2, var, na.rm = TRUE)
  good <- names(vars)[vars > 1e-10 & !is.na(vars)]
  if (length(good) < 1) return(NULL)
  Xtr <- Xtr[, good, drop = FALSE]
  Xte <- Xte[, good, drop = FALSE]

  # Logistic simple (más estable con N pequeño)
  nfolds <- min(5, floor(sum(ytr == 1)))
  if (nfolds < 2) nfolds <- 2

  fit <- tryCatch({
    cv.glmnet(Xtr, ytr, family = "binomial", alpha = 0.5,
              nfolds = nfolds, type.measure = "deviance")
  }, error = function(e) NULL)

  if (is.null(fit)) return(NULL)

  probs <- predict(fit, Xte, s = "lambda.min", type = "response")[, 1]

  # ¿Acertó? (mayor prob = ganador predicho)
  pred_winner_idx  <- which.max(probs)
  actual_winner_idx <- which(yte == 1)

  teams <- df_full %>%
    filter(year == test_year) %>%
    pull(team_abbr)

  list(
    predicted = teams[pred_winner_idx],
    actual    = teams[actual_winner_idx],
    correct   = (pred_winner_idx == actual_winner_idx),
    prob_winner = probs[actual_winner_idx],
    teams     = teams
  )
}

# ---------------------------------------------------------------------------
# Correr para cada año de test
# ---------------------------------------------------------------------------
results <- map_dfr(test_years, function(yr) {
  r_reg  <- predict_year(yr, reg_feats)
  r_play <- predict_year(yr, playoff_feats)
  r_mix  <- predict_year(yr, mixed_feats)

  tibble(
    year          = yr,
    season        = sprintf("%d-%02d", yr, (yr+1) %% 100),
    actual_winner = if (!is.null(r_reg)) r_reg$actual else NA,
    reg_ok        = if (!is.null(r_reg))  r_reg$correct  else NA,
    play_ok       = if (!is.null(r_play)) r_play$correct else NA,
    mix_ok        = if (!is.null(r_mix))  r_mix$correct  else NA,
    reg_pick      = if (!is.null(r_reg))  r_reg$predicted  else NA,
    play_pick     = if (!is.null(r_play)) r_play$predicted else NA,
    mix_pick      = if (!is.null(r_mix))  r_mix$predicted  else NA,
  )
})

# ---------------------------------------------------------------------------
# Tabla principal
# ---------------------------------------------------------------------------
cat("=== TABLA AÑO A AÑO ===\n\n")
cat(sprintf("  %-8s  %-6s  %-6s  %-6s  %-6s  %-6s  %-6s\n",
            "Season", "Real", "RegPick", "PlayPick", "RegOK", "PlayOK", "MixOK"))
cat(sprintf("  %s\n", paste(rep("-", 62), collapse="")))

for (i in seq_len(nrow(results))) {
  r <- results[i, ]
  cat(sprintf("  %-8s  %-6s  %-8s  %-8s  %-5s  %-5s  %-5s\n",
              r$season, r$actual_winner,
              r$reg_pick, r$play_pick,
              ifelse(r$reg_ok,  "✓", "✗"),
              ifelse(r$play_ok, "✓", "✗"),
              ifelse(r$mix_ok,  "✓", "✗")))
}

# ---------------------------------------------------------------------------
# Accuracy rodante: ventana de 5 años
# ---------------------------------------------------------------------------
cat("\n=== ACCURACY RODANTE (ventana 5 Finals) ===\n\n")

window <- 5
rolling <- map_dfr(window:nrow(results), function(i) {
  w <- results[(i - window + 1):i, ]
  tibble(
    year_end  = w$year[window],
    season    = w$season[window],
    reg_acc   = mean(w$reg_ok,  na.rm = TRUE),
    play_acc  = mean(w$play_ok, na.rm = TRUE),
    mix_acc   = mean(w$mix_ok,  na.rm = TRUE),
    winner    = case_when(
      play_acc > reg_acc ~ "PLAYOFFS",
      reg_acc  > play_acc ~ "REG SEASON",
      TRUE ~ "EMPATE"
    )
  )
})

cat(sprintf("  %-8s  %8s  %8s  %8s  %s\n",
            "Season", "RegAcc", "PlayAcc", "MixAcc", "Ganador"))
cat(sprintf("  %s\n", paste(rep("-", 55), collapse="")))

for (i in seq_len(nrow(rolling))) {
  r <- rolling[i, ]
  marker <- if (r$winner == "PLAYOFFS") " ← PLAYOFFS toma el liderazgo" else ""
  cat(sprintf("  %-8s  %7.1f%%  %7.1f%%  %7.1f%%  %-10s%s\n",
              r$season,
              r$reg_acc*100, r$play_acc*100, r$mix_acc*100,
              r$winner, marker))
}

# ---------------------------------------------------------------------------
# Punto de quiebre: primera vez que playoffs supera a reg season sostenidamente
# ---------------------------------------------------------------------------
cat("\n=== ANÁLISIS DEL QUIEBRE ===\n\n")

# ¿Existe ventana donde playoffs > reg season consistentemente?
breakpoint <- rolling %>%
  filter(play_acc > reg_acc) %>%
  slice(1)

if (nrow(breakpoint) > 0) {
  cat(sprintf("  Primera ventana donde Playoffs > Reg Season: %s\n",
              breakpoint$season))
  cat(sprintf("  Playoffs: %.1f%%  vs  Reg Season: %.1f%%\n\n",
              breakpoint$play_acc*100, breakpoint$reg_acc*100))
} else {
  cat("  Reg Season se mantuvo dominante en todas las ventanas.\n\n")
}

# Tendencia: ¿el gap reg-play aumenta con el tiempo?
if (nrow(rolling) >= 3) {
  gap <- rolling %>% mutate(gap = play_acc - reg_acc)
  trend <- lm(gap ~ year_end, data = gap)
  slope <- coef(trend)[2]
  cat(sprintf("  Tendencia del gap (Playoffs - RegSeason) por año: %+.4f\n",
              slope))
  if (slope > 0) {
    cat("  → Playoffs se vuelve PROGRESIVAMENTE más predictivo con el tiempo.\n\n")
  } else {
    cat("  → No hay tendencia clara de cambio de era.\n\n")
  }
}

# Accuracy global por período
cat("=== ACCURACY POR PERÍODO ===\n\n")

periodos <- list(
  "2011-2014 (pre-Warriors)" = results %>% filter(year <= 2014),
  "2015-2018 (era Warriors)" = results %>% filter(year >= 2015, year <= 2018),
  "2019-2024 (moderna)"      = results %>% filter(year >= 2019)
)

cat(sprintf("  %-28s  %8s  %8s  %8s  %s\n",
            "Período", "RegAcc", "PlayAcc", "MixAcc", "Ventaja"))
cat(sprintf("  %s\n", paste(rep("-", 65), collapse="")))

for (nm in names(periodos)) {
  p <- periodos[[nm]]
  if (nrow(p) == 0) next
  reg_a  <- mean(p$reg_ok,  na.rm=TRUE)
  play_a <- mean(p$play_ok, na.rm=TRUE)
  mix_a  <- mean(p$mix_ok,  na.rm=TRUE)
  ventaja <- if (reg_a > play_a) "REG (+)" else if (play_a > reg_a) "PLAY (+)" else "EMPATE"
  cat(sprintf("  %-28s  %7.1f%%  %7.1f%%  %7.1f%%  %s\n",
              nm, reg_a*100, play_a*100, mix_a*100, ventaja))
}

# ---------------------------------------------------------------------------
# Guardar resultados
# ---------------------------------------------------------------------------
write_csv(results, "data/features/rolling_window_results.csv")
write_csv(rolling, "data/features/rolling_accuracy.csv")
cat("\nResultados guardados.\n")
