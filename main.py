import os
import json
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from openai import OpenAI

app = FastAPI(title="Advanced Chronological Ledger Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    else:
        return sqlite3.connect("ledger_data.db")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id SERIAL PRIMARY KEY,
                timestamp TEXT,
                file_type TEXT,
                target_threshold REAL,
                raw_text TEXT
            );
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                file_type TEXT,
                target_threshold REAL,
                raw_text TEXT
            );
        """)
    conn.commit()
    conn.close()

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
    source_file: str
    custom_comment: str = ""
    audit_flag: bool = False

def parse_text_with_ai(text: str, file_type: str) -> dict:
    # Strict compliance prompt to classify dates and catch non-compliant items
    system_prompt = f"""
    You are an expert data extraction engine specializing in {file_type} documents.
    Extract all financial events, bills, treatment dates, or document dates.
    
    CRITICAL RULES:
    1. Multi-point temporal matching: Explicitly split dates into either 'Document_Date' or 'Incident_Treatment_Date'.
    2. If a date fragment is ambiguous, incomplete, or un-parseable, DO NOT make it up. Instead, add it to the 'omitted_dates' list.
    
    Format output strictly as a valid JSON object matching this schema:
    {{
        "events": [
            {{"date": "YYYY-MM-DD", "date_type": "Incident_Treatment_Date", "description": "...", "amount": 1200.00, "source_file": "document_stream.txt"}}
        ],
        "omitted_dates": ["Ambiguous fragment 05/2026", "Incomplete transaction break"]
    }}
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
        return json.loads(raw_content)
    except Exception as e:
        print(f"AI Error: {e}")
        return {"events": [], "omitted_dates": []}

@app.post("/api/v1/ledger/process")
async def process_ledger(payload: IngestionPayload):
    # Complexity Gateway Guardrail
    if payload.files_count > 10:
        raise HTTPException(status_code=422, detail="Complexity Gate Triggered: Payload too dense.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    combined_text = " | ".join(payload.unstructured_texts)
    
    placeholder = "%s" if DATABASE_URL else "?"
    cursor.execute(
        f"INSERT INTO submissions (timestamp, file_type, target_threshold, raw_text) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), payload.file_type, payload.target_threshold, combined_text)
    )
    conn.commit()
    conn.close()
    
    all_events = []
    all_omitted = []
    
    for idx, text in enumerate(payload.unstructured_texts):
        result_data = parse_text_with_ai(text, payload.file_type)
        extracted_events = result_data.get("events", [])
        omitted_dates = result_data.get("omitted_dates", [])
        
        all_omitted.extend(omitted_dates)
        
        for data in extracted_events:
            amount_val = float(data.get("amount", 0))
            event = LedgerEvent(
                date=data.get("date", "2026-01-01"),
                date_type=data.get("date_type", "Incident_Treatment_Date"),
                description=data.get("description", "Unknown Event"),
                amount=amount_val,
                source_file=data.get("source_file", f"Segment_{idx+1}.txt"),
                custom_comment="Initial parsed block record comment.",
                audit_flag=amount_val > payload.target_threshold
            )
            all_events.append(event)
            
    try:
        all_events.sort(key=lambda x: datetime.strptime(x.date, "%Y-%m-%d"))
    except Exception:
        all_events.sort(key=lambda x: x.date)

    return {
        "status": "success", 
        "total_dates_extracted": len(all_events),
        "omitted_non_compliant_dates": all_omitted,
        "timeline": all_events
    }

@app.get("/", response_class=HTMLResponse)
def read_root():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Frontend index.html missing!</h1>"

@app.get("/index.html", response_class=HTMLResponse)
def read_html_explicit():
    return read_root()
