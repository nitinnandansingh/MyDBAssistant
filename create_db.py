import sqlite3

# Connect to SQLite database (it will create the database file if it does not exist)
conn = sqlite3.connect('mydatabase.db')

# Read the SQL file
with open('Chinook_Sqlite.sql', 'r') as file:
    sql_script = file.read()

# Execute the SQL script
with conn:
    conn.executescript(sql_script)

# Close the connection
conn.close()