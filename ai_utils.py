# ai_utils.py
# This file handles all interactions with the AI model (OpenAI).

import streamlit as st
import re
from openai import OpenAI
import datetime
import pandas as pd
from supabase_utils import load_workout_history, load_filtered_exercises # NEUER IMPORT
from dateutil.relativedelta import relativedelta

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

# --- Data Enrichment and Analysis ---

def enrich_user_profile(user_profile: dict) -> dict:
    """
    Calculates Age, BMI, and Lean Body Mass and adds them to the profile.
    """
    try:
        birthday = datetime.datetime.fromisoformat(user_profile.get("birthday", "")).date()
        today = datetime.date.today()
        age = relativedelta(today, birthday).years
        user_profile['age'] = age
    except (ValueError, TypeError):
        user_profile['age'] = "N/A"

    try:
        height_m = float(user_profile.get("height_cm", 0)) / 100
        weight_kg = float(user_profile.get("weight_kg", 0))
        if height_m > 0 and weight_kg > 0:
            bmi = round(weight_kg / (height_m ** 2), 1)
            user_profile['bmi'] = bmi
        else:
            user_profile['bmi'] = "N/A"
    except (ValueError, TypeError):
        user_profile['bmi'] = "N/A"

    try:
        bodyfat_perc = float(user_profile.get("bodyfat_percentage", 0))
        weight_kg = float(user_profile.get("weight_kg", 0))
        if bodyfat_perc > 0 and weight_kg > 0:
            fat_mass = weight_kg * (bodyfat_perc / 100)
            lean_body_mass = round(weight_kg - fat_mass, 1)
            user_profile['lean_body_mass_kg'] = lean_body_mass
        else:
            user_profile['lean_body_mass_kg'] = "N/A"
    except (ValueError, TypeError):
        user_profile['lean_body_mass_kg'] = "N/A"
        
    return user_profile

def analyze_workout_history(history_data: list):
    """Analysiert die Trainingshistorie und bereitet eine Textzusammenfassung und ein DataFrame auf."""
    if not history_data:
        return "Keine Trainingshistorie vorhanden.", pd.DataFrame()
    
    df = pd.DataFrame(history_data)
    
    for col in ["weight", "reps", "rirdone", "messagetocoach"]:
        if col in df.columns:
            if col in ["weight", "reps", "rirdone"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            if col == "messagetocoach":
                df[col] = df[col].fillna('')
    
    df['date'] = pd.to_datetime(df['time']).dt.date
    
    analysis_parts = []
    
    total_workouts = df['date'].nunique()
    if total_workouts > 0:
        first_workout = df['date'].min()
        last_workout = df['date'].max()
        days_training = (last_workout - first_workout).days + 1
        frequency = total_workouts / max(days_training / 7, 1) 
        
        analysis_parts.append(f"TRAININGSÜBERSICHT:")
        analysis_parts.append(f"- Trainingseinheiten gesamt: {total_workouts}")
        analysis_parts.append(f"- Zeitraum: {first_workout.strftime('%d.%m.%Y')} bis {last_workout.strftime('%d.%m.%Y')}")
        analysis_parts.append(f"- Durchschnittliche Frequenz: {frequency:.1f} Trainings/Woche\n")
    
    analysis_parts.append("ÜBUNGSFORTSCHRITTE:")
    exercises = df['exercise'].unique()
    
    for exercise in sorted(exercises):
        ex_data = df[df['exercise'] == exercise].sort_values('date')
        if ex_data.empty: continue

        last_weight = ex_data.iloc[-1]['weight']
        max_weight = ex_data['weight'].max()
        
        analysis_parts.append(f"- {exercise}: Aktuell bei {last_weight:.1f} kg (Max: {max_weight:.1f} kg)")

    messages_df = df[df['messagetocoach'].notna() & (df['messagetocoach'] != '')].copy()
    
    if not messages_df.empty:
        analysis_parts.append("\nFEEDBACK VOM ATHLETEN:")
        messages_df = messages_df.sort_values(by='date', ascending=False)
        unique_messages = messages_df.drop_duplicates(subset=['date', 'exercise', 'messagetocoach'])
        
        for _, row in unique_messages.iterrows():
            date_str = row['date'].strftime('%d.%m.%Y')
            exercise_name = row['exercise']
            message = row['messagetocoach']
            analysis_parts.append(f"- {date_str} ({exercise_name}): \"{message}\"")
    
    summary = "\n".join(analysis_parts)
    return summary, df

# --- NEUE HILFSFUNKTION ---
def format_exercises_for_milo(exercises: list) -> str:
    """Formats the filtered list of exercises into a simple text string for the AI prompt."""
    if not exercises:
        return "Keine passenden Übungen in der Datenbank gefunden."
    
    formatted_lines = []
    for ex in exercises:
        # Wir geben Milo die wichtigsten Infos an die Hand
        line = f"- Name: {ex['name']}, Muskelgruppe: {ex['muscle_group']}, Hinweise: {ex.get('notes_for_milo', 'Keine')}"
        formatted_lines.append(line)
        
    return "\n".join(formatted_lines)

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
    # ... (diese Funktion bleibt unverändert) ...
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = None 
    
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
        
        workout_title_match = re.match(r'^\s*\*+(.+?)\*+[:]?\s*$', line)
        is_exercise_line = re.search(r'(\d+)\s*(?:x|[Ss]ätze|[Ss]ets)', line)

        if workout_title_match and not is_exercise_line:
            cleaned_title = workout_title_match.group(1).strip()
            current_workout = cleaned_title
            continue

        if current_workout is None:
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

def get_chat_response(messages: list, user_profile: dict, plan_request_params: dict = None):
    """Builds the prompt from the template and chat history, then gets a response."""
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden."

    user_profile = enrich_user_profile(user_profile.copy())
    st.session_state.user_profile = user_profile

    history_data = load_workout_history(user_profile.get('uuid'))
    history_summary, _ = analyze_workout_history(history_data)

    # NEU: Lade die gefilterte Übungsliste und formatiere sie für die KI
    filtered_exercises = load_filtered_exercises(user_profile)
    available_exercises_text = format_exercises_for_milo(filtered_exercises)

    prompt_template = get_ai_prompt_template()
    
    if plan_request_params:
        comment = plan_request_params.get('comment', '')
        additional_info = f"Der Nutzer fordert einen neuen Plan mit den unten angegebenen Parametern an. Zusätzlicher Wunsch: '{comment}'" if comment else "Der Nutzer fordert einen neuen Plan mit den unten angegebenen Parametern an."
        training_days = plan_request_params.get('days')
        split_type = plan_request_params.get('split')
        focus = plan_request_params.get('focus')
    else:
        iterative_instruction = (
            "WICHTIGE ANWEISUNG FÜR DIESE ANTWORT:\n"
            "1. Antworte zuerst in normaler Sprache auf die letzte Nachricht des Nutzers.\n"
            "2. WENN du den Trainingsplan als Reaktion auf die Nutzeranfrage geändert hast, füge NACH deiner normalen Antwort den kompletten, aktualisierten Plan in einem `<PLAN_UPDATE>` Tag hinzu. Beispiel: `<PLAN_UPDATE>...neuer Plan...</PLAN_UPDATE>`\n"
            "3. Wenn du nur eine Frage beantwortest und den Plan NICHT änderst, füge den `<PLAN_UPDATE>` Tag NICHT hinzu.\n\n"
            "Hier ist der bisherige Gesprächsverlauf:\n"
        )
        chat_history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
        additional_info = iterative_instruction + chat_history_text
        
        training_days = user_profile.get('training_days_per_week', 3)
        split_type = "passend zum Profil"
        focus = user_profile.get('primary_goal', 'Muskelaufbau')

    # NEU: Der neue Platzhalter {available_exercises} wird gefüllt
    system_prompt_content = prompt_template.format(
        profile=user_profile,
        history_analysis=history_summary, 
        available_exercises=available_exercises_text, # HIER WIRD DIE ÜBUNGSLISTE EINGEFÜGT
        additional_info=additional_info, 
        training_days=training_days,
        split_type=split_type, 
        focus=focus,
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
    # ... (diese Funktion wird ebenfalls angepasst, um die Übungsliste zu nutzen) ...
    if not ai_client:
        return "Entschuldigung, ich kann mich gerade nicht mit meiner KI verbinden."
    
    user_profile = enrich_user_profile(user_profile.copy())
    st.session_state.user_profile = user_profile

    filtered_exercises = load_filtered_exercises(user_profile)
    available_exercises_text = format_exercises_for_milo(filtered_exercises)

    prompt_template = get_ai_prompt_template()
    
    initial_prompt_text = "Hallo Milo, hier ist ein neuer Athlet. Bitte erstelle einen ersten, passenden Trainingsplan-Vorschlag basierend auf dem Profil. Begrüsse den Athleten freundlich und erkläre ihm kurz, warum der Plan so aufgebaut ist. Formatiere die Antwort vollständig mit TEIL 1 und TEIL 2."

    system_prompt_content = prompt_template.format(
        profile=user_profile,
        history_analysis="Keine Trainingshistorie vorhanden, da der Nutzer neu ist.",
        available_exercises=available_exercises_text,
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
    # ... (diese Funktion bleibt unverändert) ...
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
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": feedback_prompt}],
            temperature=0.8
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Fehler bei der Erstellung des Feedbacks: {e}")
        return "Starke Leistung! Dein Workout wurde erfolgreich gespeichert."
