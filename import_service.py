import pandas as pd
import anthropic
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def read_spreadsheet(file_path: str) -> pd.DataFrame:
    """Read CSV or Excel file into a DataFrame"""
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith(('.xlsx', '.xls')):
        return pd.read_excel(file_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or Excel.")

def analyze_columns(df: pd.DataFrame) -> dict:
    """Use Claude to figure out which columns map to which fields"""
    
    # Get sample data for Claude to analyze
    sample_data = df.head(3).to_string()
    columns = list(df.columns)
    
    prompt = f"""You are analyzing a spreadsheet that a fitness coach uses to track clients. 
Your job is to map the spreadsheet columns to our system's fields.

Our system has these fields:
- name (required): client's full name
- email (optional): client's email address  
- goal_weight (optional): target weight in lbs
- notes (optional): any notes about the client
- weight (optional): current or most recent weight in lbs

The spreadsheet has these columns:
{columns}

Here's a sample of the data:
{sample_data}

Analyze the column names and sample data to determine which spreadsheet columns map to which system fields.

Respond with ONLY a JSON object in this exact format, no other text:
{{
    "name": "column_name_or_null",
    "email": "column_name_or_null", 
    "goal_weight": "column_name_or_null",
    "notes": "column_name_or_null",
    "weight": "column_name_or_null",
    "confidence": "high/medium/low",
    "unmapped_columns": ["col1", "col2"]
}}

If you can't find a matching column, use null for that field.
For name, if there are separate first/last name columns, pick the one that seems like full name or first name."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    
    response_text = message.content[0].text
    
    # Parse JSON from response
    try:
        mapping = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON if there's extra text
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            mapping = json.loads(json_match.group())
        else:
            raise ValueError("Could not parse column mapping from AI response")
    
    return mapping

def preview_import(df: pd.DataFrame, mapping: dict) -> list[dict]:
    """Generate a preview of what will be imported"""
    previews = []
    
    for _, row in df.head(10).iterrows():
        preview = {
            "name": str(row[mapping["name"]]) if mapping.get("name") and mapping["name"] in df.columns else None,
            "email": str(row[mapping["email"]]) if mapping.get("email") and mapping["email"] in df.columns else None,
            "goal_weight": float(row[mapping["goal_weight"]]) if mapping.get("goal_weight") and mapping["goal_weight"] in df.columns and pd.notna(row[mapping["goal_weight"]]) else None,
            "notes": str(row[mapping["notes"]]) if mapping.get("notes") and mapping["notes"] in df.columns and pd.notna(row[mapping["notes"]]) else None,
            "weight": float(row[mapping["weight"]]) if mapping.get("weight") and mapping["weight"] in df.columns and pd.notna(row[mapping["weight"]]) else None,
        }
        if preview["name"]:  # Only include rows with a name
            previews.append(preview)
    
    return previews

def parse_spreadsheet_for_import(df: pd.DataFrame, mapping: dict) -> list[dict]:
    """Parse entire spreadsheet into importable records"""
    records = []
    
    for _, row in df.iterrows():
        record = {
            "name": str(row[mapping["name"]]).strip() if mapping.get("name") and mapping["name"] in df.columns and pd.notna(row[mapping["name"]]) else None,
            "email": str(row[mapping["email"]]).strip() if mapping.get("email") and mapping["email"] in df.columns and pd.notna(row[mapping["email"]]) else None,
            "goal_weight": None,
            "notes": None,
            "weight": None,
        }
        
        # Handle numeric fields carefully
        if mapping.get("goal_weight") and mapping["goal_weight"] in df.columns:
            try:
                val = row[mapping["goal_weight"]]
                if pd.notna(val):
                    record["goal_weight"] = float(val)
            except (ValueError, TypeError):
                pass
                
        if mapping.get("weight") and mapping["weight"] in df.columns:
            try:
                val = row[mapping["weight"]]
                if pd.notna(val):
                    record["weight"] = float(val)
            except (ValueError, TypeError):
                pass
        
        if mapping.get("notes") and mapping["notes"] in df.columns:
            val = row[mapping["notes"]]
            if pd.notna(val):
                record["notes"] = str(val).strip()
        
        # Only include records with a valid name
        if record["name"] and record["name"].lower() not in ['nan', 'none', '']:
            records.append(record)
    
    return records