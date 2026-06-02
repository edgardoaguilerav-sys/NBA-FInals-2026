"""
extract_raw.py
--------------
Fase 1 de extracción: descarga y guarda datos crudos desde stats.nba.com.
Debe ejecutarse en máquina LOCAL (stats.nba.com bloquea IPs de servidores cloud).

Estructura de salida:
    data/raw/{season}/
        series_structure.csv       ← CommonPlayoffSeries
        gamelog_playoffs.csv       ← LeagueGameLog (playoffs completos)
        box_traditional_{id}.csv   ← BoxScoreTraditionalV2 por partido
        box_advanced_{id}.csv      ← BoxScoreAdvancedV2 por partido
        box_summary_{id}.csv       ← BoxScoreSummaryV2 (LineScore + OtherStats)
        standings.csv              ← LeagueStandings (reg. season)
        estimated_metrics.csv      ← TeamEstimatedMetrics (reg. season)
        clutch_playoffs.csv        ← LeagueDashTeamClutch (playoffs pre-Finals)

Uso:
    python extract_raw.py                    # todas las temporadas
    python extract_raw.py --season 2022-23   # una sola temporada
    python extract_raw.py --resume           # salta temporadas ya completadas

Estimado: ~16 min para las 21 temporadas (sleep 0.6s entre llamadas)
"""

import os
import sys
import time
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd

from nba_api.stats.endpoints import (
    CommonPlayoffSeries,
    LeagueGameLog,
    BoxScoreTraditionalV3,
    BoxScoreAdvancedV3,
    BoxScoreSummaryV3,
    LeagueStandings,
    TeamEstimatedMetrics,
    LeagueDashTeamClutch,
)

from finals_config import FINALS_HISTORY, SEASONS, get_finalist_ids, TEAM_ABBR

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DATA_DIR = Path("data/raw")
LOG_FILE = Path("data/extraction.log")
SLEEP_BETWEEN_CALLS = 0.6   # segundos entre llamadas (evita rate-limiting)
MAX_RETRIES = 4              # intentos con backoff exponencial
TIMEOUT = 60                 # segundos timeout por llamada

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
# Fix encoding para consola Windows (cp1252 no soporta emojis)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------
def api_call(fn, *args, **kwargs):
    """
    Llama a un endpoint de nba_api con reintentos y backoff exponencial.
    Retorna el resultado o lanza excepción si todos los intentos fallan.
    """
    delay = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(SLEEP_BETWEEN_CALLS)
            result = fn(*args, **kwargs, timeout=TIMEOUT)
            return result
        except Exception as e:
            log.warning(f"  Intento {attempt}/{MAX_RETRIES} falló: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                log.info(f"  Esperando {delay}s antes de reintentar...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def save_csv(df: pd.DataFrame, path: Path):
    """Guarda DataFrame como CSV, crea directorio si no existe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


# Mapeo camelCase (V3) → UPPER_SNAKE_CASE (V2) para compatibilidad con build_features.py
TRAD_V3_RENAME = {
    "gameId":              "GAME_ID",
    "teamId":              "TEAM_ID",
    "personId":            "PLAYER_ID",
    "points":              "PTS",
    "plusMinusPoints":     "PLUS_MINUS",
    "assists":             "AST",
    "steals":              "STL",
    "blocks":              "BLK",
    "turnovers":           "TO",
    "reboundsTotal":       "REB",
    "reboundsOffensive":   "OREB",
    "reboundsDefensive":   "DREB",
    "foulsPersonal":       "PF",
    "minutes":             "MIN",
    "fieldGoalsMade":      "FGM",
    "fieldGoalsAttempted": "FGA",
    "threePointersMade":   "FG3M",
    "threePointersAttempted": "FG3A",
    "freeThrowsMade":      "FTM",
    "freeThrowsAttempted": "FTA",
}

ADV_V3_RENAME = {
    "gameId":                    "GAME_ID",
    "teamId":                    "TEAM_ID",
    "personId":                  "PLAYER_ID",
    "offensiveRating":           "OFF_RATING",
    "defensiveRating":           "DEF_RATING",
    "netRating":                 "NET_RATING",
    "trueShootingPercentage":    "TS_PCT",
    "effectiveFieldGoalPercentage": "EFG_PCT",
    "turnoverRatio":             "TM_TOV_PCT",
    "offensiveReboundPercentage": "OREB_PCT",
    "pace":                      "PACE",
    "minutes":                   "MIN",
    "assistPercentage":          "AST_PCT",
    "usagePercentage":           "USG_PCT",
}


def already_done(season_dir: Path) -> bool:
    """Verifica si la temporada ya fue extraída completamente."""
    checkpoint = season_dir / "_DONE"
    return checkpoint.exists()


def mark_done(season_dir: Path):
    """Marca la temporada como completada."""
    (season_dir / "_DONE").touch()


def get_season_dir(season: str) -> Path:
    return DATA_DIR / season.replace("-", "_")


# ---------------------------------------------------------------------------
# FASE 1: Estructura de playoffs y game log
# ---------------------------------------------------------------------------
def extract_season_structure(season: str, season_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Descarga:
      - CommonPlayoffSeries → structure con GAME_ID, SERIES_ID, GAME_NUM
      - LeagueGameLog (Playoffs) → todos los partidos con fecha, WL, PTS, PLUS_MINUS

    Retorna: (series_df, gamelog_df)
    """
    series_path  = season_dir / "series_structure.csv"
    gamelog_path = season_dir / "gamelog_playoffs.csv"

    # Series structure
    _series_dtype = {"SERIES_ID": str, "GAME_ID": str}
    if series_path.exists():
        log.info(f"  [cache] series_structure.csv")
        series_df = pd.read_csv(series_path, dtype=_series_dtype)
    else:
        log.info(f"  → CommonPlayoffSeries")
        endpoint = api_call(CommonPlayoffSeries, season=season, league_id="00")
        series_df = endpoint.get_data_frames()[0]
        save_csv(series_df, series_path)
        series_df = pd.read_csv(series_path, dtype=_series_dtype)
        log.info(f"     {len(series_df)} filas guardadas")

    # Game log de playoffs completo
    if gamelog_path.exists():
        log.info(f"  [cache] gamelog_playoffs.csv")
        gamelog_df = pd.read_csv(gamelog_path, parse_dates=["GAME_DATE"])
    else:
        log.info(f"  → LeagueGameLog (Playoffs)")
        endpoint = api_call(
            LeagueGameLog,
            season=season,
            season_type_all_star="Playoffs",
            league_id="00",
            player_or_team_abbreviation="T",   # Team-level log
        )
        gamelog_df = endpoint.get_data_frames()[0]
        gamelog_df["GAME_DATE"] = pd.to_datetime(gamelog_df["GAME_DATE"])
        save_csv(gamelog_df, gamelog_path)
        log.info(f"     {len(gamelog_df)} filas guardadas")

    return series_df, gamelog_df


# ---------------------------------------------------------------------------
# FASE 2: Box scores por partido pre-Finals
# ---------------------------------------------------------------------------
def get_prefinals_game_ids(series_df: pd.DataFrame,
                            gamelog_df: pd.DataFrame,
                            winner_id: int,
                            loser_id: int) -> list[str]:
    """
    Identifica los GAME_IDs de partidos pre-Finals para ambos finalistas.

    Estrategia:
      - Finals = SERIES_ID[7] == '4'  (ronda 4 en el formato NBA)
      - Pre-Finals = partidos del finalista en rondas 1, 2, 3
    """
    # Identificar GAME_IDs de la serie de Finals
    finals_series = series_df[series_df["SERIES_ID"].str[7] == "4"]
    finals_game_ids = set(finals_series["GAME_ID"].astype(str))

    finalist_ids = {winner_id, loser_id}

    # Partidos donde jugó algún finalista, excluyendo Finals
    pre_finals = gamelog_df[
        (gamelog_df["TEAM_ID"].isin(finalist_ids)) &
        (~gamelog_df["GAME_ID"].astype(str).isin(finals_game_ids))
    ]

    game_ids = pre_finals["GAME_ID"].astype(str).unique().tolist()
    return game_ids


def extract_box_scores(game_ids: list[str], season_dir: Path):
    """
    Descarga BoxScoreTraditionalV2, BoxScoreAdvancedV2, BoxScoreSummaryV2
    para cada GAME_ID. Skippea partidos ya descargados.
    """
    total = len(game_ids)
    log.info(f"  Box scores: {total} partidos por descargar")

    for i, game_id in enumerate(game_ids, 1):
        trad_path    = season_dir / f"box_traditional_{game_id}.csv"
        adv_path     = season_dir / f"box_advanced_{game_id}.csv"
        summary_path = season_dir / f"box_summary_{game_id}.csv"

        # Skip si los 3 archivos existen
        if trad_path.exists() and adv_path.exists() and summary_path.exists():
            continue

        log.info(f"  [{i:02d}/{total}] game_id={game_id}")

        # Traditional V3: PlayerStats (índice 0) y TeamStats (índice 1)
        if not trad_path.exists():
            ep = api_call(BoxScoreTraditionalV3, game_id=game_id)
            frames = ep.get_data_frames()
            player_df = frames[0].copy()
            team_df   = frames[1].copy()
            player_df["_level"] = "player"
            team_df["_level"]   = "team"
            combined = pd.concat([player_df, team_df], ignore_index=True)
            combined.rename(columns=TRAD_V3_RENAME, inplace=True)
            save_csv(combined, trad_path)

        # Advanced V3: PlayerStats (índice 0) y TeamStats (índice 1)
        if not adv_path.exists():
            ep = api_call(BoxScoreAdvancedV3, game_id=game_id)
            frames = ep.get_data_frames()
            player_df = frames[0].copy()
            team_df   = frames[1].copy()
            player_df["_level"] = "player"
            team_df["_level"]   = "team"
            combined = pd.concat([player_df, team_df], ignore_index=True)
            combined.rename(columns=ADV_V3_RENAME, inplace=True)
            save_csv(combined, adv_path)

        # Summary: un solo intento sin retries — feature secundaria, NA aceptable
        if not summary_path.exists():
            combined = None
            for SumEp, frames_idx in [(BoxScoreSummaryV3, (4, 7)), ]:
                try:
                    time.sleep(SLEEP_BETWEEN_CALLS)
                    ep = SumEp(game_id=game_id, timeout=TIMEOUT)
                    frames = ep.get_data_frames()
                    li, oi = frames_idx
                    line_df  = frames[li].copy()
                    other_df = frames[oi].copy()
                    line_df.rename(columns={
                        "gameId": "GAME_ID", "teamId": "TEAM_ID",
                        "period1Score": "PTS_QTR1", "period2Score": "PTS_QTR2",
                        "period3Score": "PTS_QTR3", "period4Score": "PTS_QTR4",
                        "score": "PTS",
                    }, inplace=True)
                    other_df.rename(columns={
                        "gameId": "GAME_ID", "teamId": "TEAM_ID",
                        "biggestLead": "LARGEST_LEAD", "leadChanges": "LEAD_CHANGES",
                        "timesTied": "TIMES_TIED",
                    }, inplace=True)
                    line_df["_table"]  = "LineScore"
                    other_df["_table"] = "OtherStats"
                    combined = pd.concat([line_df, other_df], ignore_index=True)
                    break
                except Exception:
                    pass
            # Guardar placeholder vacío para no reintentar en futuras corridas
            if combined is not None:
                save_csv(combined, summary_path)
            else:
                save_csv(pd.DataFrame(), summary_path)

    log.info(f"  Box scores completados")


# ---------------------------------------------------------------------------
# FASE 3: Contexto de temporada regular
# ---------------------------------------------------------------------------
def extract_season_context(season: str, season_dir: Path,
                            winner_id: int, loser_id: int,
                            gamelog_df: pd.DataFrame):
    """
    Descarga:
      - LeagueStandings (regular season)
      - TeamEstimatedMetrics (regular season)
      - LeagueDashTeamClutch (playoffs, pre-Finals window por cada finalista)
    """
    # --- Standings ---
    standings_path = season_dir / "standings.csv"
    if not standings_path.exists():
        log.info(f"  → LeagueStandings")
        ep = api_call(LeagueStandings, season=season, season_type="Regular Season", league_id="00")
        df = ep.get_data_frames()[0]
        save_csv(df, standings_path)
        log.info(f"     {len(df)} equipos")

    # --- Estimated Metrics (net rating preciso) ---
    metrics_path = season_dir / "estimated_metrics.csv"
    if not metrics_path.exists():
        log.info(f"  → TeamEstimatedMetrics")
        ep = api_call(TeamEstimatedMetrics, season=season, season_type="Regular Season", league_id="00")
        df = ep.get_data_frames()[0]
        save_csv(df, metrics_path)

    # --- Clutch playoffs (pre-Finals window) ---
    # Usamos date_to_nullable = último día de Conf Finals de cada equipo
    # para excluir los juegos de Finals y no contaminar la feature
    for team_id, role in [(winner_id, "winner"), (loser_id, "loser")]:
        clutch_path = season_dir / f"clutch_playoffs_{role}.csv"
        if clutch_path.exists():
            continue

        team_games = gamelog_df[gamelog_df["TEAM_ID"] == team_id]

        # Identificar fechas de Finals usando series_structure (ronda 4 = SERIES_ID[7]=="4")
        series_df_local = pd.read_csv(season_dir / "series_structure.csv",
                                      dtype={"SERIES_ID": str, "GAME_ID": str})
        finals_game_ids = set(
            series_df_local[series_df_local["SERIES_ID"].str[7] == "4"]["GAME_ID"]
        )
        finals_games_in_log = gamelog_df[gamelog_df["GAME_ID"].astype(str).str.zfill(10).isin(finals_game_ids)]
        finals_dates = finals_games_in_log["GAME_DATE"]

        # Fechas pre-Finals del equipo
        if len(finals_dates) > 0:
            finals_start = pd.to_datetime(finals_dates).min()
            team_games = team_games.copy()
            team_games["GAME_DATE"] = pd.to_datetime(team_games["GAME_DATE"])
            pre_finals_games = team_games[team_games["GAME_DATE"] < finals_start]
        else:
            pre_finals_games = team_games  # fallback

        if pre_finals_games.empty:
            log.warning(f"  ⚠️  Sin juegos pre-Finals para team_id={team_id}")
            continue

        date_from = pre_finals_games["GAME_DATE"].min().strftime("%m/%d/%Y")
        date_to   = pre_finals_games["GAME_DATE"].max().strftime("%m/%d/%Y")

        log.info(f"  → LeagueDashTeamClutch ({role}: {date_from} → {date_to})")
        ep = api_call(
            LeagueDashTeamClutch,
            season=season,
            season_type_all_star="Playoffs",
            clutch_time="Last 5 Minutes",
            point_diff="5",
            ahead_behind="Ahead or Behind",
            per_mode_detailed="Totals",
            date_from_nullable=date_from,
            date_to_nullable=date_to,
            team_id_nullable=str(team_id),
            league_id_nullable="00",
        )
        df = ep.get_data_frames()[0]
        save_csv(df, clutch_path)


# ---------------------------------------------------------------------------
# ORQUESTADOR PRINCIPAL
# ---------------------------------------------------------------------------
def extract_season(season: str, resume: bool = True):
    """Extrae todos los datos crudos para una temporada."""
    season_dir = get_season_dir(season)
    season_dir.mkdir(parents=True, exist_ok=True)

    if resume and already_done(season_dir):
        log.info(f"[{season}] ✅ Ya completada — skip")
        return

    log.info(f"\n{'='*55}")
    log.info(f"[{season}] Iniciando extracción")
    log.info(f"{'='*55}")

    winner_id, loser_id = get_finalist_ids(season)
    w_abbr = TEAM_ABBR.get(winner_id, str(winner_id))
    l_abbr = TEAM_ABBR.get(loser_id,  str(loser_id))
    log.info(f"  Finalistas: {w_abbr} (winner) vs {l_abbr} (loser)")

    # Fase 1: Estructura
    series_df, gamelog_df = extract_season_structure(season, season_dir)

    # Fase 2: Box scores pre-Finals
    game_ids = get_prefinals_game_ids(series_df, gamelog_df, winner_id, loser_id)
    log.info(f"  Partidos pre-Finals identificados: {len(game_ids)}")
    extract_box_scores(game_ids, season_dir)

    # Fase 3: Contexto de temporada
    extract_season_context(season, season_dir, winner_id, loser_id, gamelog_df)

    # Checkpoint de completado
    mark_done(season_dir)

    # Metadata de extracción
    meta = {
        "season": season,
        "winner": w_abbr,
        "loser": l_abbr,
        "prefinals_games": len(game_ids),
        "extracted_at": datetime.now().isoformat(),
    }
    with open(season_dir / "_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    log.info(f"[{season}] ✅ Completada")


def main():
    parser = argparse.ArgumentParser(description="Extrae datos crudos NBA Finals")
    parser.add_argument("--season", type=str, default=None,
                        help="Temporada específica, ej. '2022-23'. Default: todas.")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Salta temporadas ya completadas (default: True)")
    parser.add_argument("--no-resume", dest="resume", action="store_false",
                        help="Re-extrae aunque ya exista checkpoint")
    args = parser.parse_args()

    target_seasons = [args.season] if args.season else SEASONS

    log.info(f"NBA Finals Extractor — {len(target_seasons)} temporada(s)")
    log.info(f"Resume mode: {args.resume}")
    log.info(f"Sleep entre llamadas: {SLEEP_BETWEEN_CALLS}s")

    start = time.time()
    for season in target_seasons:
        if season not in FINALS_HISTORY:
            log.error(f"Temporada '{season}' no está en FINALS_HISTORY")
            continue
        try:
            extract_season(season, resume=args.resume)
        except Exception as e:
            log.error(f"[{season}] ❌ Error fatal: {e}")
            log.error(f"  Continuando con la siguiente temporada...")

    elapsed = time.time() - start
    log.info(f"\nExtracción finalizada en {elapsed/60:.1f} min")
    log.info(f"Datos en: {DATA_DIR.resolve()}")


if __name__ == "__main__":
    main()
