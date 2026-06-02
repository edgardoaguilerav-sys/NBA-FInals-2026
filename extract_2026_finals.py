"""
extract_2026_finals.py
----------------------
Extrae features reales de Spurs y Knicks para las Finals 2026.
Corre desde Desktop/NBA/ con el mismo Python de Reticulate.

Salida: data/features/finals_2026_features.csv
"""

import time
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")

from nba_api.stats.endpoints import (
    CommonPlayoffSeries,
    LeagueGameLog,
    BoxScoreAdvancedV3,
    LeagueDashTeamClutch,
)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SEASON        = "2025-26"
SAS_ID        = 1610612759   # San Antonio Spurs
NYK_ID        = 1610612752   # New York Knicks
SLEEP         = 0.8
TIMEOUT       = 60
OUT_DIR       = Path("data/features")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def call(fn, *args, **kwargs):
    time.sleep(SLEEP)
    return fn(*args, **kwargs, timeout=TIMEOUT)

# ---------------------------------------------------------------------------
# 1. Obtener game IDs pre-Finals para cada equipo
# ---------------------------------------------------------------------------
print(f"Extrayendo datos {SEASON} — Spurs vs Knicks\n")

print("→ CommonPlayoffSeries")
series_ep  = call(CommonPlayoffSeries, season=SEASON, league_id="00")
series_df  = series_ep.get_data_frames()[0]
series_df["SERIES_ID"] = series_df["SERIES_ID"].astype(str)
series_df["GAME_ID"]   = series_df["GAME_ID"].astype(str)

# Ronda 4 = Finals
finals_ids = set(series_df[series_df["SERIES_ID"].str[7] == "4"]["GAME_ID"])
print(f"   {len(finals_ids)} partidos de Finals identificados")

print("→ LeagueGameLog (Playoffs)")
gl_ep     = call(LeagueGameLog, season=SEASON, season_type_all_star="Playoffs",
                 league_id="00", player_or_team_abbreviation="T")
gamelog   = gl_ep.get_data_frames()[0]
gamelog["GAME_ID"]   = gamelog["GAME_ID"].astype(str).str.zfill(10)
gamelog["GAME_DATE"] = pd.to_datetime(gamelog["GAME_DATE"])

def get_prefinals_games(team_id):
    mask = (gamelog["TEAM_ID"] == team_id) & (~gamelog["GAME_ID"].isin(finals_ids))
    return gamelog[mask].sort_values("GAME_DATE")

sas_games = get_prefinals_games(SAS_ID)
nyk_games = get_prefinals_games(NYK_ID)
print(f"   SAS pre-Finals: {len(sas_games)} partidos")
print(f"   NYK pre-Finals: {len(nyk_games)} partidos\n")

# ---------------------------------------------------------------------------
# 2. playoff_tov_pct — desde BoxScoreAdvancedV3 (team level)
# ---------------------------------------------------------------------------
def get_tov_pct(game_ids, team_id, label):
    rows = []
    total = len(game_ids)
    for i, gid in enumerate(game_ids, 1):
        print(f"  [{i:02d}/{total}] {label} advanced game_id={gid}", end="\r")
        try:
            ep     = call(BoxScoreAdvancedV3, game_id=gid)
            frames = ep.get_data_frames()
            team   = frames[1].copy()   # TeamStats (frame 1 en V3)
            team_row = team[team["teamId"] == team_id]
            if not team_row.empty:
                rows.append({
                    "game_id":     gid,
                    "tov_ratio":   team_row["turnoverRatio"].values[0],
                })
        except Exception as e:
            print(f"\n   ⚠ skip {gid}: {e}")
    print()
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    return round(df["tov_ratio"].mean(), 4)

print("→ BoxScoreAdvancedV3 — SAS")
sas_tov_pct = get_tov_pct(sas_games["GAME_ID"].tolist(), SAS_ID, "SAS")
print(f"   SAS playoff_tov_pct = {sas_tov_pct}")

print("→ BoxScoreAdvancedV3 — NYK")
nyk_tov_pct = get_tov_pct(nyk_games["GAME_ID"].tolist(), NYK_ID, "NYK")
print(f"   NYK playoff_tov_pct = {nyk_tov_pct}\n")

# ---------------------------------------------------------------------------
# 3. clutch_tov — desde LeagueDashTeamClutch
# ---------------------------------------------------------------------------
def get_clutch_tov(team_id, game_df, label):
    if game_df.empty:
        return None
    date_from = game_df["GAME_DATE"].min().strftime("%m/%d/%Y")
    date_to   = game_df["GAME_DATE"].max().strftime("%m/%d/%Y")
    print(f"→ LeagueDashTeamClutch {label} ({date_from} → {date_to})")
    try:
        ep = call(
            LeagueDashTeamClutch,
            season=SEASON,
            season_type_all_star="Playoffs",
            clutch_time="Last 5 Minutes",
            point_diff="5",
            ahead_behind="Ahead or Behind",
            per_mode_detailed="PerGame",
            date_from_nullable=date_from,
            date_to_nullable=date_to,
            team_id_nullable=str(team_id),
            league_id_nullable="00",
        )
        df = ep.get_data_frames()[0]
        row = df[df["TEAM_ID"] == team_id]
        if row.empty:
            return None
        tov = row["TOV"].values[0]
        print(f"   {label} clutch_tov = {tov}")
        return round(float(tov), 4)
    except Exception as e:
        print(f"   ⚠ error: {e}")
        return None

sas_clutch = get_clutch_tov(SAS_ID, sas_games, "SAS")
nyk_clutch = get_clutch_tov(NYK_ID, nyk_games, "NYK")

# ---------------------------------------------------------------------------
# 4. Features adicionales directas del gamelog
# ---------------------------------------------------------------------------
def compute_gamelog_features(game_df, team_id):
    if game_df.empty:
        return {}
    wins   = (game_df["WL"] == "W").sum()
    losses = (game_df["WL"] == "L").sum()
    total  = wins + losses
    return {
        "pre_finals_wins":     int(wins),
        "pre_finals_losses":   int(losses),
        "pre_finals_win_pct":  round(wins / total, 4) if total > 0 else None,
        "games_played":        int(total),
        "avg_point_diff":      round(game_df["PLUS_MINUS"].mean(), 2)
                               if "PLUS_MINUS" in game_df.columns else None,
    }

sas_gl = compute_gamelog_features(sas_games, SAS_ID)
nyk_gl = compute_gamelog_features(nyk_games, NYK_ID)

# playoff_net_rating desde los stats ya conocidos (NBAstuffer)
# SAS: oEFF=116.5, dEFF=106.1 → net=+10.4
# NYK: oEFF=124.5, dEFF=104.4 → net=+20.1
sas_net = 10.4
nyk_net = 20.1

# ---------------------------------------------------------------------------
# 5. Guardar resultados
# ---------------------------------------------------------------------------
results = pd.DataFrame([
    {
        "team":               "SAS",
        "team_id":            SAS_ID,
        "season":             SEASON,
        "playoff_net_rating": sas_net,
        "playoff_tov_pct":    sas_tov_pct,
        "clutch_tov":         sas_clutch,
        "pre_finals_win_pct": sas_gl.get("pre_finals_win_pct"),
        "games_played":       sas_gl.get("games_played"),
        "avg_point_diff_pre": sas_gl.get("avg_point_diff"),
        "reg_diff_pg":        8.3,    # de NBAstuffer regular season
        "reg_win_pct":        0.756,
        "note":               "playoff_net_rating from NBAstuffer; clutch/tov from API"
    },
    {
        "team":               "NYK",
        "team_id":            NYK_ID,
        "season":             SEASON,
        "playoff_net_rating": nyk_net,
        "playoff_tov_pct":    nyk_tov_pct,
        "clutch_tov":         nyk_clutch,
        "pre_finals_win_pct": nyk_gl.get("pre_finals_win_pct"),
        "games_played":       nyk_gl.get("games_played"),
        "avg_point_diff_pre": nyk_gl.get("avg_point_diff"),
        "reg_diff_pg":        6.4,
        "reg_win_pct":        0.646,
        "note":               "playoff_net_rating from NBAstuffer; clutch/tov from API"
    }
])

out_path = OUT_DIR / "finals_2026_features.csv"
results.to_csv(out_path, index=False)

print("\n" + "="*55)
print("FEATURES EXTRAÍDAS — Finals 2026")
print("="*55)
print(results[["team", "playoff_net_rating", "playoff_tov_pct",
               "clutch_tov", "pre_finals_win_pct", "reg_diff_pg"]].to_string(index=False))
print(f"\nGuardado en: {out_path}")
