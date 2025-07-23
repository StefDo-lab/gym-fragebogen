# ai_utils.py
# This file handles all interactions with the AI model (OpenAI).

import streamlit as st
import re
from openai import OpenAI
import datetime

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

def parse_ai_plan_to_rows(plan_text: str, user_profile: dict) -> list:
    """
    Parses the AI-generated plan text (Markdown table) into structured data for the database.
    This version creates one row PER SET, matching the original database schema.
    """
    rows = []
    current_date = datetime.date.today().isoformat()
    user_data_uuid = user_profile.get("uuid")
    user_name = f"{user_profile.get('forename', '')} {user_profile.get('surename', '')}".strip()

    # Regex to find Markdown table rows
    lines = plan_text.split('\n')
    table_lines = [line for line in lines if '|' in line and not line.startswith('---')]

    if len(table_lines) < 2:
        st.error("Keine gültige Markdown-Tabelle im KI-Output gefunden.")
        return []

    # Dynamically find column indices from header
    header = [h.strip().lower() for h in table_lines[0].split('|')]
    try:
        # Map headers to the keys we need, allowing for variations
        col_map = {
            'tag': header.index('tag'),
            'übung': header.index('übung'),
            'sätze': header.index('sätze'),
            'wiederholungen': header.index('wiederholungen'),
            'gewicht': header.index('gewicht'),
            'notizen': header.index('notizen'),
        }
    except ValueError as e:
        st.error(f"Fehlende Spalte im Tabellenkopf: {e}. Die Tabelle muss 'Tag', 'Übung', 'Sätze', 'Wiederholungen', 'Gewicht' und 'Notizen' enthalten.")
        return []

    # Process each data row (skipping the header)
    for line in table_lines[1:]:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < len(header):
            continue

        try:
            day = parts[col_map['tag']]
            exercise_name = parts[col_map['übung']]
            sets_str = parts[col_map['sätze']]
            reps_str = parts[col_map['wiederholungen']]
            weight_str = parts[col_map['gewicht']]
            notes = parts[col_map['notizen']]

            # Extract numbers from strings
            sets = int(re.search(r'\d+', sets_str).group()) if re.search(r'\d+', sets_str) else 0
            weight_val_str = re.search(r'(\d+[\.,]?\d*)', weight_str)
            weight = float(weight_val_str.group(1).replace(',', '.')) if weight_val_str else 0.0

            # Create one row for each set
            for i in range(1, sets + 1):
                rows.append({
                    'uuid': user_data_uuid, 
                    'date': current_date, 
                    'name': user_name,
                    'workout': day, # Use the 'Tag' as the workout name
                    'exercise': exercise_name,
                    'set': i, 
                    'weight': weight,
                    'reps': reps_str, # Store the target reps string (e.g., "8-12")
                    'unit': 'kg', 
                    'type': '', 
                    'completed': False, # This is the crucial flag
                    'messageToCoach': '', 
                    'messageFromCoach': notes, # Store notes here
                    'rirSuggested': 0, 
                    'rirDone': 0,
                    # Add all dummy columns to match the table schema exactly
                    'generalStatementFrom': '', 'generalStatementTo': '',
                    'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
                    'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
                })
        except (ValueError, TypeError, IndexError) as e:
            st.warning(f"Konnte Zeile nicht verarbeiten: '{line}' ({e})")
            continue
            
    return rows

def get_chat_response(history):
    """Sends the chat history to the AI and gets a contextual response."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden. Bitte prüfe den API-Key."

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
