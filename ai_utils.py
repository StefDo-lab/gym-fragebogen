# ai_utils.py
# This file handles all interactions with the AI model (OpenAI).

import streamlit as st
import re
from openai import OpenAI
import datetime
import pandas as pd # NEUER IMPORT
from supabase_utils import load_workout_history # NEUER IMPORT

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

# --- NEUE FUNKTION ZUR ANALYSE DER HISTORIE ---
def analyze_workout_history(history_data: list):
    """Analysiert die Trainingshistorie und bereitet eine Textzusammenfassung und ein DataFrame auf."""
    if not history_data:
        return "Keine Trainingshistorie vorhanden.", pd.DataFrame()
    
    df = pd.DataFrame(history_data)
    
    # Datenbereinigung
    for col in ["weight", "reps", "rirdone"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    
    # Konvertiere 'time' aus der DB zu einem reinen Datum für die Gruppierung
    df['date'] = pd.to_datetime(df['time']).dt.date
    
    analysis_parts = []
    
    # 1. Allgemeine Statistiken
    total_workouts = df['date'].nunique()
    if total_workouts > 0:
        first_workout = df['date'].min()
        last_workout = df['date'].max()
        days_training = (last_workout - first_workout).days + 1
        # Verhindert eine Division durch Null, wenn nur ein Trainingstag existiert
        frequency = total_workouts / max(days_training / 7, 1) 
        
        analysis_parts.append(f"TRAININGSÜBERSICHT:")
        analysis_parts.append(f"- Trainingseinheiten gesamt: {total_workouts}")
        analysis_parts.append(f"- Zeitraum: {first_workout.strftime('%d.%m.%Y')} bis {last_workout.strftime('%d.%m.%Y')}")
        analysis_parts.append(f"- Durchschnittliche Frequenz: {frequency:.1f} Trainings/Woche\n")
    
    # 2. Übungsanalyse
    analysis_parts.append("ÜBUNGSFORTSCHRITTE:")
    exercises = df['exercise'].unique()
    
    for exercise in sorted(exercises):
        ex_data = df[df['exercise'] == exercise].sort_values('date')
        if ex_data.empty: continue

        last_weight = ex_data.iloc[-1]['weight']
        max_weight = ex_data['weight'].max()
        
        analysis_parts.append(f"- {exercise}: Aktuell bei {last_weight:.1f} kg (Max: {max_weight:.1f} kg)")
    
    summary = "\n".join(analysis_parts)
    return summary, df

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
        
        workout_title_match = re.match(r'^\s*\*+\s*(.*?)\s*\*+[:]?$', line)
        if workout_title_match:
            current_workout = workout_title_match.group(1).strip()
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

                reps_match = re.search(r'(\d+(?:-\d+)?)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match: reps_str_full = reps_match.group(1).strip()

                explanation_match = re.search(r'\((?:Fokus|Erklärung):\s*(.+)\)$', details)
                if explanation_match: explanation = explanation_match.group(1).strip()

                reps_for_db_match = re.search(r'\d+', reps_str_full)
                reps_for_db = int(reps_for_db_match.group(0)) if reps_for_db_match else 10
                
                full_coach_message = f"Ziel: {reps_str_full} Wdh. {explanation}".strip()

                for i in range(1, sets + 1):
                    rows.append({
                        'uuid': user_uuid, 'date': current_date, 'name': user_name,
                        'workout': current_workout, 'exercise': exercise_name, 'set': i, 
                        'weight': weight, 'reps': reps_for_db, 'unit': 'kg',
                        'completed': False, 
                        'messagetocoach': '',
                        'messagefromcoach': full_coach_message,
                        'rirdone': 0
                    })
            except Exception as e:
                st.warning(f"Konnte Zeile nicht verarbeiten: '{line}' ({e})")

    return rows

def get_chat_response(messages: list, user_profile: dict):
    """Builds the prompt from the template and chat history, then gets a response."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden."

    # --- NEU: Lade und analysiere die Trainingshistorie ---
    history_data = load_workout_history(user_profile.get('uuid'))
    history_summary, _ = analyze_workout_history(history_data)
    # --- ENDE NEU ---

    prompt_template = get_ai_prompt_template()
    
    dynamic_instruction = """
WICHTIGE ANWEISUNG FÜR DIESE ANTWORT:
1. Antworte zuerst in normaler Sprache auf die letzte Nachricht des Nutzers.
2. WENN du den Trainingsplan als Reaktion auf die Nutzeranfrage geändert hast, füge NACH deiner normalen Antwort den kompletten, aktualisierten Plan in einem <PLAN_UPDATE> Tag hinzu. Beispiel: <PLAN_UPDATE>...neuer Plan...</PLAN_UPDATE>
3. Der Plan im Tag MUSS vollständig sein und wieder TEIL 1 und TEIL 2 enthalten.
4. Wenn du nur eine Frage beantwortest (z.B. zur Ernährung) und den Plan NICHT änderst, füge den <PLAN_UPDATE> Tag NICHT hinzu.

Hier ist der bisherige Gesprächsverlauf:
"""
    
    chat_history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
    full_user_request = dynamic_instruction + chat_history_text
    
    system_prompt_content = prompt_template.format(
        profile=user_profile,
        history_analysis=history_summary, # HIER WIRD DIE ANALYSE EINGEFÜGT
        additional_info=full_user_request, 
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
    
    initial_prompt_text = "Hallo Milo, hier ist ein neuer Athlet. Bitte erstelle einen ersten, passenden Trainingsplan-Vorschlag basierend auf dem Profil. Begrüsse den Athleten freundlich und erkläre ihm kurz, warum der Plan so aufgebaut ist. Formatiere die Antwort vollständig mit TEIL 1 und TEIL 2."

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

def get_workout_feedback(analysis_text: str):
    """Generates a motivational feedback message based on the workout analysis."""
    if not ai_client:
        return "Super gemacht! Dein Workout wurde gespeichert."

    feedback_prompt = f"""
Ein Nutzer hat gerade sein Workout beendet. Hier ist eine Analyse seiner Leistung:
---
{analysis_text}
---
Deine Aufgabe: Gib ihm ein kurzes (2-3 Sätze), positives und motivierendes Feedback. Sprich ihn direkt an. Wenn neue Rekorde aufgestellt wurden, feiere das besonders. Wenn keine Rekorde dabei waren, lobe einfach den Fleiß.
"""

    try:
        response = ai_client.chat.completions.create(
            model="gpt-3.5-turbo", # Using a faster model for quick feedback
            messages=[{"role": "user", "content": feedback_prompt}],
            temperature=0.8
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei der Erstellung des Feedbacks: {e}")
        return "Starke Leistung! Dein Workout wurde erfolgreich gespeichert."
