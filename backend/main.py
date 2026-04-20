from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import random
import string
import math
import uvicorn
import os

app = FastAPI(title="MineZon Pro API")

# Erlaubt dem Frontend, mit dem Backend zu sprechen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATENBANK SETUP ---
DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Tabelle für Shops
    cursor.execute('''CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, name TEXT, owner TEXT, item TEXT, price TEXT, x INTEGER, y INTEGER, z INTEGER)''')
    # Tabelle für Aufträge (Bounties)
    cursor.execute('''CREATE TABLE IF NOT EXISTS bounties (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, buyer TEXT, item_wanted TEXT, reward TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- DATENMODELLE (Pydantic) ---
class Shop(BaseModel):
    server_code: str
    name: str
    owner: str
    item: str
    price: str
    x: int
    y: int
    z: int

class Bounty(BaseModel):
    server_code: str
    buyer: str
    item_wanted: str
    reward: str

# --- HILFSFUNKTIONEN (Business Logic) ---
def calculate_distance(x1, y1, z1, x2, y2, z2):
    return round(math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2))

def get_nether_coords(x, z):
    return f"{x // 8}, {z // 8}"

# --- API ENDPUNKTE ---

@app.get("/")
async def serve_frontend():
    # Liefert die HTML-Datei aus dem frontend-Ordner
    html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    return FileResponse(html_path)

@app.get("/api/server/new")
async def create_server():
    return {"server_code": ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}

@app.post("/api/shops/add")
async def add_shop(shop: Shop):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO shops (server_code, name, owner, item, price, x, y, z) VALUES (?,?,?,?,?,?,?,?)",
                 (shop.server_code, shop.name, shop.owner, shop.item, shop.price, shop.x, shop.y, shop.z))
    conn.commit()
    return {"status": "success"}

@app.get("/api/shops/{server_code}")
async def get_shops(server_code: str, player_x: Optional[int] = None, player_y: Optional[int] = None, player_z: Optional[int] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT name, owner, item, price, x, y, z FROM shops WHERE server_code=?", (server_code,))
    rows = cursor.fetchall()
    
    shops = []
    for row in rows:
        shop_data = {
            "name": row[0], "owner": row[1], "item": row[2], "price": row[3],
            "x": row[4], "y": row[5], "z": row[6],
            "nether_coords": get_nether_coords(row[4], row[6])
        }
        # Smart Navi Feature
        if player_x is not None and player_y is not None and player_z is not None:
            shop_data["distance"] = calculate_distance(player_x, player_y, player_z, row[4], row[5], row[6])
        
        shops.append(shop_data)

    # Wenn Spieler-Koordinaten da sind, sortiere nach Entfernung (nächster zuerst)
    if player_x is not None:
        shops.sort(key=lambda s: s["distance"])

    return shops

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)