"""
finals_config.py
----------------
Datos hardcodeados que no están disponibles directamente en nba_api:
  - Historia de Finals (2003-04 a 2023-24): equipos, team_ids, ganador
  - Regular Season MVP por temporada
  - Flags de temporadas anómalas (bubble, lockout)
  - Metadatos de temporada (era)

Estos 20 registros son la fuente de verdad del proyecto.
"""

# ---------------------------------------------------------------------------
# FINALS HISTORY
# Formato: season → {winner, loser, winner_conf, winner_id, loser_id}
# winner_conf: "E" = East, "W" = West
# ---------------------------------------------------------------------------
FINALS_HISTORY = {
    "2003-04": {"winner": "DET", "loser": "LAL", "winner_conf": "E",
                "winner_id": 1610612765, "loser_id": 1610612747},
    "2004-05": {"winner": "SAS", "loser": "DET", "winner_conf": "W",
                "winner_id": 1610612759, "loser_id": 1610612765},
    "2005-06": {"winner": "MIA", "loser": "DAL", "winner_conf": "E",
                "winner_id": 1610612748, "loser_id": 1610612742},
    "2006-07": {"winner": "SAS", "loser": "CLE", "winner_conf": "W",
                "winner_id": 1610612759, "loser_id": 1610612739},
    "2007-08": {"winner": "BOS", "loser": "LAL", "winner_conf": "E",
                "winner_id": 1610612738, "loser_id": 1610612747},
    "2008-09": {"winner": "LAL", "loser": "ORL", "winner_conf": "W",
                "winner_id": 1610612747, "loser_id": 1610612753},
    "2009-10": {"winner": "LAL", "loser": "BOS", "winner_conf": "W",
                "winner_id": 1610612747, "loser_id": 1610612738},
    "2010-11": {"winner": "DAL", "loser": "MIA", "winner_conf": "W",
                "winner_id": 1610612742, "loser_id": 1610612748},
    "2011-12": {"winner": "MIA", "loser": "OKC", "winner_conf": "E",
                "winner_id": 1610612748, "loser_id": 1610612760},
    "2012-13": {"winner": "MIA", "loser": "SAS", "winner_conf": "E",
                "winner_id": 1610612748, "loser_id": 1610612759},
    "2013-14": {"winner": "SAS", "loser": "MIA", "winner_conf": "W",
                "winner_id": 1610612759, "loser_id": 1610612748},
    "2014-15": {"winner": "GSW", "loser": "CLE", "winner_conf": "W",
                "winner_id": 1610612744, "loser_id": 1610612739},
    "2015-16": {"winner": "CLE", "loser": "GSW", "winner_conf": "E",
                "winner_id": 1610612739, "loser_id": 1610612744},
    "2016-17": {"winner": "GSW", "loser": "CLE", "winner_conf": "W",
                "winner_id": 1610612744, "loser_id": 1610612739},
    "2017-18": {"winner": "GSW", "loser": "CLE", "winner_conf": "W",
                "winner_id": 1610612744, "loser_id": 1610612739},
    "2018-19": {"winner": "TOR", "loser": "GSW", "winner_conf": "E",
                "winner_id": 1610612761, "loser_id": 1610612744},
    "2019-20": {"winner": "LAL", "loser": "MIA", "winner_conf": "W",
                "winner_id": 1610612747, "loser_id": 1610612748},
    "2020-21": {"winner": "MIL", "loser": "PHX", "winner_conf": "E",
                "winner_id": 1610612749, "loser_id": 1610612756},
    "2021-22": {"winner": "GSW", "loser": "BOS", "winner_conf": "W",
                "winner_id": 1610612744, "loser_id": 1610612738},
    "2022-23": {"winner": "DEN", "loser": "MIA", "winner_conf": "W",
                "winner_id": 1610612743, "loser_id": 1610612748},
    "2023-24": {"winner": "BOS", "loser": "DAL", "winner_conf": "E",
                "winner_id": 1610612738, "loser_id": 1610612742},
}

# ---------------------------------------------------------------------------
# REGULAR SEASON MVP
# Formato: season → {player_name, team_id, team_abbr}
# Clave para feature has_reg_season_mvp: ¿está el MVP en alguno de los finalistas?
# ---------------------------------------------------------------------------
REG_SEASON_MVP = {
    # Season  Player              Team    team_id         On finalist?
    "2003-04": {"player": "Kevin Garnett",    "team": "MIN", "team_id": 1610612750},  # ❌
    "2004-05": {"player": "Steve Nash",       "team": "PHX", "team_id": 1610612756},  # ❌
    "2005-06": {"player": "Steve Nash",       "team": "PHX", "team_id": 1610612756},  # ❌
    "2006-07": {"player": "Dirk Nowitzki",    "team": "DAL", "team_id": 1610612742},  # ❌
    "2007-08": {"player": "Kobe Bryant",      "team": "LAL", "team_id": 1610612747},  # ✅ LAL finalist (lost)
    "2008-09": {"player": "LeBron James",     "team": "CLE", "team_id": 1610612739},  # ❌
    "2009-10": {"player": "LeBron James",     "team": "CLE", "team_id": 1610612739},  # ❌
    "2010-11": {"player": "Derrick Rose",     "team": "CHI", "team_id": 1610612741},  # ❌
    "2011-12": {"player": "LeBron James",     "team": "MIA", "team_id": 1610612748},  # ✅ MIA finalist (won)
    "2012-13": {"player": "LeBron James",     "team": "MIA", "team_id": 1610612748},  # ✅ MIA finalist (won)
    "2013-14": {"player": "Kevin Durant",     "team": "OKC", "team_id": 1610612760},  # ❌
    "2014-15": {"player": "Stephen Curry",    "team": "GSW", "team_id": 1610612744},  # ✅ GSW finalist (won)
    "2015-16": {"player": "Stephen Curry",    "team": "GSW", "team_id": 1610612744},  # ✅ GSW finalist (lost)
    "2016-17": {"player": "Russell Westbrook","team": "OKC", "team_id": 1610612760},  # ❌
    "2017-18": {"player": "James Harden",     "team": "HOU", "team_id": 1610612745},  # ❌
    "2018-19": {"player": "Giannis",          "team": "MIL", "team_id": 1610612749},  # ❌
    "2019-20": {"player": "Giannis",          "team": "MIL", "team_id": 1610612749},  # ❌
    "2020-21": {"player": "Nikola Jokic",     "team": "DEN", "team_id": 1610612743},  # ❌
    "2021-22": {"player": "Nikola Jokic",     "team": "DEN", "team_id": 1610612743},  # ❌
    "2022-23": {"player": "Nikola Jokic",     "team": "DEN", "team_id": 1610612743},  # ✅ DEN finalist (won)
    "2023-24": {"player": "Nikola Jokic",     "team": "DEN", "team_id": 1610612743},  # ❌
}

# ---------------------------------------------------------------------------
# DYNASTY / HISTORY FEATURES
# Computado una sola vez; no requiere API
# ---------------------------------------------------------------------------
# Apariciones en Finals en las 5 temporadas previas (por team_id)
# Se computa en build_features.py a partir de FINALS_HISTORY — no hardcodeado aquí

# ---------------------------------------------------------------------------
# FLAGS DE TEMPORADA ANÓMALA
# Riesgos 5 y 6 del pre-mortem
# ---------------------------------------------------------------------------
SEASON_FLAGS = {
    "2011-12": {"is_shortened": True,  "is_bubble": False, "season_era": "post2010"},
    "2019-20": {"is_shortened": False, "is_bubble": True,  "season_era": "modern"},
}

def get_season_flags(season: str) -> dict:
    """Retorna flags para una temporada. Defaults a False si no tiene anomalías."""
    base = SEASON_FLAGS.get(season, {})
    year = int(season[:4])
    return {
        "is_shortened": base.get("is_shortened", False),
        "is_bubble":    base.get("is_bubble",    False),
        # Era: pre2010 (2004-2009), post2010 (2010-2014), modern (2015+)
        "season_era":   base.get("season_era",
                                 "pre2010"  if year < 2010 else
                                 "post2010" if year < 2015 else
                                 "modern"),
    }

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def get_finalist_ids(season: str) -> tuple[int, int]:
    """Retorna (winner_id, loser_id) para la temporada dada."""
    info = FINALS_HISTORY[season]
    return info["winner_id"], info["loser_id"]

def has_reg_season_mvp(season: str, team_id: int) -> int:
    """1 si el MVP de temporada regular jugó para este equipo, 0 si no."""
    mvp = REG_SEASON_MVP.get(season)
    if mvp is None:
        return 0
    return int(mvp["team_id"] == team_id)

SEASONS = list(FINALS_HISTORY.keys())  # ["2003-04", ..., "2023-24"]

# ---------------------------------------------------------------------------
# TEAM ID → ABBREVIATION MAP (para logs legibles)
# ---------------------------------------------------------------------------
TEAM_ABBR = {
    1610612738: "BOS", 1610612739: "CLE", 1610612741: "CHI",
    1610612742: "DAL", 1610612743: "DEN", 1610612744: "GSW",
    1610612745: "HOU", 1610612747: "LAL", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612752: "NYK",
    1610612753: "ORL", 1610612756: "PHX", 1610612759: "SAS",
    1610612760: "OKC", 1610612761: "TOR", 1610612765: "DET",
}
