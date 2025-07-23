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

def parse_ai_plan_to_rows(plan_text: str, user_profile: dict):
    """
    Parses the AI-generated plan text into structured data for the database,
    based on the proven logic from the working monolithic file.
    It creates one row PER SET.
    """
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = "Unbenanntes Workout"
    
    # Get user identifiers from the profile dictionary
    user_uuid = user_profile.get("uuid")
    user_name = f"{user_profile.get('forename', '')} {user_profile.get('surename', '')}".strip()

    lines = plan_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # KORRIGIERT: Flexiblere Erkennung des Workout-Namens (Doppelpunkt ist optional)
        # Verhindert auch, dass eine Übung fälschlicherweise als Workout-Name erkannt wird.
        workout_match = re.match(r'^\*\*(.+?):?\*\*', line)
        if workout_match and ":" not in workout_match.group(1):
            current_workout = workout_match.group(1).strip()
            continue
        
        # Match exercise lines like "- Exercise: 3 Sätze, 8-10 Wdh, 60 kg (Fokus: ...)"
        exercise_match = re.match(r'^\s*[-*]\s*(.+?):\s*(.*)', line)
        if exercise_match:
            # KORRIGIERT: Bereinige den Übungsnamen von Markdown-Sternchen
            exercise_name = exercise_match.group(1).strip().strip('*')
            details = exercise_match.group(2).strip()
            
            try:
                # Default values
                sets, weight, reps, explanation = 3, 0.0, "10", ""
                
                # Parse details using regex
                sets_match = re.search(r'(\d+)\s*(?:x|[Ss]ätze|[Ss]ets)', details)
                if sets_match: sets = int(sets_match.group(1))

                weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                if weight_match: weight = float(weight_match.group(1).replace(',', '.'))

                reps_match = re.search(r'(\d+\s*-\s*\d+|\d+)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match: reps = reps_match.group(1).strip()

                explanation_match = re.search(r'\((?:Fokus|Erklärung):\s*(.+)\)$', details)
                if explanation_match: explanation = explanation_match.group(1).strip()

                # Create one row for each set
                for i in range(1, sets + 1):
                    # This dictionary structure MUST EXACTLY match the Supabase table
                    rows.append({
                        'uuid': user_uuid, 
                        'date': current_date, 
                        'name': user_name,
                        'workout': current_workout,
                        'exercise': exercise_name,
                        'set': i, 
                        'weight': weight,
                        'reps': reps, # Store the target reps string (e.g., "8-12")
                        'unit': 'kg', 
                        'type': '', 
                        'completed': False,
                        'messageToCoach': '', 
                        'messageFromCoach': explanation,
                        'rirSuggested': 0, 
                        'rirDone': 0, 
                        'generalStatementFrom': '', 
                        'generalStatementTo': '',
                        'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
                        'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
                    })
            except Exception as e:
                st.warning(f"Konnte Zeile nicht verarbeiten: '{line}' ({e})")

    return rows


def get_chat_response(history):
    """Sends the chat history to the AI and gets a contextual response."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden. Bitte prüfe den API-Key."

    system_prompt = {
        "role": "system",
        "content": """Du bist Milo, ein persönlicher KI-Coach. Deine Aufgabe ist es, mit dem Nutzer interaktiv einen Trainingsplan zu erstellen.
1. Beginne IMMER mit einer kurzen, motivierenden Erklärung.
2. Erstelle den Plan danach. Jeder Trainingstag MUSS mit einem Workout-Namen beginnen im Format: **Name des Workouts:**
3. Format pro Übung EXAKT so: - Übungsname: X Sätze, Y Wdh, Z kg (Fokus: Kurzer Hinweis)
4. Wenn der Nutzer Änderungen vorschlägt (z.B. "ersetze Übung X"), passe den letzten Plan an und sende den **kompletten, aktualisierten Plan** zurück.
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
