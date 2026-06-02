# =============================================================================
# NBA_advanced_analysis.R
# Análisis 2-6:
#   2. Factor fatiga (games played + Game 7 en Conf. Finals)
#   3. Monte Carlo — simulación de la serie 7 partidos
#   4. Dynasty penalty — primeros campeones históricos
#   5. Upset analysis — cuando ambos modelos fallan
#   6. Asimetría de conferencia (Este vs Oeste)
# =============================================================================
# Requiere: source("NBA_model.R") corrido antes, o se corre al inicio.
# =============================================================================

source("NBA_model.R")

cat("\n============================================================\n")
cat("  ANÁLISIS 2-6: NBA Finals Predictor — Insights Avanzados\n")
cat("============================================================\n\n")

# =============================================================================
# ANÁLISIS 2: FACTOR FATIGA
# =============================================================================
cat("------------------------------------------------------------\n")
cat("ANÁLISIS 2: ¿El desgaste de playoffs predice el ganador?\n")
cat("------------------------------------------------------------\n\n")

# games_played_pre_finals ya está en el dataset
# Agregar: ¿tuvo Game 7 en Conf. Finals específicamente?
# Proxy: max_series_length == 7 (captura cualquier serie de 7)
# Variable directa: si el equipo jugó más partidos = más desgaste

fatigue_df <- df_raw %>%
  mutate(year = as.integer(substr(season, 1, 4))) %>%
  select(season, year, team_abbr, won_finals, games_played_pre_finals,
         had_7game_series, rest_days_before_finals, max_series_length)

# ¿Equipo con menos partidos jugados pre-Finals gana más?
fatigue_summary <- fatigue_df %>%
  group_by(season) %>%
  summarise(
    winner          = team_abbr[won_finals == 1],
    loser           = team_abbr[won_finals == 0],
    winner_games    = games_played_pre_finals[won_finals == 1],
    loser_games     = games_played_pre_finals[won_finals == 0],
    winner_rested   = rest_days_before_finals[won_finals == 1],
    loser_rested    = rest_days_before_finals[won_finals == 0],
    fresher_won     = (winner_games <= loser_games),
    .groups = "drop"
  )

cat(sprintf("Equipo con MENOS partidos jugados gana: %d/%d (%.1f%%)\n",
            sum(fatigue_summary$fresher_won, na.rm=TRUE),
            sum(!is.na(fatigue_summary$fresher_won)),
            mean(fatigue_summary$fresher_won, na.rm=TRUE)*100))

# Correlación entre diferencia de partidos y resultado
fatigue_summary <- fatigue_summary %>%
  mutate(game_diff = winner_games - loser_games)

cat(sprintf("Diferencia promedio de partidos (winner - loser): %.2f\n",
            mean(fatigue_summary$game_diff, na.rm=TRUE)))
cat(sprintf("  Ganadores jugaron en promedio %.1f partidos pre-Finals\n",
            mean(fatigue_summary$winner_games, na.rm=TRUE)))
cat(sprintf("  Perdedores jugaron en promedio %.1f partidos pre-Finals\n\n",
            mean(fatigue_summary$loser_games, na.rm=TRUE)))

# ¿Descanso importa?
cat("Correlación días de descanso vs ganó Finals:\n")
rest_cor <- cor(as.numeric(df_raw$won_finals),
                df_raw$rest_days_before_finals, use="complete.obs")
cat(sprintf("  r = %.3f\n\n", rest_cor))

# Aplicar a 2026: Spurs jugaron 18 pre-Finals, Knicks jugaron 14
cat("Aplicación a Finals 2026:\n")
cat("  Spurs: 18 partidos pre-Finals (12-6, incluyendo Game 7 vs OKC)\n")
cat("  Knicks: 14 partidos pre-Finals (12-2, sin Game 7)\n")
cat(sprintf("  Diferencia: +4 partidos a favor de los Knicks\n"))
cat(sprintf("  Históricamente el equipo con menos desgaste gana el %.1f%% de las veces\n\n",
            mean(fatigue_summary$fresher_won, na.rm=TRUE)*100))

# Distribución por tamaño de diferencia
cat("¿Cuánto importa la magnitud de la diferencia?\n")
fatigue_summary %>%
  mutate(diff_bucket = case_when(
    game_diff <= -3 ~ "Winner jugó 3+ menos",
    game_diff < 0   ~ "Winner jugó 1-2 menos",
    game_diff == 0  ~ "Igual",
    game_diff > 0   ~ "Winner jugó más"
  )) %>%
  count(diff_bucket) %>%
  print()

cat("\n")

# =============================================================================
# ANÁLISIS 3: MONTE CARLO — simulación de la serie
# =============================================================================
cat("------------------------------------------------------------\n")
cat("ANÁLISIS 3: Monte Carlo — ¿Cuántos partidos durará la serie?\n")
cat("------------------------------------------------------------\n\n")

set.seed(42)
N_SIM <- 100000

# Probabilidades base del modelo de playoffs (más preciso en era moderna)
# Knicks 57.4%, Spurs 42.6% (del NBA_predict_2026.R)
P_KNICKS <- 0.574
P_SPURS  <- 1 - P_KNICKS

# Ajuste por ventaja de cancha (Spurs tienen Games 1,2,5,7 en casa)
# Históricamente: equipo local gana ~56% de los partidos de Finals
HOME_ADVANTAGE <- 0.56  # P(local gana) cuando equipos iguales

# Home schedule NBA Finals: 1,2 → local; 3,4 → visitante; 5 → local; 6 → visitante; 7 → local
# "Local" = Spurs (tienen el mejor record)
home_team <- c("SAS","SAS","NYK","NYK","SAS","NYK","SAS")  # equipo local por partido

simulate_series <- function(p_away_win, n_sims = N_SIM) {
  # p_away_win = P(visitante gana un partido) cuando no hay HCA
  wins_sas <- wins_nyk <- series_lengths <- numeric(n_sims)

  for (i in 1:n_sims) {
    w_sas <- 0; w_nyk <- 0; game_num <- 0

    while (w_sas < 4 && w_nyk < 4) {
      game_num <- game_num + 1
      local <- home_team[game_num]

      # Ajustar por home court
      if (local == "SAS") {
        p_sas_wins_game <- P_SPURS + HOME_ADVANTAGE * (1 - 2*P_SPURS) * 0.5
      } else {
        p_sas_wins_game <- P_SPURS - HOME_ADVANTAGE * (1 - 2*P_SPURS) * 0.5
      }
      p_sas_wins_game <- max(0.05, min(0.95, p_sas_wins_game))

      if (runif(1) < p_sas_wins_game) w_sas <- w_sas + 1
      else                             w_nyk <- w_nyk + 1
    }

    wins_sas[i]       <- w_sas
    wins_nyk[i]       <- w_nyk
    series_lengths[i] <- w_sas + w_nyk
  }

  list(wins_sas = wins_sas, wins_nyk = wins_nyk, lengths = series_lengths)
}

sim <- simulate_series(P_SPURS)

knicks_win_pct <- mean(sim$wins_nyk == 4)
spurs_win_pct  <- mean(sim$wins_sas == 4)

cat(sprintf("Simulación con %s iteraciones:\n\n", format(N_SIM, big.mark=",")))
cat(sprintf("  P(Knicks ganan la serie):  %.1f%%\n", knicks_win_pct * 100))
cat(sprintf("  P(Spurs ganan la serie):   %.1f%%\n\n", spurs_win_pct  * 100))

# Distribución de longitud de serie
length_dist <- table(sim$lengths) / N_SIM * 100
cat("Distribución de longitud de la serie:\n")
for (nm in names(length_dist)) {
  bar <- paste(rep("█", round(length_dist[nm]/3)), collapse="")
  cat(sprintf("  %s partidos: %5.1f%%  %s\n", nm, length_dist[nm], bar))
}

# Quién gana en cada longitud
cat("\nQuién gana según longitud de serie:\n")
results_by_length <- data.frame(
  length  = sim$lengths,
  knicks  = sim$wins_nyk == 4
) %>%
  group_by(length) %>%
  summarise(
    pct_knicks = mean(knicks) * 100,
    pct_spurs  = (1 - mean(knicks)) * 100,
    n          = n(),
    .groups = "drop"
  ) %>%
  mutate(pct_total = n / N_SIM * 100)

cat(sprintf("  %-10s  %8s  %8s  %8s\n", "Partidos", "Knicks%", "Spurs%", "P(escenario)"))
cat(sprintf("  %s\n", paste(rep("-", 42), collapse="")))
for (i in 1:nrow(results_by_length)) {
  r <- results_by_length[i, ]
  cat(sprintf("  %-10s  %7.1f%%  %7.1f%%  %7.1f%%\n",
              paste0(r$length, " games"),
              r$pct_knicks, r$pct_spurs, r$pct_total))
}

# Escenario más probable
most_likely <- results_by_length %>%
  arrange(desc(n)) %>%
  slice(1)
winner_ml <- if (most_likely$pct_knicks > 50) "KNICKS" else "SPURS"
cat(sprintf("\nEscenario más probable: %s gana en %d partidos (%.1f%% del tiempo)\n\n",
            winner_ml, most_likely$length, most_likely$pct_total))

# =============================================================================
# ANÁLISIS 4: DYNASTY PENALTY — primeros campeones históricos
# =============================================================================
cat("------------------------------------------------------------\n")
cat("ANÁLISIS 4: Dynasty penalty — primeros campeones\n")
cat("------------------------------------------------------------\n\n")

dynasty_df <- df_raw %>%
  filter(won_finals == 1) %>%
  mutate(
    is_first_champ = (consecutive_finals == 0 | is.na(consecutive_finals)) &
                     (championships_last5 == 0 | is.na(championships_last5))
  ) %>%
  select(season, team_abbr, consecutive_finals, championships_last5,
         finals_appearances_last5, is_first_champ)

cat("Ganadores sin historial reciente de Finals:\n")
dynasty_df %>%
  filter(is_first_champ | finals_appearances_last5 == 0) %>%
  select(season, team_abbr, finals_appearances_last5, championships_last5) %>%
  print()

cat(sprintf("\nDe %d campeones, %d (%.1f%%) llegaron sin historial reciente.\n",
            nrow(dynasty_df),
            sum(dynasty_df$is_first_champ | dynasty_df$finals_appearances_last5 == 0),
            mean(dynasty_df$is_first_champ | dynasty_df$finals_appearances_last5 == 0)*100))

# ¿Los perdedores con más historial tienden a perder?
cat("\n¿El exceso de historial es una desventaja? (fatiga de dynasty)\n")
dynasty_compare <- df_raw %>%
  group_by(season) %>%
  summarise(
    dynasty_diff = finals_appearances_last5[won_finals == 1] -
                   finals_appearances_last5[won_finals == 0],
    champ_had_more_history = dynasty_diff >= 0,
    .groups = "drop"
  )

cat(sprintf("Ganador tenía IGUAL O MÁS historial que perdedor: %.1f%% de las veces\n",
            mean(dynasty_compare$champ_had_more_history, na.rm=TRUE)*100))

# Aplicar a 2026
cat("\nAplicación a Finals 2026:\n")
cat("  Spurs: vuelven a Finals por primera vez desde 2014. Appearances_last5 ≈ 0.\n")
cat("  Knicks: primera Finals desde 1999. Appearances_last5 = 0.\n")
cat("  Ambos equipos son 'primeros campeones' potenciales → el modelo de dynasty no aplica.\n\n")

# =============================================================================
# ANÁLISIS 5: UPSET ANALYSIS — cuando ambos modelos fallan
# =============================================================================
cat("------------------------------------------------------------\n")
cat("ANÁLISIS 5: Upsets — cuando ningún modelo predice bien\n")
cat("------------------------------------------------------------\n\n")

# Los dos grandes upsets: CLE 2016 (remontó 1-3), TOR 2019
upsets <- df_raw %>%
  filter(season %in% c("2015-16", "2018-19")) %>%
  select(season, team_abbr, won_finals, reg_win_pct, playoff_net_rating,
         playoff_seed, rest_days_before_finals, avg_point_diff_pre,
         pre_finals_win_pct, clutch_win_pct)

cat("Datos de los dos grandes upsets:\n")
print(upsets)

# Patrón común
cat("\nPatrón común en los upsets:\n")
upsets %>%
  group_by(season) %>%
  summarise(
    upset_winner     = team_abbr[won_finals == 1],
    upset_loser      = team_abbr[won_finals == 0],
    winner_reg_seed  = playoff_seed[won_finals == 1],
    loser_reg_seed   = playoff_seed[won_finals == 0],
    winner_pref_win  = pre_finals_win_pct[won_finals == 1],
    loser_pref_win   = pre_finals_win_pct[won_finals == 0],
    winner_clutch    = clutch_win_pct[won_finals == 1],
    loser_clutch     = clutch_win_pct[won_finals == 0],
    .groups = "drop"
  ) %>%
  print()

cat("\nHipótesis sobre los upsets:\n")
cat("  - CLE 2016: Cleveland remontó 1-3. LeBron jugó el mejor playoff de su carrera.\n")
cat("    Los Warriors tenían mejor seed, mejor reg season, mejor playoff net rating.\n")
cat("    Lo que no captura el modelo: injuries (Bogut, Love), fatiga de 3 años de Finals.\n")
cat("  - TOR 2019: Golden State perdió a Durant y Klay en la serie.\n")
cat("    El modelo de reg season no captura injuries en tiempo real.\n")
cat("  CONCLUSIÓN: Los upsets correlacionan con INJURIES a jugadores clave,\n")
cat("  que ningún modelo estadístico puede anticipar ex-ante.\n\n")

# Feature propuesta: índice de vulnerabilidad (edad promedio de top-3 jugadores)
cat("Feature candidata para mitigar upsets: profundidad del roster\n")
cat("  (requeriría datos de jugador que están fuera del pipeline actual)\n\n")

# =============================================================================
# ANÁLISIS 6: ASIMETRÍA DE CONFERENCIA
# =============================================================================
cat("------------------------------------------------------------\n")
cat("ANÁLISIS 6: ¿Este o Oeste? — Asimetría de conferencia\n")
cat("------------------------------------------------------------\n\n")

conference_df <- df_raw %>%
  filter(won_finals == 1) %>%
  mutate(
    year = as.integer(substr(season, 1, 4)),
    era  = case_when(
      year < 2010 ~ "pre2010",
      year < 2015 ~ "post2010",
      TRUE        ~ "modern"
    )
  ) %>%
  select(season, year, era, team_abbr, conference)

cat("Ganadores por conferencia (todos los años):\n")
conference_df %>%
  count(conference, name = "campeonatos") %>%
  mutate(pct = campeonatos / sum(campeonatos) * 100) %>%
  print()

cat("\nGanadores por conferencia y era:\n")
conference_df %>%
  count(era, conference) %>%
  pivot_wider(names_from = conference, values_from = n, values_fill = 0) %>%
  mutate(total = E + W,
         pct_W = round(W / total * 100, 1)) %>%
  arrange(era) %>%
  print()

cat("\nCampeonatos del Oeste por era:\n")
eras_tbl <- conference_df %>%
  mutate(won_west = (conference == "W")) %>%
  group_by(era) %>%
  summarise(pct_west = mean(won_west)*100, n=n(), .groups="drop")
for(i in 1:nrow(eras_tbl)) {
  cat(sprintf("  %s: Oeste ganó %.0f%% (%d Finals)\n",
              eras_tbl$era[i], eras_tbl$pct_west[i], eras_tbl$n[i]))
}

cat("\nHistorial reciente (últimas 5 Finals, 2019-2023):\n")
conference_df %>%
  filter(year >= 2019) %>%
  select(season, team_abbr, conference) %>%
  mutate(conf_label = ifelse(conference=="W","OESTE","ESTE")) %>%
  print()

cat("\nAplicación a Finals 2026:\n")
cat("  Spurs = Conferencia OESTE\n")
cat("  Knicks = Conferencia ESTE\n")
recent_west_pct <- conference_df %>%
  filter(year >= 2019) %>%
  summarise(pct = mean(conference=="W")*100) %>% pull(pct)
cat(sprintf("  En era moderna (2019+): Oeste gana %.0f%% de las Finals\n", recent_west_pct))
modern_west_pct <- eras_tbl %>% filter(era=="modern") %>% pull(pct_west)
cat(sprintf("  En era moderna completa (2015+): Oeste gana %.0f%% de las Finals\n\n", modern_west_pct))

# =============================================================================
# RESUMEN CONSOLIDADO PARA 2026
# =============================================================================
cat("============================================================\n")
cat("  SÍNTESIS: TODOS LOS ÁNGULOS PARA FINALS 2026\n")
cat("============================================================\n\n")

cat(sprintf("  %-35s  %-8s  %-8s\n", "Factor", "Spurs", "Knicks"))
cat(sprintf("  %s\n", paste(rep("-", 55), collapse="")))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Modelo mixto (reg season dom.)", "61.8%", "38.2%"))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Modelo playoffs (era moderna)", "42.6%", "57.4%"))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Monte Carlo (con HCA)", sprintf("%.1f%%",spurs_win_pct*100), sprintf("%.1f%%",knicks_win_pct*100)))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Factor fatiga (juegos pre-Finals)", "18 (+4)", "14"))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Dynasty penalty", "Neutral", "Neutral"))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Conf. histórica (era moderna)", "Oeste=fav", "Este"))
cat(sprintf("  %-35s  %-8s  %-8s\n", "Racha de playoffs", "OK", "+11 (+23.8)"))

cat(sprintf("\n  Escenario más probable según Monte Carlo: %s gana en %d partidos\n",
            winner_ml, most_likely$length))
cat(sprintf("  Serie a 7 partidos: %.1f%% de probabilidad\n",
            length_dist["7"]))
cat("\n  PREDICCIÓN INTEGRADA: el peso de la evidencia favorece a los KNICKS.\n")
cat("  Cuatro de los seis factores los favorecen (modelo playoffs,\n")
cat("  Monte Carlo, fatiga, racha). Spurs ganan en reg season y conferencia.\n")
cat("  El factor que podría cambiar el resultado: injuries o clutch_tov real.\n\n")

# Guardar resumen
summary_df <- tibble(
  factor     = c("Modelo mixto (Spurs%)", "Modelo playoffs (Knicks%)",
                 "Monte Carlo (Knicks%)", "Factor fatiga (juegos extra Spurs)",
                 "Escenario más probable"),
  valor      = c(sprintf("%.1f%%", 61.8),
                 sprintf("%.1f%%", knicks_win_pct*100),
                 sprintf("%.1f%%", knicks_win_pct*100),
                 "+4 partidos",
                 sprintf("%s en %d", winner_ml, most_likely$length))
)
write_csv(summary_df, "data/features/analysis_2026_summary.csv")
cat("Resumen guardado en data/features/analysis_2026_summary.csv\n")
