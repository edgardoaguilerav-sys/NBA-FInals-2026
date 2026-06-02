# =============================================================================
# NBA_model.R
# Predicción de ganador de NBA Finals — Rolling Window Validation
# Train: 2004-2018 | Test: 2019-2024 | Max 5 features | Target: won_finals
# =============================================================================

library(tidyverse)
library(glmnet)       # Logistic Regression (LASSO/Ridge)
library(randomForest)
library(xgboost)
library(caret)

# -----------------------------------------------------------------------------
# 1. CARGA Y LIMPIEZA
# -----------------------------------------------------------------------------
df_raw <- read_csv("data/features/finals_dataset.csv", show_col_types = FALSE)

# Eliminar features 100% NA y columnas no-predictivas
drop_cols <- c(
  "largest_lead_g4plus", "lead_changes_g4plus", "times_tied_g4plus",
  "star_ppg_trend",               # reemplazado por star_momentum
  "team_id",                      # identificador numérico (team_abbr se conserva)
  "reg_pts_pg", "reg_opp_pts_pg", # redundantes con reg_diff_pg y reg_net_rating
  "playoff_off_rating", "playoff_def_rating",  # redundantes con playoff_net_rating
  "reg_off_rating", "reg_def_rating"           # redundantes con reg_net_rating
)

df <- df_raw %>%
  select(-all_of(drop_cols)) %>%
  mutate(
    season_year = as.integer(substr(season, 1, 4)),
    won_finals  = factor(won_finals, levels = c(0, 1))
  )

cat("Dataset:", nrow(df), "filas x", ncol(df), "columnas\n")
cat("Temporadas:", paste(sort(unique(df$season_year)), collapse = ", "), "\n\n")

# -----------------------------------------------------------------------------
# 2. NORMALIZACIÓN ERA-SHIFT (en R, como establece arquitectura del proyecto)
# Escalar features numéricas por era para corregir inflación de ratings
# -----------------------------------------------------------------------------
df <- df %>%
  mutate(season_era = factor(season_era, levels = c("pre2010", "2010s", "2020s")))

# Features numéricas a escalar (excluir target, identifiers, flags binarios)
numeric_features <- df %>%
  select(where(is.numeric)) %>%
  select(-season_year, -is_shortened, -is_bubble,
         -has_reg_season_mvp, -had_7game_series,
         -blown_lead_g4plus, -ot_games_g4plus,
         -finals_appearances_last5, -championships_last5, -consecutive_finals,
         -playoff_seed, -n_g4plus_games) %>%
  names()

# Normalización Z-score por era
df <- df %>%
  group_by(season_era) %>%
  mutate(across(all_of(numeric_features),
                ~ (. - mean(., na.rm = TRUE)) / (sd(., na.rm = TRUE) + 1e-8),
                .names = "{.col}_z")) %>%
  ungroup()

cat("Features escaladas por era:", length(numeric_features), "\n\n")

# -----------------------------------------------------------------------------
# 3. FEATURE CANDIDATES
# Usar versiones normalizadas (_z) + features categóricas/binarias
# -----------------------------------------------------------------------------
z_features  <- paste0(numeric_features, "_z")
bin_features <- c("is_shortened", "is_bubble", "has_reg_season_mvp",
                  "had_7game_series", "blown_lead_g4plus",
                  "finals_appearances_last5", "championships_last5",
                  "consecutive_finals")

all_features <- c(z_features, bin_features)

# Eliminar features con NA residual (ej: clutch puede tener NAs)
na_pct <- df %>%
  select(all_of(all_features)) %>%
  summarise(across(everything(), ~ mean(is.na(.)))) %>%
  pivot_longer(everything(), names_to = "feature", values_to = "na_pct")

clean_features <- na_pct %>%
  filter(na_pct < 0.20) %>%          # max 20% NA
  pull(feature)

cat("Features candidatas (NA < 20%):", length(clean_features), "\n")
cat(paste(clean_features, collapse = "\n"), "\n\n")

# -----------------------------------------------------------------------------
# 4. ROLLING WINDOW VALIDATION
# Train: 2003-04 a 2017-18 | Test: 2019-20 a 2023-24
# -----------------------------------------------------------------------------
train_df <- df %>% filter(season_year <= 2017)
test_df  <- df %>% filter(season_year >= 2019)

cat("Train:", nrow(train_df), "obs |",
    "Test:", nrow(test_df), "obs\n\n")

# Imputar NA con mediana (del train) antes de modelar
impute_medians <- train_df %>%
  select(all_of(clean_features)) %>%
  summarise(across(everything(), ~ median(., na.rm = TRUE)))

impute_df <- function(data, medians) {
  for (col in names(medians)) {
    if (col %in% names(data)) {
      data[[col]][is.na(data[[col]])] <- medians[[col]]
    }
  }
  data
}

train_df <- impute_df(train_df, impute_medians)
test_df  <- impute_df(test_df,  impute_medians)

# Matrices para modelos
X_train <- train_df %>% select(all_of(clean_features)) %>% as.matrix()
y_train <- as.integer(train_df$won_finals) - 1   # 0/1
X_test  <- test_df  %>% select(all_of(clean_features)) %>% as.matrix()
y_test  <- as.integer(test_df$won_finals) - 1

# -----------------------------------------------------------------------------
# 5. SELECCIÓN DE FEATURES — LASSO (en train solamente)
# Selecciona las features más informativas respetando el límite de 5
# -----------------------------------------------------------------------------
set.seed(42)
cv_lasso <- cv.glmnet(X_train, y_train, family = "binomial", alpha = 1,
                      nfolds = 5, type.measure = "auc")

coef_lasso <- coef(cv_lasso, s = "lambda.1se")
selected_features <- rownames(coef_lasso)[which(abs(coef_lasso) > 0)]
selected_features <- selected_features[selected_features != "(Intercept)"]

# Limitar a top 5 por magnitud de coeficiente
if (length(selected_features) > 5) {
  coef_vals <- abs(coef_lasso[selected_features, 1])
  selected_features <- names(sort(coef_vals, decreasing = TRUE))[1:5]
}

cat("=== Features seleccionadas por LASSO (top", length(selected_features), ") ===\n")
print(coef_lasso[selected_features, 1])
cat("\n")

# Subsets con features seleccionadas
X_train_sel <- X_train[, selected_features, drop = FALSE]
X_test_sel  <- X_test[,  selected_features, drop = FALSE]

# -----------------------------------------------------------------------------
# 6. MODELOS
# -----------------------------------------------------------------------------

# --- 6a. Logistic Regression (LASSO con features seleccionadas) ---
lr_model <- glmnet(X_train_sel, y_train, family = "binomial", alpha = 1,
                   lambda = cv_lasso$lambda.1se)

lr_pred_prob <- predict(lr_model, X_test_sel, type = "response")[, 1]
lr_pred      <- ifelse(lr_pred_prob >= 0.5, 1, 0)

# --- 6b. Random Forest ---
set.seed(42)
rf_train <- data.frame(X_train_sel, won_finals = factor(y_train))
rf_model <- randomForest(won_finals ~ ., data = rf_train,
                         ntree = 500, mtry = max(1, floor(sqrt(length(selected_features)))),
                         importance = TRUE)

rf_pred_prob <- predict(rf_model, data.frame(X_test_sel), type = "prob")[, "1"]
rf_pred      <- ifelse(rf_pred_prob >= 0.5, 1, 0)

# --- 6c. XGBoost ---
set.seed(42)
dtrain <- xgb.DMatrix(X_train_sel, label = y_train)
dtest  <- xgb.DMatrix(X_test_sel,  label = y_test)

xgb_params <- list(
  objective        = "binary:logistic",
  eval_metric      = "auc",
  eta              = 0.05,
  max_depth        = 2,          # shallow para N pequeño
  subsample        = 0.8,
  colsample_bytree = 1.0,
  min_child_weight = 3
)

xgb_cv <- xgb.cv(params = xgb_params, data = dtrain,
                  nrounds = 200, nfold = 5, verbose = 0,
                  early_stopping_rounds = 20)

best_rounds <- if (!is.null(xgb_cv$best_iteration) && xgb_cv$best_iteration > 0)
                 xgb_cv$best_iteration else 50
xgb_model   <- xgb.train(params = xgb_params, data = dtrain,
                          nrounds = best_rounds, verbose = 0)

xgb_pred_prob <- predict(xgb_model, dtest)
xgb_pred      <- ifelse(xgb_pred_prob >= 0.5, 1, 0)

# -----------------------------------------------------------------------------
# 7. EVALUACIÓN
# Métricas por temporada de test (par ganador/perdedor → accuracy por Finals)
# -----------------------------------------------------------------------------
eval_by_season <- function(probs, preds, label) {
  test_seasons <- test_df$season_year

  results <- tibble(
    season   = test_df$season,
    year     = test_seasons,
    team     = test_df$team_abbr,
    actual   = y_test,
    prob     = probs,
    pred     = preds
  )

  # Por Finals: el equipo con mayor prob predicha es el ganador
  season_acc <- results %>%
    group_by(season) %>%
    summarise(
      correct = (prob[actual == 1] > prob[actual == 0]),
      .groups = "drop"
    )

  acc <- mean(season_acc$correct)
  cat(sprintf("  %s — Accuracy por Finals: %.1f%% (%d/%d)\n",
              label, acc * 100,
              sum(season_acc$correct), nrow(season_acc)))

  invisible(list(acc = acc, by_season = season_acc))
}

cat("=== RESULTADOS EN TEST (2019-2024) ===\n")
lr_res  <- eval_by_season(lr_pred_prob,  lr_pred,  "Logistic Regression")
rf_res  <- eval_by_season(rf_pred_prob,  rf_pred,  "Random Forest      ")
xgb_res <- eval_by_season(xgb_pred_prob, xgb_pred, "XGBoost            ")

# Detalle por temporada
cat("\n=== DETALLE POR TEMPORADA (modelo ganador = max prob) ===\n")
test_df_eval <- test_df %>%
  mutate(
    lr_prob  = lr_pred_prob,
    rf_prob  = rf_pred_prob,
    xgb_prob = xgb_pred_prob
  )

test_df_eval %>%
  group_by(season) %>%
  summarise(
    winner_actual = team_abbr[won_finals == 1],
    lr_pick       = team_abbr[lr_prob  == max(lr_prob)],
    rf_pick       = team_abbr[rf_prob  == max(rf_prob)],
    xgb_pick      = team_abbr[xgb_prob == max(xgb_prob)],
    .groups = "drop"
  ) %>%
  mutate(
    lr_ok  = (lr_pick  == winner_actual),
    rf_ok  = (rf_pick  == winner_actual),
    xgb_ok = (xgb_pick == winner_actual)
  ) %>%
  print(n = Inf)

# -----------------------------------------------------------------------------
# 8. FEATURE IMPORTANCE (Random Forest)
# -----------------------------------------------------------------------------
cat("\n=== FEATURE IMPORTANCE (Random Forest, MeanDecreaseAccuracy) ===\n")
imp <- importance(rf_model, type = 1) %>%
  as.data.frame() %>%
  rownames_to_column("feature") %>%
  arrange(desc(MeanDecreaseAccuracy))
print(imp)

# -----------------------------------------------------------------------------
# 9. GUARDAR RESULTADOS
# -----------------------------------------------------------------------------
results_summary <- tibble(
  model    = c("Logistic Regression", "Random Forest", "XGBoost"),
  accuracy = c(lr_res$acc, rf_res$acc, xgb_res$acc),
  n_test   = 6
)

write_csv(results_summary, "data/features/model_results.csv")
cat("\nResultados guardados en data/features/model_results.csv\n")
