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
import json
from datetime import datetime

app = FastAPI(title="MineZon Pro API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Neue Shop Tabelle (mit items_json und image_url)
    cursor.execute('''CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, name TEXT, owner TEXT, 
        image_url TEXT, items_json TEXT, x INTEGER, y INTEGER, z INTEGER)''')
    # Schwarzes Brett (Bounties)
    cursor.execute('''CREATE TABLE IF NOT EXISTS bounties (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, buyer TEXT, item_wanted TEXT, reward TEXT)''')
    # Preis-Historie (Für den Graphen)
    cursor.execute('''CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, item_name TEXT, price_value REAL, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- DATENMODELLE ---
class ShopItem(BaseModel):
    name: str
    price: str
    price_number: float # Für den Graphen (z.B. "10" wenn es 10 Dias kostet)

class Shop(BaseModel):
    server_code: str
    name: str
    owner: str
    image_url: str
    items: List[ShopItem]
    x: int
    y: int
    z: int

class Bounty(BaseModel):
    server_code: str
    buyer: str
    item_wanted: str
    reward: str

# --- HILFSFUNKTIONEN ---
def get_nether_coords(x, z):
    return f"{x // 8}, {z // 8}"

# --- API ENDPUNKTE ---

@app.get("/")
async def serve_frontend():
    html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    return FileResponse(html_path)

@app.get("/api/server/new")
async def create_server():
    return {"server_code": ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}

@app.post("/api/shops/add")
async def add_shop(shop: Shop):
    conn = sqlite3.connect(DB_PATH)
    items_json = json.dumps([{"name": i.name, "price": i.price} for i in shop.items])
    
    conn.execute("INSERT INTO shops (server_code, name, owner, image_url, items_json, x, y, z) VALUES (?,?,?,?,?,?,?,?)",
                 (shop.server_code, shop.name, shop.owner, shop.image_url, items_json, shop.x, shop.y, shop.z))
    
    # Preise in die Historie für den Graphen schreiben
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in shop.items:
        if item.price_number > 0:
            conn.execute("INSERT INTO price_history (server_code, item_name, price_value, timestamp) VALUES (?,?,?,?)",
                         (shop.server_code, item.name.lower(), item.price_number, now))
            
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/shops/{server_code}")
async def get_shops(server_code: str, player_x: Optional[int] = None, player_y: Optional[int] = None, player_z: Optional[int] = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT name, owner, image_url, items_json, x, y, z, id FROM shops WHERE server_code=?", (server_code,))
    rows = cursor.fetchall()
    
    shops = []
    for row in rows:
        shop_data = {
            "name": row[0], "owner": row[1], "image_url": row[2], 
            "items": json.loads(row[3]), "x": row[4], "y": row[5], "z": row[6],
            "nether_coords": get_nether_coords(row[4], row[6]), "id": row[7]
        }
        if player_x is not None and player_y is not None and player_z is not None:
            shop_data["distance"] = round(math.sqrt((player_x - row[4])**2 + (player_y - row[5])**2 + (player_z - row[6])**2))
        shops.append(shop_data)

    if player_x is not None:
        shops.sort(key=lambda s: s.get("distance", 999999))
    return shops

# --- BOUNTY ENDPUNKTE (Schwarzes Brett) ---
@app.post("/api/bounties/add")
async def add_bounty(bounty: Bounty):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO bounties (server_code, buyer, item_wanted, reward) VALUES (?,?,?,?)",
                 (bounty.server_code, bounty.buyer, bounty.item_wanted, bounty.reward))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/bounties/{server_code}")
async def get_bounties(server_code: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT buyer, item_wanted, reward FROM bounties WHERE server_code=?", (server_code,))
    bounties = [{"buyer": row[0], "item_wanted": row[1], "reward": row[2]} for row in cursor.fetchall()]
    conn.close()
    return bounties

# --- WIRTSCHAFTS-GRAPH ---
@app.get("/api/economy/chart/{server_code}")
async def get_chart_data(server_code: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT item_name, price_value, timestamp FROM price_history WHERE server_code=? ORDER BY timestamp ASC", (server_code,))
    rows = cursor.fetchall()
    conn.close()
    
    # Gruppiere Daten nach Items für den Chart
    datasets = {}
    for row in rows:
        item = row[0]
        if item not in datasets:
            datasets[item] = {"prices": [], "times": []}
        datasets[item]["prices"].append(row[1])
        datasets[item]["times"].append(row[2])
        
    return datasets

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)