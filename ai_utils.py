# ai_utils.py
# This file handles all interactions with the AI model (OpenAI).

import streamlit as st
import re
import pandas as pd
from openai import OpenAI
import datetime

# --- OpenAI Client Initialization ---
@st.cache_resource
def init_openai_client():
    """Initializes and returns the OpenAI client."""
    try:
        openai_key = st.secrets.get("openai_api_key", None)
        if openai_key:
            return OpenAI(api_key=openai_key)
    except Exception:
        return None
    return None

ai_client = init_openai_client()

# --- AI Prompt and Plan Parsing Functions ---
def get_ai_prompt_template():
    """
    Loads the AI prompt template and configuration from an external file.
    Falls back to a default prompt if the file is not found.
    This function is now mainly a fallback or for non-chat plan generation.
    """
    config = {
        'temperature': 0.7,
        'model': 'gpt-4o-mini',
        'max_tokens': 4000,
        'top_p': 1.0,
        'prompt': ''
    }
    
    try:
        with open('ai_prompt.txt', 'r', encoding='utf-8') as file:
            config['prompt'] = file.read()
    except FileNotFoundError:
        st.warning("ai_prompt.txt nicht gefunden! Verwende eingebautes Template.")
        config['prompt'] = """
Du bist Milo, ein persönlicher KI-Coach, benannt nach dem antiken Athleten Milon von Kroton, der für das Prinzip der progressiven Überlastung bekannt ist. 
Sprich immer in der Ich-Form, sei motivierend und erkläre deine Entscheidungen, als würdest du mit einem Klienten sprechen.

Beginne deine Antwort immer mit einer kurzen, persönlichen Erklärung (2-3 Sätze), warum du diesen Plan erstellt hast.

**Dein persönlicher Trainingsplan**
[Hier deine Erklärung einfügen]

BENUTZERPROFIL:
{profile}

TRAININGSHISTORIE:
{history_analysis}

AKTUELLE WÜNSCHE DES NUTZERS:
{additional_info}

TRAININGSPARAMETER:
- Trainingstage pro Woche: {training_days}
- Split-Typ: {split_type}
- Fokus: {focus}

WICHTIGE FORMATIERUNGSREGELN:
1. Erstelle GENAU {training_days} Trainingstage.
2. Jeder Trainingstag MUSS mit einem Namen im Format **Workout Name:** beginnen.
3. Formatiere jede Übung EXAKT so: - Übungsname: X Sätze, Y Wdh, Z kg (Fokus: Kurzer Hinweis)
4. {weight_instruction}
"""
    return config

def parse_ai_plan_to_rows(plan_text, user_data_uuid, user_name):
    """Parses the AI-generated plan text into structured data for the database."""
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = "Unbenanntes Workout"
    plan_explanation = "" # Placeholder for explanation extraction

    lines = plan_text.split('\n')
    
    # Simple logic to find the explanation
    try:
        # Find the first bolded line after the intro as the start of the plan
        first_bold_index = -1
        for i, line in enumerate(lines):
            if line.startswith('**'):
                first_bold_index = i
                break
        if first_bold_index > 0:
            plan_explanation = "\n".join(lines[:first_bold_index]).strip()
        else:
            plan_explanation = "Milo hat diesen Plan speziell für dich erstellt."

    except ValueError:
        plan_explanation = "Milo hat diesen Plan speziell für dich erstellt."

    for line in lines:
        line = line.strip()
        if line.startswith('**'):
            match = re.match(r'\*\*(.*?):\*\*', line)
            if match:
                current_workout = match.group(1).strip()
        elif line.startswith('-'):
            exercise_match = re.match(r'^\s*[-*]\s*(.+?):\s*(.*)', line)
            if exercise_match:
                exercise_name = exercise_match.group(1).strip()
                details = exercise_match.group(2).strip()
                
                # Default values
                sets, weight, reps, explanation = 3, 0.0, "10", ""

                try:
                    # Extract details using regex - this is from your original code
                    sets_match = re.search(r'(\d+)\s*(?:x|[Ss]ätze|[Ss]ets)', details)
                    if sets_match: sets = int(sets_match.group(1))

                    weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                    if weight_match: weight = float(weight_match.group(1).replace(',', '.'))

                    reps_match = re.search(r'(\d+\s*-\s*\d+|\d+)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                    if reps_match: reps = reps_match.group(1).strip()

                    explanation_match = re.search(r'\((?:Fokus):\s*(.+)\)$', details)
                    if explanation_match: explanation = explanation_match.group(1).strip()

                    for i in range(1, sets + 1):
                        rows.append({
                            'uuid': user_data_uuid, 'date': current_date, 'name': user_name,
                            'workout': current_workout, 'exercise': exercise_name, 'set': i,
                            'weight': weight, 'reps': reps.split('-')[0] if '-' in str(reps) else reps,
                            'unit': 'kg', 'completed': False, 'messageFromCoach': explanation,
                        })
                except Exception as e:
                    st.warning(f"Konnte Zeile nicht verarbeiten: '{line}' ({e})")

    return rows, plan_explanation

# --- NEUE FUNKTION FÜR DEN INTERAKTIVEN CHAT ---
def get_chat_response(history):
    """
    Sendet den Chat-Verlauf an die KI und erhält eine kontextbezogene Antwort.

    Args:
        history (list): Eine Liste von Dictionaries, die den bisherigen Chat-Verlauf darstellt.
                        Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    Returns:
        str: Die Text-Antwort der KI.
    """
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden. Bitte prüfe den API-Key."

    # Der System-Prompt gibt der KI ihre Rolle und grundlegende Anweisungen für das gesamte Gespräch.
    system_prompt = {
        "role": "system",
        "content": """Du bist Milo, ein persönlicher KI-Coach. Deine Aufgabe ist es, mit dem Nutzer interaktiv einen Trainingsplan zu erstellen.
        1. Wenn der Nutzer zum ersten Mal nach einem Plan fragt, erstelle einen vollständigen Plan basierend auf seinen Wünschen und den bereitgestellten Profildaten (die in der ersten User-Nachricht enthalten sind).
        2. Wenn der Nutzer danach Änderungen vorschlägt (z.B. "ersetze Übung X" oder "füge einen Satz hinzu"), passe den **letzten Plan, den du gesendet hast**, entsprechend an und sende den **kompletten, aktualisierten Plan** zurück. Gib nicht nur die Änderung an, sondern immer den vollen Plan.
        3. Behalte immer deine freundliche, motivierende und kompetente Coach-Persönlichkeit bei. Erkläre kurz, warum du eine Änderung vorgenommen hast.
        4. Halte dich strikt an das Formatierungs-Schema für den Plan.
        """
    }
    
    messages_to_send = [system_prompt] + history

    try:
        response = ai_client.chat.completions.create(
            model="gpt-4o-mini",  # Wir können hier ein leistungsstarkes Modell festlegen
            messages=messages_to_send,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei der Kommunikation mit der KI: {e}")
        return "Es tut mir leid, es gab ein Problem bei der Verbindung zur KI. Bitte versuche es später erneut."
