import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
from openai import OpenAI

app = FastAPI(title="Advanced Chronological Ledger Engine")

# OpenAI Client Setup 
# Local testing ke liye yahan apni "sk-proj-..." key daal sakti hain.
# GitHub par upload karne se pehle isko os.getenv("OPENAI_API_KEY") kar dena.
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# Input Data Structure
class IngestionPayload(BaseModel):
    files_count: int
    file_type: str  # medical, insurance, or legal
    target_threshold: float  # e.g., 5000.0
    unstructured_texts: List[str]

# Individual Event Structure
class LedgerEvent(BaseModel):
    date: str          # YYYY-MM-DD format
    date_type: str     # Document_Date or Incident_Treatment_Date
    description: str
    amount: float
    audit_flag: bool = False

# Robust AI Parsing Function with JSON Mode
def parse_text_with_ai(text: str, file_type: str) -> List[dict]:
    system_prompt = f"""
    You are an expert data extraction engine specializing in {file_type} documents.
    Extract all financial events, bills, treatment dates, or document dates from the text.
    For each event, extract:
    1. Date strictly normalized to YYYY-MM-DD. If year is missing, assume 2026.
    2. Date Type: Must be exactly 'Document_Date' or 'Incident_Treatment_Date'.
    3. Description: What happened or what was billed.
    4. Amount: Numeric dollar value (0.0 if not found).
    
    Return the output STRICTLY as a valid JSON object with an "events" key containing the array:
    {{ "events": [ {{"date": "YYYY-MM-DD", "date_type": "Incident_Treatment_Date", "description": "...", "amount": 1200.00}} ] }}
    Do not include any markdown formatting or backticks.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            temperature=0,
            response_format={ "type": "json_object" }  # OpenAI Strict JSON Mode
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # Clean potential markdown block wrappers just in case
        if raw_content.startswith("```"):
            raw_content = raw_content.split("\n", 1)[1]
        if raw_content.endswith("```"):
            raw_content = raw_content.rsplit("\n", 1)[0]
            
        clean_json = json.loads(raw_content.strip())
        
        # Safely extract array from JSON object
        if isinstance(clean_json, dict):
            if "events" in clean_json and isinstance(clean_json["events"], list):
                return clean_json["events"]
            # Fallback keys
            for key in ["timeline", "data", "ledger"]:
                if key in clean_json and isinstance(clean_json[key], list):
                    return clean_json[key]
            return [clean_json]
            
        return clean_json if isinstance(clean_json, list) else []
    except Exception as e:
        print(f"AI Extraction/Parsing Error: {e}")
        return []

# Main Process Endpoint
@app.post("/api/v1/ledger/process")
async def process_ledger(payload: IngestionPayload):
    # --- COMPLEXITY GATEWAY RULE ---
    if payload.files_count > 10:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Complexity Gate Triggered",
                "message": "Files count exceeds 10. Automatic loop frozen.",
                "redirect_to_funnel": "https://calendly.com/your-team-booking"
            }
        )
    
    all_events = []
    
    # Process inputs through the AI parser
    for text in payload.unstructured_texts:
        extracted_events = parse_text_with_ai(text, payload.file_type)
        for data in extracted_events:
            # --- ANOMALOUS PATTERN AUDIT LOGIC ---
            is_flagged = False
            amount_val = float(data.get("amount", 0))
            if amount_val > payload.target_threshold:
                is_flagged = True
            
            event = LedgerEvent(
                date=data.get("date", "2026-01-01"),
                date_type=data.get("date_type", "Incident_Treatment_Date"),
                description=data.get("description", "Unknown Event"),
                amount=amount_val,
                audit_flag=is_flagged
            )
            all_events.append(event)
            
    # --- TEMPORAL RECONCILIATION & CHRONOLOGICAL SORTING ---
    try:
        all_events.sort(key=lambda x: datetime.strptime(x.date, "%Y-%m-%d"))
    except Exception:
        all_events.sort(key=lambda x: x.date)

    return {
        "status": "success",
        "total_processed_events": len(all_events),
        "timeline": all_events
    }

@app.get("/")
def read_root():
    return {"message": "Ledger Engine Backend is Running Live!"}