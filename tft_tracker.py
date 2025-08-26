import requests
import sqlite3
import pandas as pd
from riotwatcher import LolWatcher, TftWatcher, ApiError
from dotenv import load_dotenv
import os

# ---- CONFIG FROM .env ----
load_dotenv()  # read .env file

api_key = os.getenv("API_KEY")
region = os.getenv("REGION")
continent = os.getenv("CONTINENT")
match_count = int(os.getenv("MATCH_COUNT"))

headers = {"X-Riot-Token": api_key}

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

# ---- SETUP DATABASE ----
conn = sqlite3.connect("tft_matches.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player TEXT,
    puuid TEXT,
    match_id TEXT,
    placement INTEGER,
    augments TEXT,
    traits TEXT
)
""")
conn.commit()

# ---- FETCH MATCH DATA ----
for name, info in summoners.items():
    puuid = info["puuid"]
    try:
        match_ids = tft_watcher.match.by_puuid(continent, puuid, count=match_count)

        for match_id in match_ids:
            match = tft_watcher.match.by_id(continent, match_id)
            info_match = match['info']

            for p in info_match['participants']:
                if p['puuid'] == puuid:
                    record = {
                        "player": name,
                        "puuid": puuid,
                        "match_id": match_id,
                        "placement": p.get("placement", 0),
                        "augments": ",".join(p.get("augments", [])),
                        "traits": ",".join([t["name"] for t in p.get("traits", []) if t["tier_current"] > 0])
                    }

                    cur.execute("""
                        INSERT INTO matches (player, puuid, match_id, placement, augments, traits)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        record["player"], record["puuid"], record["match_id"],
                        record["placement"], record["augments"], record["traits"]
                    ))
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


