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

def get_ai_prompt_template():
    """Loads the main AI prompt from an external file."""
    try:
        with open('ai_prompt.txt', 'r', encoding='utf-8') as file:
            content = file.read()
            if '### ENDE KONFIGURATION ###' in content:
                return content.split('### ENDE KONFIGURATION ###', 1)[1]
            return content
    except FileNotFoundError:
        st.error("WICHTIG: Die Datei 'ai_prompt.txt' wurde nicht gefunden. Bitte erstellen Sie sie.")
        return "Erstelle einen Trainingsplan für: {user_request}"

def parse_ai_plan_to_rows(plan_text: str, user_profile: dict):
    """
    Parses the AI-generated plan text, expecting the TEIL 1 / TEIL 2 structure.
    """
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = "Trainingsplan"
    
    user_uuid = user_profile.get("uuid")
    user_name = f"{user_profile.get('forename', '')} {user_profile.get('surename', '')}".strip()

    plan_section = plan_text
    if "TEIL 2 - DER TRAININGSPLAN" in plan_text:
        plan_section = plan_text.split("TEIL 2 - DER TRAININGSPLAN", 1)[1]

    lines = plan_section.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if line.startswith('**') and line.endswith(':'):
            current_workout = line.strip('*').strip(':').strip()
            continue

        exercise_match = re.match(r'^\s*[-*]\s*(.+?):\s*(.*)', line)
        if exercise_match:
            exercise_name = exercise_match.group(1).strip()
            details = exercise_match.group(2).strip()
            
            try:
                sets, weight, explanation = 3, 0.0, ""
                reps_str_full = "10"
                
                sets_match = re.search(r'(\d+)\s*(?:x|[Ss]ätze|[Ss]ets)', details)
                if sets_match: sets = int(sets_match.group(1))

                weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                if weight_match: weight = float(weight_match.group(1).replace(',', '.'))
                elif "körpergewicht" in details.lower() or "bw" in details.lower():
                    weight = 0.0

                reps_match = re.search(r'(\d+)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match: reps_str_full = reps_match.group(1).strip()

                explanation_match = re.search(r'\((?:Fokus|Erklärung):\s*(.+)\)$', details)
                if explanation_match: explanation = explanation_match.group(1).strip()

                reps_for_db = int(reps_str_full)
                full_coach_message = f"Ziel: {reps_str_full} Wdh. {explanation}".strip()

                for i in range(1, sets + 1):
                    rows.append({
                        'uuid': user_uuid, 'date': current_date, 'name': user_name,
                        'workout': current_workout, 'exercise': exercise_name, 'set': i, 
                        'weight': weight, 'reps': reps_for_db, 'unit': 'kg',
                        'completed': False, 'messagetoCoach': '', 'messagefromCoach': full_coach_message,
                        'rirdone': 0 
                    })
            except Exception as e:
                st.warning(f"Konnte Zeile nicht verarbeiten: '{line}' ({e})")

    return rows

def get_chat_response(messages: list, user_profile: dict, history_analysis: str):
    """Builds the prompt from the template and chat history, then gets a response."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden."

    prompt_template = get_ai_prompt_template()
    chat_history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
    
    system_prompt_content = prompt_template.format(
        profile=user_profile,
        history_analysis=history_analysis,
        additional_info=chat_history_text, 
        training_days=user_profile.get("training_days_per_week", 3),
        split_type="passend zum Profil", 
        focus=user_profile.get("primary_goal", "Muskelaufbau"),
        weight_instruction="Basiere die Gewichte auf der Trainingshistorie oder schlage für Anfänger passende Startgewichte vor."
    )

    messages_to_send = [{"role": "user", "content": system_prompt_content}]

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages_to_send,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei der Kommunikation mit der KI: {e}")
        return "Es tut mir leid, es gab ein Problem bei der Verbindung zur KI."

def get_initial_plan_response(user_profile: dict):
    """Generates the very first plan proposal based on the questionnaire data."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden."

    prompt_template = get_ai_prompt_template()
    
    # Create a specific initial prompt for the AI
    initial_prompt_text = "Hallo Milo, hier ist ein neuer Athlet. Bitte erstelle einen ersten, passenden Trainingsplan-Vorschlag basierend auf dem Profil. Begrüsse den Athleten freundlich und erkläre ihm kurz, warum der Plan so aufgebaut ist."

    system_prompt_content = prompt_template.format(
        profile=user_profile,
        history_analysis="Keine Trainingshistorie vorhanden, da der Nutzer neu ist.",
        additional_info=initial_prompt_text,
        training_days=user_profile.get("training_days_per_week", 3),
        split_type="passend zum Profil",
        focus=user_profile.get("primary_goal", "Muskelaufbau"),
        weight_instruction="Schlage für Anfänger passende Startgewichte vor. Für Fortgeschrittene, gib Platzhalter an."
    )

    messages_to_send = [{"role": "user", "content": system_prompt_content}]

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages_to_send,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei der Kommunikation mit der KI: {e}")
        return "Es tut mir leid, es gab ein Problem bei der Verbindung zur KI."