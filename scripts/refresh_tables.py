import sqlite3

#-----THIS IS ONLY FOR FULLY EMPTYING TABLES FOR WHATEVER REASON (Or Dropping)----------
conn = sqlite3.connect("../tft_matches.db")
print("Connected to database successfully.")
cur = conn.cursor()

table_refreshed = 'matches'  # <----------- Change this variable to change which table is being refreshed

# Drop the Table
cur.execute(f"DROP TABLE {table_refreshed};")
print(f"TABLE [{table_refreshed}] has been dropped.")

# # Empties table
# cur.execute(f"DELETE FROM {table_refreshed};")
# print(f"{table_refreshed} has been refreshed.")
#
# # Resets the AUTOINCREMENT counter
# cur.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_refreshed}';")
# print(f"{table_refreshed} AUTOINCREMENT has been reset.")

conn.commit()
conn.close()
