"""
build_features.py
-----------------
Fase 2: construye el dataset de features a partir de los CSVs crudos.
No llama a la API — trabaja solo con los archivos de data/raw/.

Salida:
    data/features/finals_dataset.csv     ← 1 fila por equipo-año (~40 filas)
    data/features/finals_dataset_diff.csv ← 1 fila por Finals-año (~20 filas)
                                             con features diferenciales (winner - loser)

Uso:
    python build_features.py
    python build_features.py --season 2022-23   # debug de una temporada
"""

import sys
import warnings
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from finals_config import (
    FINALS_HISTORY, SEASONS, get_finalist_ids, get_season_flags,
    has_reg_season_mvp, TEAM_ABBR
)

DATA_DIR     = Path("data/raw")
FEATURES_DIR = Path("data/features")
FEATURES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# HELPERS DE LECTURA
# ---------------------------------------------------------------------------
def read_csv_safe(path: Path) -> pd.DataFrame:
    """Lee CSV, retorna DataFrame vacío si no existe."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def get_season_dir(season: str) -> Path:
    return DATA_DIR / season.replace("-", "_")


# ---------------------------------------------------------------------------
# BLOQUE 1: Momentum pre-Finals
# ---------------------------------------------------------------------------
def compute_momentum(gamelog_df: pd.DataFrame, series_df: pd.DataFrame,
                     team_id: int, winner_id: int, loser_id: int) -> dict:
    """
    Computa features de momentum pre-Finals para un equipo.
    Usa: LeagueGameLog + CommonPlayoffSeries
    """
    finals_series = series_df[series_df["SERIES_ID"].str[7] == "4"]
    finals_game_ids = set(finals_series["GAME_ID"].astype(str))

    # Partidos pre-Finals del equipo
    team_pre = gamelog_df[
        (gamelog_df["TEAM_ID"] == team_id) &
        (~gamelog_df["GAME_ID"].astype(str).isin(finals_game_ids))
    ].copy()

    if team_pre.empty:
        return {}

    wins   = (team_pre["WL"] == "W").sum()
    losses = (team_pre["WL"] == "L").sum()
    total_games = wins + losses

    # Longitud máxima de serie
    team_game_ids = set(team_pre["GAME_ID"].astype(str))
    team_series = series_df[
        (series_df["GAME_ID"].astype(str).isin(team_game_ids)) &
        (series_df["SERIES_ID"].str[7] != "4")
    ]
    max_series_len = 0
    for sid, grp in team_series.groupby("SERIES_ID"):
        max_series_len = max(max_series_len, grp["GAME_NUM"].max())

    # Overtime: partidos con PTS_QTR1 = sumatorio que no cuadra (lo detectamos en box_summary)
    # Aquí solo usamos PLUS_MINUS del gamelog como proxy de dominancia
    avg_plus_minus = team_pre["PLUS_MINUS"].mean()

    # Rest days: distancia entre último juego pre-Finals y G1 de Finals
    finalist_games = gamelog_df[gamelog_df["TEAM_ID"].isin([winner_id, loser_id])].copy()
    finalist_games["GAME_DATE"] = pd.to_datetime(finalist_games["GAME_DATE"])
    team_pre["GAME_DATE"] = pd.to_datetime(team_pre["GAME_DATE"])
    date_counts = finalist_games.groupby("GAME_DATE")["TEAM_ID"].nunique()
    finals_dates = date_counts[date_counts == 2].index

    rest_days = None
    if len(finals_dates) > 0:
        finals_g1 = finals_dates.min()
        last_pre  = team_pre["GAME_DATE"].max()
        rest_days = (finals_g1 - last_pre).days

    return {
        "pre_finals_wins":          int(wins),
        "pre_finals_losses":        int(losses),
        "pre_finals_win_pct":       round(wins / total_games, 4) if total_games > 0 else None,
        "games_played_pre_finals":  int(total_games),
        "avg_point_diff_pre":       round(avg_plus_minus, 2),
        "max_series_length":        int(max_series_len),
        "had_7game_series":         int(max_series_len == 7),
        "rest_days_before_finals":  rest_days,
    }


# ---------------------------------------------------------------------------
# BLOQUE 2: Rendimiento en Game 4+ (eliminación)
# ---------------------------------------------------------------------------
def compute_g4plus(season_dir: Path, series_df: pd.DataFrame,
                   gamelog_df: pd.DataFrame, team_id: int,
                   winner_id: int, loser_id: int) -> dict:
    """
    Computa features de partidos de eliminación (GAME_NUM >= 4) pre-Finals.
    Usa: BoxScoreTraditionalV2 + BoxScoreSummaryV2 + CommonPlayoffSeries
    """
    finals_series = series_df[series_df["SERIES_ID"].str[7] == "4"]
    finals_game_ids = set(finals_series["GAME_ID"].astype(str))

    # Identificar game_ids de G4+ pre-Finals para este equipo
    team_pre = gamelog_df[
        (gamelog_df["TEAM_ID"] == team_id) &
        (~gamelog_df["GAME_ID"].astype(str).isin(finals_game_ids))
    ]
    team_game_ids = set(team_pre["GAME_ID"].astype(str))

    # GAME_NUM >= 4 de las series del equipo
    team_series = series_df[
        (series_df["GAME_ID"].astype(str).isin(team_game_ids)) &
        (series_df["SERIES_ID"].str[7] != "4") &
        (series_df["GAME_NUM"] >= 4)
    ]
    g4plus_ids = team_series["GAME_ID"].astype(str).tolist()

    if not g4plus_ids:
        return {k: None for k in [
            "pts_per_game_g4plus", "point_diff_g4plus", "win_pct_g4plus",
            "largest_lead_g4plus", "lead_changes_g4plus", "times_tied_g4plus",
            "blown_lead_g4plus", "ot_games_g4plus"
        ]}

    pts_list, diff_list, wl_list = [], [], []
    largest_lead_list, lead_changes_list, times_tied_list = [], [], []
    blown_leads = 0
    ot_games = 0

    for gid in g4plus_ids:
        # Traditional box score — TeamStats (level=team)
        trad = read_csv_safe(season_dir / f"box_traditional_{gid}.csv")
        trad_team = trad[(trad.get("_level", "") == "team") & (trad["TEAM_ID"] == team_id)] \
                    if not trad.empty and "_level" in trad.columns else pd.DataFrame()

        if not trad_team.empty:
            # V3: team stats split en Starters+Bench → sumar ambas filas
            pts_list.append(trad_team["PTS"].sum())

        # PLUS_MINUS desde gamelog (V3 no lo provee en team stats)
        gl_row = gamelog_df[
            (gamelog_df["GAME_ID"] == gid) & (gamelog_df["TEAM_ID"] == team_id)
        ]
        if not gl_row.empty and "PLUS_MINUS" in gl_row.columns:
            diff_list.append(gl_row["PLUS_MINUS"].values[0])

        # Summary — LineScore y OtherStats
        summary = read_csv_safe(season_dir / f"box_summary_{gid}.csv")
        if not summary.empty and "_table" in summary.columns:
            line = summary[(summary["_table"] == "LineScore") & (summary["TEAM_ID"] == team_id)]
            other = summary[(summary["_table"] == "OtherStats") & (summary["TEAM_ID"] == team_id)]

            if not other.empty:
                largest_lead_list.append(other["LARGEST_LEAD"].values[0])
                lead_changes_list.append(other["LEAD_CHANGES"].values[0])
                times_tied_list.append(other["TIMES_TIED"].values[0])

            if not line.empty:
                # Blown lead: ventaja al final del Q3 (Q1+Q2+Q3) pero perdió el partido
                q_cols = ["PTS_QTR1", "PTS_QTR2", "PTS_QTR3", "PTS_QTR4"]
                if all(c in line.columns for c in q_cols):
                    pts_through_q3 = line[["PTS_QTR1","PTS_QTR2","PTS_QTR3"]].values[0].sum()
                    # Para opponent: necesitamos la otra fila de LineScore
                    opp_line = summary[
                        (summary["_table"] == "LineScore") &
                        (summary["TEAM_ID"] != team_id) &
                        (summary["TEAM_ID"].notna())
                    ]
                    if not opp_line.empty:
                        opp_q3 = opp_line[["PTS_QTR1","PTS_QTR2","PTS_QTR3"]].values[0].sum()
                        team_final = line["PTS"].values[0]
                        opp_final  = opp_line["PTS"].values[0]
                        # Tenía ventaja al Q3 pero perdió el partido
                        if pts_through_q3 > opp_q3 and team_final < opp_final:
                            blown_leads += 1

                # Overtime: PTS_OT1 > 0
                if "PTS_OT1" in line.columns and line["PTS_OT1"].values[0] > 0:
                    ot_games += 1

        # WL para este partido
        wl_row = gamelog_df[
            (gamelog_df["GAME_ID"].astype(str) == gid) &
            (gamelog_df["TEAM_ID"] == team_id)
        ]
        if not wl_row.empty:
            wl_list.append(1 if wl_row["WL"].values[0] == "W" else 0)

    n = len(g4plus_ids)
    return {
        "pts_per_game_g4plus":   round(np.mean(pts_list), 2) if pts_list else None,
        "point_diff_g4plus":     round(np.mean(diff_list), 2) if diff_list else None,
        "win_pct_g4plus":        round(np.mean(wl_list), 4) if wl_list else None,
        "largest_lead_g4plus":   round(np.mean(largest_lead_list), 2) if largest_lead_list else None,
        "lead_changes_g4plus":   round(np.mean(lead_changes_list), 2) if lead_changes_list else None,
        "times_tied_g4plus":     round(np.mean(times_tied_list), 2) if times_tied_list else None,
        "blown_lead_g4plus":     blown_leads,
        "ot_games_g4plus":       ot_games,
        "n_g4plus_games":        n,
    }


# ---------------------------------------------------------------------------
# BLOQUE 3: Métricas avanzadas (playoffs pre-Finals)
# ---------------------------------------------------------------------------
def compute_advanced(season_dir: Path, series_df: pd.DataFrame,
                     gamelog_df: pd.DataFrame, team_id: int,
                     winner_id: int, loser_id: int) -> dict:
    """
    Agrega BoxScoreAdvancedV2 (TeamStats) para todos los juegos pre-Finals.
    Retorna promedios de OFF/DEF/NET rating, TS%, PIE, etc.
    """
    finals_game_ids = set(
        series_df[series_df["SERIES_ID"].str[7] == "4"]["GAME_ID"].astype(str)
    )
    team_pre = gamelog_df[
        (gamelog_df["TEAM_ID"] == team_id) &
        (~gamelog_df["GAME_ID"].astype(str).isin(finals_game_ids))
    ]
    game_ids = team_pre["GAME_ID"].astype(str).tolist()

    rows = []
    for gid in game_ids:
        adv = read_csv_safe(season_dir / f"box_advanced_{gid}.csv")
        if adv.empty or "_level" not in adv.columns:
            continue
        team_row = adv[(adv["_level"] == "team") & (adv["TEAM_ID"] == team_id)]
        if not team_row.empty:
            rows.append(team_row.iloc[0])

    if not rows:
        return {}

    adv_df = pd.DataFrame(rows)

    def safe_mean(col):
        if col in adv_df.columns:
            return round(adv_df[col].mean(), 4)
        return None

    return {
        "playoff_off_rating":  safe_mean("OFF_RATING"),
        "playoff_def_rating":  safe_mean("DEF_RATING"),
        "playoff_net_rating":  safe_mean("NET_RATING"),
        "playoff_ts_pct":      safe_mean("TS_PCT"),
        "playoff_efg_pct":     safe_mean("EFG_PCT"),
        "playoff_tov_pct":     safe_mean("TM_TOV_PCT"),
        "playoff_oreb_pct":    safe_mean("OREB_PCT"),
        "playoff_pace":        safe_mean("PACE"),
        "playoff_pie":         safe_mean("PIE"),
    }


# ---------------------------------------------------------------------------
# BLOQUE 4: Star Player con rezago temporal y doble fuente
# ---------------------------------------------------------------------------
LAMBDA_DECAY = 0.25   # decaimiento exponencial: último partido peso=1.0, penúltimo=0.78...
DIVERGENCE_THRESHOLD = 0.30  # diferencia >30% en PPG → warning de diseño


def _weighted_stats(game_records: list, star_id, adv_records: list) -> dict:
    """
    Calcula PPG, TS% y USG% ponderados por rezago para un jugador dado.
    game_records: list de (weight, player_df_row)
    adv_records:  list de (weight, adv_df_row)
    """
    pts_w, ts_w, usg_w, total_w = 0.0, 0.0, 0.0, 0.0
    ts_total_w, usg_total_w = 0.0, 0.0

    for weight, row in game_records:
        if row["PLAYER_ID"] != star_id:
            continue
        pts = row.get("PTS") or 0
        pts_w    += weight * pts
        total_w  += weight

    for weight, row in adv_records:
        if row["PLAYER_ID"] != star_id:
            continue
        ts  = row.get("TS_PCT")
        usg = row.get("USG_PCT")
        if ts is not None and not np.isnan(ts):
            ts_w      += weight * ts
            ts_total_w += weight
        if usg is not None and not np.isnan(usg):
            usg_w      += weight * usg
            usg_total_w += weight

    return {
        "ppg_w":  round(pts_w  / total_w,    2) if total_w    > 0 else None,
        "ts_w":   round(ts_w   / ts_total_w, 4) if ts_total_w > 0 else None,
        "usg_w":  round(usg_w  / usg_total_w,4) if usg_total_w> 0 else None,
    }


def compute_star_features(season_dir: Path, series_df: pd.DataFrame,
                           gamelog_df: pd.DataFrame, team_id: int,
                           winner_id: int, loser_id: int,
                           season: str = "") -> dict:
    """
    Star player con rezago temporal y doble fuente:
      - Fuente 1: top scorer ponderado por rezago en TODOS los juegos pre-Finals
      - Fuente 2: top scorer en Conf. Finals (ronda 3) — proxy del MVP de Conf.
    Si coinciden → señal robusta, peso 1.0.
    Si divergen  → combinación 70/30 + warning de posible error de diseño.
    """
    finals_game_ids   = set(series_df[series_df["SERIES_ID"].str[7] == "4"]["GAME_ID"])
    cf_game_ids_set   = set(series_df[series_df["SERIES_ID"].str[7] == "3"]["GAME_ID"])

    # Partidos pre-Finals ordenados cronológicamente
    team_pre = gamelog_df[
        (gamelog_df["TEAM_ID"] == team_id) &
        (~gamelog_df["GAME_ID"].isin(finals_game_ids))
    ].sort_values("GAME_DATE").reset_index(drop=True)

    if team_pre.empty:
        return {}

    game_ids = team_pre["GAME_ID"].tolist()
    n        = len(game_ids)

    # -----------------------------------------------------------------------
    # Cargar box scores y asignar pesos de rezago
    # w_i = exp(-λ * (n-1-i))  → partido más reciente (i=n-1) tiene peso 1.0
    # -----------------------------------------------------------------------
    all_trad_records = []   # list de (weight, row_dict)
    all_adv_records  = []

    for i, gid in enumerate(game_ids):
        weight = np.exp(-LAMBDA_DECAY * (n - 1 - i))
        gid_str = str(gid)

        trad = read_csv_safe(season_dir / f"box_traditional_{gid_str}.csv")
        if not trad.empty and "_level" in trad.columns:
            players = trad[(trad["_level"] == "player") & (trad["TEAM_ID"] == team_id)]
            for _, row in players.iterrows():
                all_trad_records.append((weight, row))

        adv = read_csv_safe(season_dir / f"box_advanced_{gid_str}.csv")
        if not adv.empty and "_level" in adv.columns:
            adv_players = adv[(adv["_level"] == "player") & (adv["TEAM_ID"] == team_id)]
            for _, row in adv_players.iterrows():
                all_adv_records.append((weight, row))

    if not all_trad_records:
        return {}

    # -----------------------------------------------------------------------
    # FUENTE 1: Top scorer por PPG ponderado — todos los juegos pre-Finals
    # -----------------------------------------------------------------------
    player_pts_w   = {}
    player_total_w = {}
    for weight, row in all_trad_records:
        pid = row["PLAYER_ID"]
        pts = row.get("PTS") or 0
        player_pts_w[pid]   = player_pts_w.get(pid, 0.0)   + weight * pts
        player_total_w[pid] = player_total_w.get(pid, 0.0) + weight

    player_wppg = {pid: player_pts_w[pid] / player_total_w[pid]
                   for pid in player_pts_w if player_total_w[pid] > 0}

    if not player_wppg:
        return {}

    overall_star_id   = max(player_wppg, key=player_wppg.get)
    overall_star_wppg = player_wppg[overall_star_id]

    # -----------------------------------------------------------------------
    # FUENTE 2: Top scorer en Conf. Finals (ronda 3) — proxy MVP de Conf.
    # -----------------------------------------------------------------------
    cf_pts   = {}
    cf_count = {}
    for weight, row in all_trad_records:
        gid_raw = row.get("GAME_ID") or row.get("gameId") or ""
        gid_str = str(gid_raw).zfill(10)
        if gid_str not in cf_game_ids_set:
            continue
        pid = row["PLAYER_ID"]
        pts = row.get("PTS") or 0
        cf_pts[pid]   = cf_pts.get(pid, 0.0)   + pts       # PPG simple en CF
        cf_count[pid] = cf_count.get(pid, 0.0)  + 1

    cf_wppg = {pid: cf_pts[pid] / cf_count[pid]
               for pid in cf_pts if cf_count[pid] > 0}

    cf_star_id   = max(cf_wppg, key=cf_wppg.get) if cf_wppg else overall_star_id
    cf_star_ppg  = round(cf_wppg.get(cf_star_id, overall_star_wppg), 2)

    # -----------------------------------------------------------------------
    # Chequeo de divergencia
    # -----------------------------------------------------------------------
    is_divergent = (overall_star_id != cf_star_id)
    if is_divergent:
        ppg_diff = abs(overall_star_wppg - cf_wppg.get(cf_star_id, 0))
        ppg_ref  = max(overall_star_wppg, 1e-6)
        if ppg_diff / ppg_ref > DIVERGENCE_THRESHOLD:
            print(f"  ⚠️  DIVERGENCIA FUERTE [{season}] team={team_id}: "
                  f"overall_star={overall_star_id} (wPPG={overall_star_wppg:.1f}) "
                  f"vs CF_star={cf_star_id} (PPG={cf_star_ppg:.1f}). "
                  f"Revisar posible error de diseño.")

    # -----------------------------------------------------------------------
    # Elegir star final y calcular métricas ponderadas
    # -----------------------------------------------------------------------
    if not is_divergent:
        # Señal alineada → usar el star con todos los juegos ponderados
        star_id = overall_star_id
        stats   = _weighted_stats(all_trad_records, star_id, all_adv_records)
        star_ppg_w  = stats["ppg_w"]
        star_ts_w   = stats["ts_w"]
        star_usg_w  = stats["usg_w"]
    else:
        # Divergencia → promedio ponderado 70% CF star + 30% overall star
        s_cf  = _weighted_stats(all_trad_records, cf_star_id,    all_adv_records)
        s_all = _weighted_stats(all_trad_records, overall_star_id, all_adv_records)
        star_id    = cf_star_id   # el CF star es el "principal"

        def blend(a, b, w=0.7):
            if a is not None and b is not None:
                return round(w * a + (1 - w) * b, 4)
            return a if a is not None else b

        star_ppg_w  = blend(s_cf["ppg_w"],  s_all["ppg_w"])
        star_ts_w   = blend(s_cf["ts_w"],   s_all["ts_w"])
        star_usg_w  = blend(s_cf["usg_w"],  s_all["usg_w"])

    # -----------------------------------------------------------------------
    # Momentum: PPG ponderado últimos 3 partidos vs primeros 3
    # -----------------------------------------------------------------------
    star_pts_by_game = []
    for i, gid in enumerate(game_ids):
        gid_str = str(gid)
        for weight, row in all_trad_records:
            row_gid = str(row.get("GAME_ID") or "").zfill(10)
            if row["PLAYER_ID"] == star_id and row_gid == gid_str.zfill(10):
                star_pts_by_game.append(row.get("PTS") or 0)
                break

    if len(star_pts_by_game) >= 6:
        momentum = round(
            np.mean(star_pts_by_game[-3:]) - np.mean(star_pts_by_game[:3]), 2
        )
    else:
        momentum = None

    return {
        "star_ppg_weighted":    star_ppg_w,       # PPG con rezago exponencial
        "star_ts_weighted":     star_ts_w,         # TS% con rezago
        "star_usg_weighted":    star_usg_w,        # USG% con rezago
        "star_momentum":        momentum,          # últimos 3 vs primeros 3
        "star_ppg_cf":          cf_star_ppg,       # PPG simple en Conf. Finals
        "star_is_divergent":    int(is_divergent), # 1 si las dos fuentes difieren
        # Compatibilidad hacia atrás
        "star_ppg_pre_finals":  round(overall_star_wppg, 2),
        "star_ppg_trend":       momentum,
    }


# ---------------------------------------------------------------------------
# BLOQUE 5: Calidad temporada regular
# ---------------------------------------------------------------------------
def compute_reg_season(season_dir: Path, team_id: int) -> dict:
    """
    Lee LeagueStandings y TeamEstimatedMetrics para el equipo.
    """
    standings = read_csv_safe(season_dir / "standings.csv")
    metrics   = read_csv_safe(season_dir / "estimated_metrics.csv")

    result = {}

    if not standings.empty:
        row = standings[standings["TeamID"] == team_id]
        if not row.empty:
            result.update({
                "reg_win_pct":    round(row["WinPCT"].values[0], 4),
                "playoff_seed":   int(row["PlayoffRank"].values[0]),
                "reg_pts_pg":     round(row["PointsPG"].values[0], 2),
                "reg_opp_pts_pg": round(row["OppPointsPG"].values[0], 2),
                "reg_diff_pg":    round(row["DiffPointsPG"].values[0], 2),
            })

    if not metrics.empty:
        row = metrics[metrics["TEAM_ID"] == team_id]
        if not row.empty:
            result.update({
                "reg_net_rating": round(row["E_NET_RATING"].values[0], 4),
                "reg_off_rating": round(row["E_OFF_RATING"].values[0], 4),
                "reg_def_rating": round(row["E_DEF_RATING"].values[0], 4),
                "reg_pace":       round(row["E_PACE"].values[0], 4),
            })

    return result


# ---------------------------------------------------------------------------
# BLOQUE 6: Clutch
# ---------------------------------------------------------------------------
def compute_clutch(season_dir: Path, role: str) -> dict:
    """Lee clutch stats pre-Finals para winner o loser."""
    clutch = read_csv_safe(season_dir / f"clutch_playoffs_{role}.csv")
    if clutch.empty:
        return {}

    row = clutch.iloc[0] if len(clutch) == 1 else clutch.iloc[0]
    return {
        "clutch_win_pct":  round(row.get("W_PCT", None), 4) if row.get("W_PCT") is not None else None,
        "clutch_pm":       round(row.get("PLUS_MINUS", None), 2) if row.get("PLUS_MINUS") is not None else None,
        "clutch_fg_pct":   round(row.get("FG_PCT", None), 4) if row.get("FG_PCT") is not None else None,
        "clutch_tov":      row.get("TOV", None),
    }


# ---------------------------------------------------------------------------
# BLOQUE 7: Historia / Dynasty
# ---------------------------------------------------------------------------
def compute_dynasty(season: str, team_id: int) -> dict:
    """Computa features históricas desde FINALS_HISTORY (no requiere API)."""
    current_idx = SEASONS.index(season)
    last5_seasons = SEASONS[max(0, current_idx - 5): current_idx]

    appearances = 0
    championships = 0
    consecutive = 0

    for prev in reversed(last5_seasons):
        info = FINALS_HISTORY[prev]
        in_finals = team_id in (info["winner_id"], info["loser_id"])
        if in_finals:
            appearances += 1
            if info["winner_id"] == team_id:
                championships += 1
            if consecutive == len(last5_seasons) - SEASONS.index(prev) - 1:
                consecutive += 1
        else:
            break  # racha rota → stop

    return {
        "finals_appearances_last5": appearances,
        "championships_last5":      championships,
        "consecutive_finals":       consecutive,
    }


# ---------------------------------------------------------------------------
# ENSAMBLADO DE FEATURES POR EQUIPO-AÑO
# ---------------------------------------------------------------------------
def build_team_features(season: str, team_id: int, role: str) -> dict:
    """
    Construye el vector completo de features para un equipo en una temporada.
    role: 'winner' | 'loser'
    """
    season_dir    = get_season_dir(season)
    winner_id, loser_id = get_finalist_ids(season)
    info          = FINALS_HISTORY[season]
    flags         = get_season_flags(season)

    gamelog_path  = season_dir / "gamelog_playoffs.csv"
    series_path   = season_dir / "series_structure.csv"

    if not gamelog_path.exists() or not series_path.exists():
        print(f"  ⚠️  [{season}/{role}] Faltan archivos base — skip")
        return {}

    gamelog_df = pd.read_csv(gamelog_path, parse_dates=["GAME_DATE"])
    gamelog_df["GAME_ID"] = gamelog_df["GAME_ID"].astype(str).str.zfill(10)
    series_df  = pd.read_csv(series_path, dtype={"SERIES_ID": str, "GAME_ID": str})

    # Identificadores
    base = {
        "season":         season,
        "team_id":        team_id,
        "team_abbr":      TEAM_ABBR.get(team_id, str(team_id)),
        "conference":     info["winner_conf"] if role == "winner" else
                          ("W" if info["winner_conf"] == "E" else "E"),
        "won_finals":     1 if role == "winner" else 0,
        "is_shortened":   int(flags["is_shortened"]),
        "is_bubble":      int(flags["is_bubble"]),
        "season_era":     flags["season_era"],
    }

    # Awards
    awards = {
        "has_reg_season_mvp": has_reg_season_mvp(season, team_id),
    }

    # Bloques de features
    momentum = compute_momentum(gamelog_df, series_df, team_id, winner_id, loser_id)
    g4plus   = compute_g4plus(season_dir, series_df, gamelog_df, team_id, winner_id, loser_id)
    advanced = compute_advanced(season_dir, series_df, gamelog_df, team_id, winner_id, loser_id)
    star     = compute_star_features(season_dir, series_df, gamelog_df, team_id, winner_id, loser_id, season=season)
    reg      = compute_reg_season(season_dir, team_id)
    clutch   = compute_clutch(season_dir, role)
    dynasty  = compute_dynasty(season, team_id)

    return {**base, **awards, **momentum, **g4plus, **advanced, **star, **reg, **clutch, **dynasty}


# ---------------------------------------------------------------------------
# DATASET DIFERENCIAL (1 fila por Finals)
# ---------------------------------------------------------------------------
def build_diff_dataset(team_df: pd.DataFrame) -> pd.DataFrame:
    """
    Transforma el dataset de 2 filas/año → 1 fila/año con features diferenciales.
    winner_value - loser_value para cada feature numérica.
    target: won_finals siempre = 1 para winner (trivial) →
            se redefine como winner_conf = "W" (1) o "E" (0) para predecir qué conferencia gana.

    Nota: en el modelo real el target puede ser cualquier definición binaria consistente.
    """
    numeric_cols = team_df.select_dtypes(include=[np.number]).columns.tolist()
    exclude = ["won_finals", "team_id", "is_shortened", "is_bubble"]
    diff_cols = [c for c in numeric_cols if c not in exclude]

    rows = []
    for season in SEASONS:
        winner = team_df[(team_df["season"] == season) & (team_df["won_finals"] == 1)]
        loser  = team_df[(team_df["season"] == season) & (team_df["won_finals"] == 0)]

        if winner.empty or loser.empty:
            continue

        w = winner.iloc[0]
        l = loser.iloc[0]

        row = {
            "season":           season,
            "winner":           w["team_abbr"],
            "loser":            l["team_abbr"],
            "winner_conf":      w["conference"],
            "is_shortened":     w["is_shortened"],
            "is_bubble":        w["is_bubble"],
            "season_era":       w["season_era"],
        }

        for col in diff_cols:
            w_val = w.get(col)
            l_val = l.get(col)
            if w_val is not None and l_val is not None:
                try:
                    row[f"diff_{col}"] = round(float(w_val) - float(l_val), 4)
                except (TypeError, ValueError):
                    row[f"diff_{col}"] = None

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Construye features desde datos crudos")
    parser.add_argument("--season", type=str, default=None)
    args = parser.parse_args()

    target_seasons = [args.season] if args.season else SEASONS

    all_rows = []
    for season in target_seasons:
        season_dir = get_season_dir(season)
        if not (season_dir / "_DONE").exists():
            print(f"[{season}] ⚠️  Extracción no completada — skip")
            continue

        print(f"\n[{season}] Construyendo features...")
        winner_id, loser_id = get_finalist_ids(season)

        for team_id, role in [(winner_id, "winner"), (loser_id, "loser")]:
            abbr = TEAM_ABBR.get(team_id, str(team_id))
            print(f"  {abbr} ({role})...")
            row = build_team_features(season, team_id, role)
            if row:
                all_rows.append(row)

    if not all_rows:
        print("\n❌ No se construyeron features. ¿Está completa la extracción?")
        return

    # Dataset principal (2 filas por año)
    team_df = pd.DataFrame(all_rows)
    out_main = FEATURES_DIR / "finals_dataset.csv"
    team_df.to_csv(out_main, index=False)
    print(f"\n✅ finals_dataset.csv → {len(team_df)} filas × {len(team_df.columns)} columnas")
    print(f"   {out_main.resolve()}")

    # Dataset diferencial (1 fila por año)
    diff_df = build_diff_dataset(team_df)
    out_diff = FEATURES_DIR / "finals_dataset_diff.csv"
    diff_df.to_csv(out_diff, index=False)
    print(f"✅ finals_dataset_diff.csv → {len(diff_df)} filas × {len(diff_df.columns)} columnas")
    print(f"   {out_diff.resolve()}")

    # Resumen de NAs
    na_pct = (team_df.isna().mean() * 100).round(1)
    problem_cols = na_pct[na_pct > 20]
    if not problem_cols.empty:
        print(f"\n⚠️  Columnas con >20% NAs:")
        for col, pct in problem_cols.items():
            print(f"   {col}: {pct}%")


if __name__ == "__main__":
    main()
