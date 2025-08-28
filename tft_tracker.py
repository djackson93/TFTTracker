import requests
import sqlite3
from datetime import datetime
import pandas as pd
from riotwatcher import LolWatcher, TftWatcher, ApiError
from dotenv import load_dotenv
import os

# --- datetime setup ---
# Adapter: converts Python datetime to string for SQLite
def adapt_datetime(dt):
    return dt.isoformat(" ")

# Converter: converts SQLite string back to Python datetime
def convert_datetime(s):
    return datetime.fromisoformat(s.decode())

# Register them
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("DATETIME", convert_datetime)

# Connect to DB with detect_types
conn = sqlite3.connect("tft_matches.db", detect_types=sqlite3.PARSE_DECLTYPES)
cur = conn.cursor()

# ---- CONFIG FROM .env ----
load_dotenv()  # read .env file

api_key = os.getenv("API_KEY")
region = os.getenv("REGION")
continent = os.getenv("CONTINENT")
match_count = int(os.getenv("MATCH_COUNT"))

headers = {"X-Riot-Token": api_key}

## print(api_key)

# ---- INIT ----
watcher = LolWatcher(api_key)
tft_watcher = TftWatcher(api_key)

# List of Riot IDs (gameName, tagLine)
riot_ids = [
    ("SuperHandi", "NA1"),
    ("TyphoonCEO", "NA1"),
    ("Ronnichu", "NA1"),
    ("StrokableCactus", "NA1"),
]

# ---- GET PUUIDs & Summoner IDs ----
summoners = {}

for gameName, tagLine in riot_ids:
    summoners_url = f"https://{continent}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}"
    response = requests.get(summoners_url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        summoners[f"{gameName}#{tagLine}"] = {
            "puuid": data['puuid'],
            "summoner_name": gameName
        }
    else:
        print(f"❌ Failed to fetch {gameName}#{tagLine}: {response.status_code}")

print(summoners)

# -------------------- SETUP DATABASE ----------------------------
conn = sqlite3.connect("tft_matches.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player TEXT,
    puuid TEXT,
    match_id TEXT UNIQUE,
    placement INTEGER,
    augments TEXT,
    traits TEXT,
    start_timestamp DATETIME,
    end_timestamp DATETIME,
    match_length DECIMAL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS rank_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summoner_id TEXT,
    summoner_name TEXT,
    rank_tier TEXT,
    league_points INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ---- FETCH MATCH DATA ----
for name, info in summoners.items():
    puuid = info["puuid"]
    try:
        match_ids = tft_watcher.match.by_puuid(continent, puuid, count=match_count)

        # --- Check latest match timestamp for the player to eliminate rechecking whole set---
        cur.execute("SELECT MAX(start_timestamp) FROM matches WHERE puuid = ?", (puuid,))
        last_timestamp = cur.fetchone()[0]

        if last_timestamp:
            if isinstance(last_timestamp, str):
                last_timestamp = datetime.fromisoformat(last_timestamp)
            start_time = int(last_timestamp.timestamp())
        else:
            start_time = None  # Want to fetch all games if no previous game history has been recorded

        params = {}
        if start_time:
            params["start"] = start_time

        # --- Step 1: Get only NEW matches ---
        match_ids = tft_watcher.match.by_puuid(continent, puuid, **params)

        new_matches_count = 0  # counter for inserted rows

        # --- Step 2: Process each of the matches ---
        for match_id in match_ids:
            match = tft_watcher.match.by_id(continent, match_id)
            info_match = match['info']

            # Pull timestamps once per match
            start_time = info_match.get("game_datetime")  # in ms since epoch
            end_time = start_time + info_match.get("game_length", 0) * 1000  # add length (seconds → ms)
            match_length = info_match.get("game_length", 0)  # already seconds

            for p in info_match['participants']:
                if p['puuid'] == puuid:
                    record = {
                        "player": name,
                        "puuid": puuid,
                        "match_id": match_id,
                        "placement": p.get("placement", 0),
                        "augments": ",".join(p.get("augments", [])),
                        "traits": ",".join([t["name"] for t in p.get("traits", []) if t["tier_current"] > 0]),
                        "start_timestamp": datetime.fromtimestamp(info_match["game_datetime"] / 1000),
                        "end_timestamp": datetime.fromtimestamp(
                            (info_match["game_datetime"] + info_match["game_length"] * 1000) / 1000),
                        "match_length": info_match["game_length"]
                    }

                    cur.execute("""
                            INSERT OR IGNORE INTO matches
                            (player, puuid, match_id, placement, augments, traits, start_timestamp, end_timestamp, match_length)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                                    record["player"], record["puuid"], record["match_id"],
                                    record["placement"], record["augments"], record["traits"],
                                    record["start_timestamp"], record["end_timestamp"], record["match_length"]
                    ))

                    if cur.rowcount > 0:  # was actually inserted
                        new_matches_count += 1

        print(f"Player [{name}] had {new_matches_count} new matches stored on this run.")

        conn.commit()

    except ApiError as err:
        print(f"Error fetching data for {name}: {err}")

# ---- QUERY RESULTS ----
df = pd.read_sql_query("SELECT * FROM matches", conn)

print("\n\n📊 Average placement per player with current rank:")
avg_df = df.groupby("player")["placement"].mean().reset_index()

for _, row in avg_df.iterrows():
    player_name = row['player']
    avg_placement = row['placement']

    # Fetch current TFT rank
    puuid = summoners[player_name]["puuid"]

    # Fetch league entries for TFT
    league_url = f"https://{region}.api.riotgames.com/tft/league/v1/by-puuid/{puuid}"
    response = requests.get(league_url, headers=headers)

    if response.status_code == 200:
        league_entries = response.json()
        tft_rank = "Unranked"
        for entry in league_entries:
            if entry["queueType"] == "RANKED_TFT":
                tft_rank = f"{entry['tier'].capitalize()} {entry['rank']}"
                break

        print(f"{player_name}: {avg_placement:.2f} {tft_rank}")
    else:
        print(league_url)
        print(f"Error fetching league data: {response.status_code} {response.text}")


conn.close()


