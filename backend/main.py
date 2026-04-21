from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import random
import string
import math
import uvicorn
import os
import json
import hashlib
from datetime import datetime
import shutil

app = FastAPI(title="MineZon Pro API v2")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# Erstelle Upload-Verzeichnis, falls nicht vorhanden
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

DB_PATH = "database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users & Accounts
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, email TEXT UNIQUE, 
        password_hash TEXT, role TEXT DEFAULT 'User', is_verified INTEGER DEFAULT 0, verification_code TEXT, bio TEXT DEFAULT '')''')
    # Rooms (Server)
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        code TEXT PRIMARY KEY, owner_id INTEGER, currency_name TEXT DEFAULT '', is_currency_active INTEGER DEFAULT 0)''')
    # Active Players in Room
    c.execute('''CREATE TABLE IF NOT EXISTS room_players (
        user_id INTEGER, room_code TEXT, last_ping TEXT, balance REAL DEFAULT 100.0, PRIMARY KEY(user_id, room_code))''')
    # Shops (Mit user_id verknüpft)
    c.execute('''CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, user_id INTEGER, name TEXT, owner_name TEXT, 
        image_url TEXT, items_json TEXT, x INTEGER, y INTEGER, z INTEGER)''')
    # Bounties
    c.execute('''CREATE TABLE IF NOT EXISTS bounties (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, user_id INTEGER, buyer_name TEXT, item_wanted TEXT, reward TEXT)''')
    # Price History
    c.execute('''CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, server_code TEXT, item_name TEXT, price_value REAL, timestamp TEXT)''')
    # Private Messages
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER, receiver_id INTEGER, content TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNKTIONEN ---
def hash_pw(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user(token: Optional[str] = Header(None)):
    if not token: raise HTTPException(status_code=401, detail="Nicht eingeloggt")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, role, email, bio FROM users WHERE password_hash=?", (token,)) # Für dieses Beispiel nutzen wir den Hash als Token
    user = c.fetchone()
    conn.close()
    if not user: raise HTTPException(status_code=401, detail="Ungültiger Token")
    return {"id": user[0], "username": user[1], "role": user[2], "email": user[3], "bio": user[4]}

# --- DATENMODELLE ---
class UserRegister(BaseModel): username: str; email: str; password: str
class UserLogin(BaseModel): email: str; password: str
class VerifyCode(BaseModel): email: str; code: str
class ProfileUpdate(BaseModel): bio: str
class ShopItem(BaseModel): name: str; price: str; price_number: float
class ShopModel(BaseModel): server_code: str; name: str; image_url: str; items: List[ShopItem]; x: int; y: int; z: int
class BountyModel(BaseModel): server_code: str; item_wanted: str; reward: str
class MessageModel(BaseModel): receiver_name: str; content: str

# --- API: AUTHENTIFIZIERUNG ---
@app.post("/api/auth/register")
async def register(user: UserRegister):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    code = ''.join(random.choices(string.digits, k=6))
    try:
        c.execute("INSERT INTO users (username, email, password_hash, verification_code) VALUES (?,?,?,?)",
                  (user.username, user.email, hash_pw(user.password), code))
        conn.commit()
        # MOCK-EMAIL SENDEN
        print(f"--- EMAIL AN {user.email} ---")
        print(f"Dein MineZon Verifizierungs-Code ist: {code}")
        print(f"-----------------------------")
        return {"message": "Code gesendet. (Schau in die Konsolenausgabe des Servers!)"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Name oder E-Mail existiert bereits.")
    finally: conn.close()

@app.post("/api/auth/verify")
async def verify(data: VerifyCode):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=? AND verification_code=?", (data.email, data.code))
    user = c.fetchone()
    if not user: return HTTPException(status_code=400, detail="Falscher Code")
    c.execute("UPDATE users SET is_verified=1 WHERE id=?", (user[0],))
    conn.commit()
    conn.close()
    return {"message": "Verifiziert!"}

@app.post("/api/auth/login")
async def login(user: UserLogin):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    p_hash = hash_pw(user.password)
    c.execute("SELECT id, is_verified, password_hash FROM users WHERE email=? AND password_hash=?", (user.email, p_hash))
    u = c.fetchone()
    conn.close()
    if not u: raise HTTPException(status_code=400, detail="Falsche Daten")
    if u[1] == 0: raise HTTPException(status_code=403, detail="Bitte E-Mail verifizieren")
    return {"token": u[2]} # Simpler Token für dieses Projekt

@app.get("/api/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@app.post("/api/profile/update")
async def update_profile(data: ProfileUpdate, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET bio=? WHERE id=?", (data.bio, user["id"]))
    conn.commit()
    return {"status": "ok"}

# --- API: UPLOAD ---
@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    file_ext = file.filename.split(".")[-1]
    file_name = f"{random.randint(100000, 999999)}_{file.filename}"
    file_location = f"static/uploads/{file_name}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
    return {"url": f"/{file_location}"}

# --- API: SERVER / RÄUME ---
@app.get("/api/server/new")
async def create_server(user: dict = Depends(get_current_user)):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO rooms (code, owner_id) VALUES (?,?)", (code, user["id"]))
    conn.commit()
    return {"server_code": code}

@app.get("/api/server/ping/{server_code}")
async def ping_server(server_code: str, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Insert or update
    conn.execute('''INSERT INTO room_players (user_id, room_code, last_ping) VALUES (?,?,?)
                    ON CONFLICT(user_id, room_code) DO UPDATE SET last_ping=?''', 
                 (user["id"], server_code, now, now))
    
    # Hole Währungs-Info des Raumes und den Kontostand
    c = conn.cursor()
    # HIER IST DIE ÄNDERUNG (owner_id hinzugefügt):
    c.execute("SELECT currency_name, is_currency_active, owner_id FROM rooms WHERE code=?", (server_code,))
    room_info = c.fetchone()
    c.execute("SELECT balance FROM room_players WHERE user_id=? AND room_code=?", (user["id"], server_code))
    balance = c.fetchone()[0]
    
    # Hole aktive Spieler (Ping in den letzten 5 Minuten)
    c.execute('''SELECT u.username, u.role FROM room_players rp 
                 JOIN users u ON rp.user_id = u.id 
                 WHERE rp.room_code=? AND rp.last_ping >= datetime(?, '-5 minutes')''', (server_code, now))
    players = [{"username": r[0], "role": r[1]} for r in c.fetchall()]
    conn.commit()
    conn.close()
    
    # HIER IST DIE ÄNDERUNG (owner_id wird mitgeschickt):
    return {
        "players": players, 
        "currency_active": bool(room_info[1] if room_info else 0), 
        "currency_name": (room_info[0] if room_info else ""), 
        "balance": balance,
        "owner_id": (room_info[2] if room_info else None)
    }

class RoomSettingsUpdate(BaseModel):
    is_currency_active: bool
    currency_name: str

@app.post("/api/server/settings/{server_code}")
async def update_room_settings(server_code: str, settings: RoomSettingsUpdate, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT owner_id FROM rooms WHERE code=?", (server_code,))
    room = c.fetchone()
    if not room: raise HTTPException(404, "Raum nicht gefunden")
    if room[0] != user["id"] and user["role"] != "Admin": raise HTTPException(403, "Nur der Besitzer kann das ändern.")

    c.execute("UPDATE rooms SET is_currency_active=?, currency_name=? WHERE code=?",
              (1 if settings.is_currency_active else 0, settings.currency_name, server_code))
    conn.commit()
    conn.close()
    return {"status": "updated"}

# --- API: SHOPS ---
@app.post("/api/shops/add")
async def add_shop(shop: ShopModel, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    items_json = json.dumps([{"name": i.name, "price": i.price, "num": i.price_number} for i in shop.items])
    conn.execute("INSERT INTO shops (server_code, user_id, name, owner_name, image_url, items_json, x, y, z) VALUES (?,?,?,?,?,?,?,?,?)",
                 (shop.server_code, user["id"], shop.name, user["username"], shop.image_url, items_json, shop.x, shop.y, shop.z))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in shop.items:
        if item.price_number > 0:
            conn.execute("INSERT INTO price_history (server_code, item_name, price_value, timestamp) VALUES (?,?,?,?)",
                         (shop.server_code, item.name.lower(), item.price_number, now))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/shops/{server_code}")
async def get_shops(server_code: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute('''SELECT s.id, s.name, s.owner_name, s.image_url, s.items_json, s.x, s.y, s.z, u.role, s.user_id 
                             FROM shops s JOIN users u ON s.user_id = u.id WHERE s.server_code=?''', (server_code,))
    shops = [{"id": r[0], "name": r[1], "owner": r[2], "image_url": r[3], "items": json.loads(r[4]), 
              "x": r[5], "y": r[6], "z": r[7], "owner_role": r[8], "owner_id": r[9]} for r in cursor.fetchall()]
    conn.close()
    return shops

@app.delete("/api/shops/{shop_id}")
async def delete_shop(shop_id: int, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM shops WHERE id=?", (shop_id,))
    shop = c.fetchone()
    if not shop: raise HTTPException(404)
    if shop[0] != user["id"] and user["role"] != "Admin": raise HTTPException(403)
    c.execute("DELETE FROM shops WHERE id=?", (shop_id,))
    conn.commit()
    return {"status": "deleted"}

@app.post("/api/buy/{server_code}")
async def buy_item(server_code: str, shop_id: int, item_name: str, cost: float, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT user_id FROM shops WHERE id=?", (shop_id,))
    seller_id = c.fetchone()[0]
    
    if seller_id == user["id"]: return HTTPException(400, "Das ist dein eigener Shop!")
    
    c.execute("SELECT balance FROM room_players WHERE user_id=? AND room_code=?", (user["id"], server_code))
    buyer_balance = c.fetchone()[0]
    
    if buyer_balance < cost: return HTTPException(400, "Nicht genug Guthaben!")
    
    # Transaktion
    c.execute("UPDATE room_players SET balance = balance - ? WHERE user_id=? AND room_code=?", (cost, user["id"], server_code))
    c.execute("UPDATE room_players SET balance = balance + ? WHERE user_id=? AND room_code=?", (cost, seller_id, server_code))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- API: NACHRICHTEN ---
@app.post("/api/messages/send")
async def send_msg(msg: MessageModel, user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (msg.receiver_name,))
    rec = c.fetchone()
    if not rec: raise HTTPException(404, "Benutzer nicht gefunden")
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO messages (sender_id, receiver_id, content, timestamp) VALUES (?,?,?,?)",
              (user["id"], rec[0], msg.content, now))
    conn.commit()
    return {"status": "sent"}

@app.get("/api/messages")
async def get_messages(user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.execute('''SELECT m.content, m.timestamp, u.username FROM messages m
                        JOIN users u ON m.sender_id = u.id WHERE m.receiver_id=? ORDER BY m.id DESC''', (user["id"],))
    msgs = [{"content": r[0], "time": r[1], "sender": r[2]} for r in c.fetchall()]
    return msgs

# --- WIRTSCHAFTS-GRAPH ---
@app.get("/api/economy/chart/{server_code}")
async def get_chart_data(server_code: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT item_name, price_value, timestamp FROM price_history WHERE server_code=? ORDER BY timestamp ASC", (server_code,))
    rows = cursor.fetchall()
    datasets = {}
    for row in rows:
        item = row[0]
        if item not in datasets: datasets[item] = {"prices": [], "times": []}
        datasets[item]["prices"].append(row[1])
        datasets[item]["times"].append(row[2])
    return datasets

# --- FRONTEND AUSLIEFERN ---
# --- FRONTEND AUSLIEFERN ---
@app.get("/")
async def serve_frontend():
    # Geht einen Ordner zurück (..) und sucht dann im "frontend" Ordner nach der index.html
    html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    
    # Sicherheitscheck, falls der Pfad immer noch nicht stimmt
    if not os.path.exists(html_path):
        return {"error": f"Datei nicht gefunden: {html_path}. Bitte überprüfe deine Ordnerstruktur."}
        
    return FileResponse(html_path)