import sqlite3

conn = sqlite3.connect("database.db")

benutzername = input("Name: ") 

conn.execute("UPDATE users SET role='Admin' WHERE username=?", (benutzername,))
conn.commit()
conn.close()

print(f"Erfolgreich: {benutzername} ist jetzt Admin!")