import os
import json
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from datetime import datetime
from openai import OpenAI

app = FastAPI(title="Advanced Chronological Ledger Engine")

# CORS Setup taaki frontend backend se connect ho sake
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLite Database Setup
DB_FILE = "ledger_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
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

init_db()

openai_api_key = os.getenv("OPENAI_API_KEY")
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
    
    # Save Inputs to Database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    combined_text = " | ".join(payload.unstructured_texts)
    cursor.execute(
        "INSERT INTO submissions (timestamp, file_type, target_threshold, raw_text) VALUES (?, ?, ?, ?)",
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

@app.get("/")
def read_root():
    return {"message": "Ledger Engine Backend with Database Running!"}
