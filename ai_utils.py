# ai_utils.py
# This file handles all interactions with the AI model (OpenAI).

import streamlit as st
import re
from openai import OpenAI

# --- OpenAI Client Initialization ---
@st.cache_resource
def init_openai_client():
    """Initializes and returns the OpenAI client."""
    try:
        openai_key = st.secrets.get("openai_api_key")
        if openai_key:
            return OpenAI(api_key=openai_key)
        else:
            st.error("OpenAI API Key nicht in den Secrets gefunden.")
            return None
    except Exception as e:
        st.error(f"Fehler bei der Initialisierung des OpenAI Clients: {e}")
        return None

ai_client = init_openai_client()

# --- AI Prompt and Plan Parsing Functions ---

def parse_ai_plan_to_rows(ai_response_text: str, auth_user_id: str) -> list:
    """
    Parses a Markdown table from the AI's response into a list of dictionaries
    ready for Supabase insertion into the 'workouts' table.
    """
    rows = []
    # Find all lines that look like Markdown table rows (surrounded by |)
    table_lines = [line.strip() for line in ai_response_text.split('\n') if line.strip().startswith('|') and line.strip().endswith('|')]
    
    if len(table_lines) < 3:
        # If no table is found, we cannot proceed.
        return []

    # --- Column Name Mapping ---
    # Maps possible German/English names to the exact DB column names
    COLUMN_MAP = {
        'tag': 'day',
        'day': 'day',
        'übung': 'exercise_name',
        'exercise': 'exercise_name',
        'exercise_name': 'exercise_name',
        'sätze': 'sets',
        'sets': 'sets',
        'wiederholungen': 'reps',
        'reps': 'reps',
        'gewicht': 'weight',
        'weight': 'weight',
        'notizen': 'notes',
        'notes': 'notes'
    }

    # Extract and normalize the header
    header_raw = [h.strip().lower() for h in table_lines[0].split('|')][1:-1] # [1:-1] to remove empty ends
    header = [COLUMN_MAP.get(h, h) for h in header_raw]
    
    # Process the data rows (everything after the header and separator line)
    workout_lines = table_lines[2:]

    for line in workout_lines:
        values = [v.strip() for v in line.split('|')][1:-1]
        
        if len(values) != len(header):
            continue # Skip malformed rows

        row_dict = dict(zip(header, values))
        
        # --- CRITICAL: Add the auth_user_id to every single record! ---
        row_dict['auth_user_id'] = auth_user_id
        
        # --- Data Type Conversion and Cleanup ---
        # Convert 'sets' to integer
        try:
            row_dict['sets'] = int(row_dict.get('sets', 0))
        except (ValueError, TypeError):
            row_dict['sets'] = 0
        
        # Convert 'weight' to float, removing any "kg" etc.
        try:
            weight_str = re.sub(r'[^0-9.]', '', str(row_dict.get('weight', '0')))
            row_dict['weight'] = float(weight_str) if weight_str else 0.0
        except (ValueError, TypeError):
            row_dict['weight'] = 0.0
        
        # Ensure 'reps' is a string
        row_dict['reps'] = str(row_dict.get('reps', '0'))

        # Ensure 'notes' exists, even if empty
        row_dict.setdefault('notes', '')

        # Ensure all core fields for the new schema are present
        final_row = {
            'auth_user_id': row_dict['auth_user_id'],
            'day': row_dict.get('day', 'Unbekannter Tag'),
            'exercise_name': row_dict.get('exercise_name', 'Unbekannte Übung'),
            'sets': row_dict.get('sets', 0),
            'reps': row_dict.get('reps', '0'),
            'weight': row_dict.get('weight', 0.0),
            'notes': row_dict.get('notes', ''),
            'completed_sets': 0 # Add a field to track progress
        }
        rows.append(final_row)
    
    return rows


def get_chat_response(history):
    """Sends the chat history to the AI and gets a contextual response."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden. Bitte prüfe den API-Key."

    # --- REVISED SYSTEM PROMPT ---
    system_prompt = {
        "role": "system",
        "content": """Du bist Milo, ein persönlicher KI-Coach. Deine Aufgabe ist es, mit dem Nutzer interaktiv einen Trainingsplan zu erstellen.
1. Beginne IMMER mit einer kurzen, motivierenden Erklärung.
2. Erstelle den Plan danach IMMER als Markdown-Tabelle.
3. Die Tabelle MUSS die Spalten `Tag`, `Übung`, `Sätze`, `Wiederholungen`, `Gewicht`, und `Notizen` enthalten.
4. Wenn der Nutzer Änderungen vorschlägt (z.B. "ersetze Übung X"), passe den letzten Plan an und sende den **kompletten, aktualisierten Plan** als neue Markdown-Tabelle zurück.
5. Behalte immer deine freundliche, motivierende und kompetente Coach-Persönlichkeit bei.
"""
    }
    
    messages_to_send = [system_prompt] + history

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_to_send,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei der Kommunikation mit der KI: {e}")
        return "Es tut mir leid, es gab ein Problem bei der Verbindung zur KI."
