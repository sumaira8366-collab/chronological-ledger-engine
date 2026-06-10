import os
import json
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse # <--- Naya import
from pydantic import BaseModel
from typing import List
from datetime import datetime
from openai import OpenAI

app = FastAPI(title="Advanced Chronological Ledger Engine")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE SETUP (Railway PostgreSQL / SQLite Compatibility) ---
# Railway automatically DATABASE_URL provide karta hai jab aap database attach karte hain
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        # Agar Railway par PostgreSQL hai (Iski zaroorat padegi, step 2 dekhein)
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        # Local testing ke liye SQLite
        return sqlite3.connect("ledger_data.db")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # SQLite aur PostgreSQL dono ke liye standard query
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            file_type TEXT,
            target_threshold REAL,
            raw_text TEXT
        )
    """)
    conn.commit()
    conn.close()

# SQLite local testing me create ho jayega, cloud par hum direct DB chalayenge
if not DATABASE_URL:
    init_db()

openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

class IngestionPayload(BaseModel):
    files_count: int
    file_type: str
    target_threshold: float
    unstructured_texts: List[str]

class LedgerEvent(BaseModel):
    date: str
    date_type: str
    description: str
    amount: float
    audit_flag: bool = False

def parse_text_with_ai(text: str, file_type: str) -> List[dict]:
    system_prompt = f"""
    You are an expert data extraction engine specializing in {file_type} documents.
    Extract all financial events, bills, treatment dates, or document dates from the text.
    Format output strictly as a valid JSON object with an "events" key:
    {{ "events": [ {{"date": "YYYY-MM-DD", "date_type": "Incident_Treatment_Date", "description": "...", "amount": 1200.00}} ] }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0,
            response_format={ "type": "json_object" }
        )
        raw_content = response.choices[0].message.content.strip()
        clean_json = json.loads(raw_content)
        return clean_json.get("events", [])
    except Exception as e:
        print(f"AI Error: {e}")
        return []

@app.post("/api/v1/ledger/process")
async def process_ledger(payload: IngestionPayload):
    if payload.files_count > 10:
        raise HTTPException(status_code=422, detail="Complexity Gate Triggered")
    
    # Database Connection Custom Method se handle hoga
    conn = get_db_connection()
    cursor = conn.cursor()
    combined_text = " | ".join(payload.unstructured_texts)
    
    # Adapt placeholder for PostgreSQL (%s) vs SQLite (?) if needed, 
    # but for simple cloud migration standard variables are adjusted.
    placeholder = "%s" if DATABASE_URL else "?"
    
    cursor.execute(
        f"INSERT INTO submissions (timestamp, file_type, target_threshold, raw_text) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), payload.file_type, payload.target_threshold, combined_text)
    )
    conn.commit()
    conn.close()
    
    all_events = []
    for text in payload.unstructured_texts:
        extracted_events = parse_text_with_ai(text, payload.file_type)
        for data in extracted_events:
            amount_val = float(data.get("amount", 0))
            event = LedgerEvent(
                date=data.get("date", "2026-01-01"),
                date_type=data.get("date_type", "Incident_Treatment_Date"),
                description=data.get("description", "Unknown Event"),
                amount=amount_val,
                audit_flag=amount_val > payload.target_threshold
            )
            all_events.append(event)
            
    try:
        all_events.sort(key=lambda x: datetime.strptime(x.date, "%Y-%m-%d"))
    except Exception:
        all_events.sort(key=lambda x: x.date)

    return {"status": "success", "timeline": all_events}

# --- YAHAN BADLAO KIYA HAI: Purane root message ki jagah index.html return karega ---
@app.get("/", response_class=HTMLResponse)
def read_root():
    # Yeh check karega ki repository me jahan main.py hai, wahi index.html hai ya nahi
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend index.html missing from root directory!</h1>"

# Backup route agar logs fir bhi /index.html dhoondein
@app.get("/index.html", response_class=HTMLResponse)
def read_html_explicit():
    return read_root()
