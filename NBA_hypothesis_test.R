# =============================================================================
# NBA_hypothesis_test.R
# Hipótesis: ¿qué predice mejor al ganador de las Finals?
#   H1: rendimiento en temporada regular
#   H2: rendimiento en playoffs (pre-Finals)
#   H3: modelo mixto (LASSO elige libremente)
#
# Requiere haber corrido source("NBA_model.R") primero.
# =============================================================================

source("NBA_model.R")

cat("============================================================\n")
cat("  TEST DE HIPÓTESIS: Regular Season vs Playoffs\n")
cat("============================================================\n\n")

# -----------------------------------------------------------------------------
# Definir los grupos de features (versiones _z ya normalizadas)
# -----------------------------------------------------------------------------
reg_features <- c(
  "reg_diff_pg_z",
  "reg_net_rating_z",
  "reg_win_pct_z",
  "playoff_seed_z",
  "reg_pace_z"
)

playoff_features <- c(
  "playoff_net_rating_z",
  "playoff_tov_pct_z",
  "playoff_ts_pct_z",
  "playoff_pace_z",
  "playoff_pie_z",
  "clutch_tov_z",
  "clutch_win_pct_z",
  "clutch_pm_z",
  "win_pct_g4plus_z",
  "pre_finals_win_pct_z",
  "avg_point_diff_pre_z"
)

# Filtrar solo las que existen en el dataset limpio
reg_features     <- intersect(reg_features,     clean_features)
playoff_features <- intersect(playoff_features, clean_features)

cat(sprintf("Features de temporada regular disponibles: %d\n", length(reg_features)))
cat(paste(" ", reg_features, collapse = "\n"), "\n\n")
cat(sprintf("Features de playoffs disponibles: %d\n", length(playoff_features)))
cat(paste(" ", playoff_features, collapse = "\n"), "\n\n")

# -----------------------------------------------------------------------------
# Función genérica: train LASSO + RF en un subconjunto de features
# Retorna accuracy por Finals en test
# -----------------------------------------------------------------------------
eval_feature_group <- function(features, label, max_feat = 5) {
  Xtr <- X_train[, features, drop = FALSE]
  Xte <- X_test[,  features, drop = FALSE]

  # LASSO para seleccionar top features dentro del grupo
  set.seed(42)
  nfolds <- min(5, floor(nrow(Xtr) / 2))
  cv_fit <- cv.glmnet(Xtr, y_train, family = "binomial", alpha = 1,
                      nfolds = nfolds, type.measure = "deviance")

  coefs  <- coef(cv_fit, s = "lambda.1se")
  sel    <- rownames(coefs)[which(abs(coefs) > 0)]
  sel    <- sel[sel != "(Intercept)"]

  if (length(sel) == 0) sel <- features[1:min(2, length(features))]
  if (length(sel) > max_feat) {
    vals <- abs(coefs[sel, 1])
    sel  <- names(sort(vals, decreasing = TRUE))[1:max_feat]
  }

  cat(sprintf("  [%s] Features seleccionadas: %s\n", label,
              paste(sel, collapse = ", ")))

  Xtr_s <- Xtr[, sel, drop = FALSE]
  Xte_s <- Xte[, sel, drop = FALSE]

  # Random Forest
  set.seed(42)
  rf_fit <- randomForest(
    won_finals ~ .,
    data  = data.frame(Xtr_s, won_finals = factor(y_train)),
    ntree = 500, importance = FALSE
  )
  rf_prob <- predict(rf_fit, newdata = data.frame(Xte_s), type = "prob")[, "1"]

  # Logistic (glmnet)
  lr_fit  <- glmnet(Xtr_s, y_train, family = "binomial", alpha = 1,
                    lambda = cv_fit$lambda.1se)
  lr_prob <- predict(lr_fit, Xte_s, type = "response")[, 1]

  # Accuracy por Finals (ganador = mayor prob)
  seasons_test <- unique(test_df$season)
  correct_rf <- correct_lr <- 0

  for (s in seasons_test) {
    idx    <- which(test_df$season == s)
    actual <- test_df$team_abbr[idx[which(y_test[idx] == 1)]]
    if (test_df$team_abbr[idx[which.max(rf_prob[idx])]] == actual) correct_rf <- correct_rf + 1
    if (test_df$team_abbr[idx[which.max(lr_prob[idx])]] == actual) correct_lr <- correct_lr + 1
  }

  n <- length(seasons_test)
  list(
    label      = label,
    features   = sel,
    rf_acc     = correct_rf / n,
    lr_acc     = correct_lr / n,
    rf_prob    = rf_prob,
    lr_prob    = lr_prob,
    rf_model   = rf_fit,
    lr_model   = lr_fit,
    sel        = sel
  )
}

# -----------------------------------------------------------------------------
# Correr los 3 grupos
# -----------------------------------------------------------------------------
cat("--- Evaluando grupos ---\n\n")
res_reg     <- eval_feature_group(reg_features,     "REG SEASON")
res_playoff <- eval_feature_group(playoff_features, "PLAYOFFS  ")

# Mixto: usar el modelo ya entrenado (all_features + LASSO)
mixed_rf_prob <- rf_pred_prob   # del NBA_model.R
mixed_lr_prob <- lr_pred_prob

seasons_test <- unique(test_df$season)
correct_mixed_rf <- correct_mixed_lr <- 0
for (s in seasons_test) {
  idx    <- which(test_df$season == s)
  actual <- test_df$team_abbr[idx[which(y_test[idx] == 1)]]
  if (test_df$team_abbr[idx[which.max(mixed_rf_prob[idx])]] == actual) correct_mixed_rf <- correct_mixed_rf + 1
  if (test_df$team_abbr[idx[which.max(mixed_lr_prob[idx])]] == actual) correct_mixed_lr <- correct_mixed_lr + 1
}
n <- length(seasons_test)

# -----------------------------------------------------------------------------
# Tabla comparativa
# -----------------------------------------------------------------------------
cat("\n")
cat("============================================================\n")
cat("  RESULTADO: ¿Qué predice mejor al ganador de las Finals?\n")
cat("============================================================\n\n")

results_tbl <- tibble(
  Grupo              = c("Temporada Regular", "Playoffs pre-Finals", "Mixto (LASSO)"),
  N_features         = c(length(res_reg$features),
                         length(res_playoff$features),
                         length(selected_features)),
  Accuracy_RF        = c(res_reg$rf_acc, res_playoff$rf_acc, correct_mixed_rf/n),
  Accuracy_LR        = c(res_reg$lr_acc, res_playoff$lr_acc, correct_mixed_lr/n),
  Features           = c(paste(res_reg$features,     collapse = " | "),
                         paste(res_playoff$features, collapse = " | "),
                         paste(selected_features,    collapse = " | "))
)

cat(sprintf("  %-22s  %6s  %6s  Features\n", "Grupo", "RF", "LR"))
cat(sprintf("  %s\n", paste(rep("-", 70), collapse="")))
for (i in 1:nrow(results_tbl)) {
  cat(sprintf("  %-22s  %5.1f%%  %5.1f%%\n",
              results_tbl$Grupo[i],
              results_tbl$Accuracy_RF[i] * 100,
              results_tbl$Accuracy_LR[i] * 100))
}

cat("\nFeatures seleccionadas por grupo:\n")
cat(sprintf("  Reg Season: %s\n", paste(res_reg$features,     collapse = ", ")))
cat(sprintf("  Playoffs:   %s\n", paste(res_playoff$features, collapse = ", ")))
cat(sprintf("  Mixto:      %s\n", paste(selected_features,    collapse = ", ")))

# -----------------------------------------------------------------------------
# Detalle por temporada para cada grupo
# -----------------------------------------------------------------------------
cat("\n--- Detalle por temporada ---\n\n")

detail <- test_df %>%
  mutate(
    reg_rf   = res_reg$rf_prob,
    reg_lr   = res_reg$lr_prob,
    play_rf  = res_playoff$rf_prob,
    play_lr  = res_playoff$lr_prob
  )

detail %>%
  group_by(season) %>%
  summarise(
    ganador      = team_abbr[won_finals == 1],
    reg_rf_pick  = team_abbr[reg_rf  == max(reg_rf)],
    play_rf_pick = team_abbr[play_rf == max(play_rf)],
    mix_rf_pick  = team_abbr[which.max(mixed_rf_prob[cur_group_rows()])],
    .groups = "drop"
  ) %>%
  mutate(
    reg_ok  = (reg_rf_pick  == ganador),
    play_ok = (play_rf_pick == ganador),
    mix_ok  = (mix_rf_pick  == ganador)
  ) %>%
  rename(
    `Ganador real` = ganador,
    `Reg (RF)`     = reg_rf_pick,
    `Playoff (RF)` = play_rf_pick,
    `Mixto (RF)`   = mix_rf_pick
  ) %>%
  print(n = Inf)

# -----------------------------------------------------------------------------
# Predicción 2026 con el modelo ganador de la hipótesis
# -----------------------------------------------------------------------------
cat("\n============================================================\n")
cat("  PREDICCIÓN 2026 CON MODELO DE PLAYOFFS\n")
cat("============================================================\n\n")

# Datos 2026 disponibles para features de playoffs
# playoff_net_rating: Spurs +10.4, Knicks +20.1
# playoff_tov_pct: estimado Spurs 13.0, Knicks 11.5
# clutch_tov: estimado Spurs 8.5, Knicks 6.5
# win_pct_g4plus: Spurs ~0.67, Knicks ~0.78
# pre_finals_win_pct: Spurs 12/18=.667, Knicks 12/14=.857
# avg_point_diff_pre: Spurs +10.3, Knicks +19.3

# Normalizar usando era "modern" (2015+)
era_pl <- df_raw %>%
  mutate(year = as.integer(substr(season, 1, 4))) %>%
  filter(year >= 2015) %>%
  summarise(
    m_net    = mean(playoff_net_rating,  na.rm=T), sd_net  = sd(playoff_net_rating,  na.rm=T)+1e-8,
    m_tov    = mean(playoff_tov_pct,     na.rm=T), sd_tov  = sd(playoff_tov_pct,     na.rm=T)+1e-8,
    m_cts    = mean(clutch_tov,          na.rm=T), sd_cts  = sd(clutch_tov,          na.rm=T)+1e-8,
    m_g4p    = mean(win_pct_g4plus,      na.rm=T), sd_g4p  = sd(win_pct_g4plus,      na.rm=T)+1e-8,
    m_wcp    = mean(pre_finals_win_pct,  na.rm=T), sd_wcp  = sd(pre_finals_win_pct,  na.rm=T)+1e-8,
    m_diff   = mean(avg_point_diff_pre,  na.rm=T), sd_diff = sd(avg_point_diff_pre,  na.rm=T)+1e-8
  )

z <- function(val, m, s) (val - m) / s

# Spurs 2026
sp <- list(
  playoff_net_rating_z  = z(10.4, era_pl$m_net,  era_pl$sd_net),
  playoff_tov_pct_z     = z(13.0, era_pl$m_tov,  era_pl$sd_tov),
  clutch_tov_z          = z(8.5,  era_pl$m_cts,  era_pl$sd_cts),
  win_pct_g4plus_z      = z(0.67, era_pl$m_g4p,  era_pl$sd_g4p),
  pre_finals_win_pct_z  = z(0.667,era_pl$m_wcp,  era_pl$sd_wcp),
  avg_point_diff_pre_z  = z(10.3, era_pl$m_diff, era_pl$sd_diff)
)

# Knicks 2026
kn <- list(
  playoff_net_rating_z  = z(20.1, era_pl$m_net,  era_pl$sd_net),
  playoff_tov_pct_z     = z(11.5, era_pl$m_tov,  era_pl$sd_tov),
  clutch_tov_z          = z(6.5,  era_pl$m_cts,  era_pl$sd_cts),
  win_pct_g4plus_z      = z(0.78, era_pl$m_g4p,  era_pl$sd_g4p),
  pre_finals_win_pct_z  = z(0.857,era_pl$m_wcp,  era_pl$sd_wcp),
  avg_point_diff_pre_z  = z(19.3, era_pl$m_diff, era_pl$sd_diff)
)

# Usar solo las features que el modelo de playoffs seleccionó
sel_pl <- res_playoff$sel
sp_vec <- sapply(sel_pl, function(f) if (!is.null(sp[[f]])) sp[[f]] else 0)
kn_vec <- sapply(sel_pl, function(f) if (!is.null(kn[[f]])) kn[[f]] else 0)

cat(sprintf("Features del modelo playoffs: %s\n\n", paste(sel_pl, collapse=", ")))

cat("Valores z normalizados 2026:\n")
cat(sprintf("  %-28s  %8s  %8s\n", "Feature", "Spurs", "Knicks"))
cat(sprintf("  %s\n", paste(rep("-", 48), collapse="")))
for (f in sel_pl) {
  obs <- if (!is.null(sp[[f]])) "*" else ""
  cat(sprintf("  %-28s  %8.3f  %8.3f%s\n", f, sp_vec[f], kn_vec[f], obs))
}
cat("  (* = estimado)\n\n")

new_sp <- matrix(sp_vec, nrow=1, dimnames=list(NULL, sel_pl))
new_kn <- matrix(kn_vec, nrow=1, dimnames=list(NULL, sel_pl))

prob_sp <- predict(res_playoff$rf_model, data.frame(new_sp), type="prob")[,"1"]
prob_kn <- predict(res_playoff$rf_model, data.frame(new_kn), type="prob")[,"1"]

norm2 <- function(a, b) c(a/(a+b), b/(a+b))
probs <- norm2(prob_sp, prob_kn)

cat(sprintf("  Modelo Playoffs RF:  Spurs %.1f%%  —  Knicks %.1f%%\n",
            probs[1]*100, probs[2]*100))
cat(sprintf("  Predicción: %s\n\n",
            ifelse(probs[1] > probs[2], "SPURS", "KNICKS")))

# Guardar tabla comparativa
write_csv(results_tbl %>% select(-Features), "data/features/hypothesis_test.csv")
cat("Tabla guardada en data/features/hypothesis_test.csv\n")
