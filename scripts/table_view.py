import sqlite3
import pandas as pd

conn = sqlite3.connect("../tft_matches.db")
print(f"Connected to database succesfully.")

table_viewed = 'matches'  #<---- change this variable to view a different table

df = pd.read_sql_query(f"""SELECT * FROM {table_viewed};""", conn)
print(df)
conn.close()