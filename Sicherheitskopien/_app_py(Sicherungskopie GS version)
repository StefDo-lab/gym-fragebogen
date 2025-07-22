import streamlit as st
import datetime
import gspread
import pandas as pd
import numpy as np
from oauth2client.service_account import ServiceAccountCredentials
from string import Template
from openai import OpenAI
import json
import os
import re
import time

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"
ARCHIVE_SHEET = "Workout_archiv"
FRAGEBOGEN_SHEET = "fragebogen"
PLAN_HISTORY_SHEET = "Plan_Historie"
PROMPT_TEMPLATE_PATH = "prompt_templates/update_plan.txt"
SYSTEM_PROMPT_PATH = "prompt_templates/system_prompt.txt"

# ---- Google Sheets Setup ----
@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["gcp_service_account"], scopes
    )
    return gspread.authorize(creds)

@st.cache_resource
def get_worksheet(sheet_name, worksheet_name):
    """Cached worksheet getter - wird nur einmal geladen"""
    try:
        client = get_gspread_client()
        ss = client.open(sheet_name)
        return ss.worksheet(worksheet_name)
    except Exception as e:
        if "quota" in str(e).lower():
            return None
        raise e

# ---- OpenAI Setup ----
openai_key = st.secrets.get("openai_api_key", None)
if openai_key:
    client = OpenAI(api_key=openai_key)
else:
    client = None

# ---- Standard Templates ----
DEFAULT_PROMPT_TEMPLATE = """
Du bist ein professioneller Fitness-Trainer. Erstelle einen personalisierten Trainingsplan.

BENUTZERPROFIL:
- Fitnesslevel: ${Fitnesslevel}
- Ziele: ${Ziel}
- Verfügbare Tage: ${Verfügbare_Tage}
- Ausrüstung: ${Ausrüstung}

BISHERIGE LEISTUNGEN (letzte Workouts):
${workout_summary}

ZUSÄTZLICHE WÜNSCHE:
${additional_goals}

Erstelle einen Trainingsplan für die nächste Woche. Nutze alle verfügbaren Informationen bestmöglich.
"""

DEFAULT_SYSTEM_PROMPT = """Erstelle einen Wochenplan mit eindeutigen Workout-Namen. 

WICHTIG: Jedes Workout muss einen EINDEUTIGEN Namen haben!
Beispiele:
- "Oberkörper A" (nicht nur "Oberkörper")
- "Push Day 1" (nicht nur "Push Day")
- "Beine & Po - Schwer" (nicht nur "Beine")

Format:
Oberkörper A:
- Bankdrücken: 3 Sätze, 80kg, 8-10 Wdh
- Rudern: 3 Sätze, 60kg, 10-12 Wdh

Unterkörper A:
- Kniebeuge: 4 Sätze, 100kg, 6-8 Wdh
- Kreuzheben: 3 Sätze, 120kg, 5 Wdh

Regeln:
- Eindeutige Workout-Namen
- Realistische Gewichte
- 4-6 Übungen pro Workout
- Klare Satz/Wdh Angaben"""

# ---- Template Loader ----
@st.cache_data
def load_template(path: str, default: str):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            pass
    return default

@st.cache_data
def load_prompt_and_config():
    prompt_content = load_template(PROMPT_TEMPLATE_PATH, DEFAULT_PROMPT_TEMPLATE)
    system_content = load_template(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    return Template(prompt_content), system_content, {'temperature': 0.7, 'max_tokens': 2500}

prompt_template, system_prompt, prompt_config = load_prompt_and_config()

# ---- Hilfsfunktionen ----
def col_letter(col_num):
    """Konvertiert Spaltennummer zu Buchstaben"""
    letter = ''
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

@st.cache_data(ttl=300)  # Cache für 5 Minuten
def load_user_data(user_id):
    """Lädt nur Daten für einen spezifischen User - mit Cache"""
    try:
        worksheet = get_worksheet(SHEET_NAME, WORKSHEET_NAME)
        if not worksheet:
            return pd.DataFrame()
        
        # Hole Header
        header = worksheet.row_values(1)
        if not header:
            return pd.DataFrame()
        
        # Finde UserID Spalte
        try:
            uid_col = header.index("UserID") + 1
        except ValueError:
            st.error("UserID Spalte nicht gefunden")
            return pd.DataFrame()
        
        # Hole alle Zeilen mit dieser UserID
        all_values = worksheet.get_all_values()
        user_rows = []
        
        for i, row in enumerate(all_values[1:], 2):  # Skip header
            if len(row) >= uid_col and row[uid_col-1] == user_id:
                user_rows.append(row)
        
        if not user_rows:
            return pd.DataFrame()
        
        # Erstelle DataFrame
        df = pd.DataFrame(user_rows, columns=header)
        
        # Konvertiere Datentypen
        for col in ['Gewicht', 'Wdh', 'Satz-Nr.']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # Füge Index-Spalte für Referenz hinzu
        df['_row_index'] = range(len(user_rows))
        
        return df
        
    except Exception as e:
        if "quota" in str(e).lower():
            return None  # Signalisiert Quota-Error
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

def init_session_state():
    """Initialisiert Session State für lokale Änderungen"""
    if 'local_changes' not in st.session_state:
        st.session_state.local_changes = {}
    if 'unsaved_changes' not in st.session_state:
        st.session_state.unsaved_changes = False
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False

def track_change(row_id, field, value):
    """Speichert Änderungen lokal"""
    if row_id not in st.session_state.local_changes:
        st.session_state.local_changes[row_id] = {}
    st.session_state.local_changes[row_id][field] = value
    st.session_state.unsaved_changes = True

def get_value(row_id, field, default):
    """Holt Wert aus lokalen Änderungen oder Default"""
    if row_id in st.session_state.local_changes and field in st.session_state.local_changes[row_id]:
        return st.session_state.local_changes[row_id][field]
    return default

def save_all_changes(current_df):
    """Speichert alle lokalen Änderungen in einem Batch"""
    if not st.session_state.local_changes:
        return True
    
    try:
        worksheet = get_worksheet(SHEET_NAME, WORKSHEET_NAME)
        if not worksheet:
            st.error("Kann nicht auf Google Sheets zugreifen")
            return False
        
        batch_data = []
        header = current_df.columns.tolist()
        
        # Finde die tatsächlichen Zeilennummern
        all_values = worksheet.get_all_values()
        uid_col = header.index("UserID")
        
        # Erstelle Mapping von DataFrame Index zu Sheet Zeile
        row_mapping = {}
        sheet_row = 2  # Start nach Header
        for i, row in enumerate(all_values[1:]):
            if len(row) > uid_col and row[uid_col] == st.session_state.userid:
                if len(row_mapping) < len(current_df):
                    row_mapping[len(row_mapping)] = sheet_row
            sheet_row += 1
        
        for row_id, changes in st.session_state.local_changes.items():
            if row_id in row_mapping:
                sheet_row = row_mapping[row_id]
                
                for field, value in changes.items():
                    if field in header and field != '_row_index':
                        col_num = header.index(field) + 1
                        col_let = col_letter(col_num)
                        batch_data.append({
                            'range': f'{col_let}{sheet_row}',
                            'values': [[str(value)]]
                        })
        
        # Führe Batch Update aus
        if batch_data:
            # Teile in kleinere Batches auf
            for i in range(0, len(batch_data), 50):  # Kleinere Batches
                batch_chunk = batch_data[i:i+50]
                worksheet.batch_update(batch_chunk)
                time.sleep(1)  # Längere Pause
        
        # Clear lokale Änderungen
        st.session_state.local_changes = {}
        st.session_state.unsaved_changes = False
        return True
        
    except Exception as e:
        if "quota" in str(e).lower():
            st.error("⏳ API Limit erreicht. Bitte in 1 Minute erneut versuchen.")
        else:
            st.error(f"Fehler beim Speichern: {e}")
        return False

# ---- App UI ----
st.set_page_config(page_title="Workout Tracker", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS
st.markdown("""
<style>
    .stButton > button {
        width: 100%;
        padding: 0.25rem 0.5rem;
        font-size: 0.875rem;
    }
    .row-widget.stNumberInput {
        max-width: 100px;
    }
    .save-button {
        background-color: #28a745;
        color: white;
        font-weight: bold;
    }
    .unsaved-indicator {
        background-color: #ffc107;
        color: black;
        padding: 0.5rem;
        border-radius: 0.25rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

st.title("Workout Tracker")

# Session State initialisieren
init_session_state()

# Login
if 'userid' not in st.session_state:
    st.session_state.userid = None

if not st.session_state.userid:
    uid = st.text_input("UserID", type="password")
    
    if st.button("Login"):
        try:
            worksheet = get_worksheet(SHEET_NAME, WORKSHEET_NAME)
            if not worksheet:
                st.error("⏳ Google Sheets momentan nicht erreichbar. Bitte später versuchen.")
                st.stop()
            
            # Prüfe ob UserID existiert
            header = worksheet.row_values(1)
            uid_col = header.index("UserID") + 1
            
            # Hole nur die UserID Spalte
            user_ids = worksheet.col_values(uid_col)[1:]  # Skip header
            valid_ids = [id.strip() for id in user_ids if id.strip()]
            
            if uid.strip() in valid_ids:
                st.session_state.userid = uid.strip()
                st.success(f"Eingeloggt als {uid.strip()}")
                st.rerun()
            else:
                st.error("UserID nicht gefunden.")
                
        except Exception as e:
            if "quota" in str(e).lower():
                st.error("⏳ Google Sheets Limit erreicht. Bitte in 1 Minute erneut versuchen.")
            else:
                st.error(f"Login-Fehler: {e}")
    st.stop()

# ---- Hauptnavigation ----
tab1, tab2, tab3 = st.tabs(["Training", "Neuer Plan", "Historie"])

# ---- Tab 1: Aktueller Plan ----
with tab1:
    # Ungespeicherte Änderungen Indikator
    if st.session_state.unsaved_changes:
        st.markdown('<div class="unsaved-indicator">⚠️ Ungespeicherte Änderungen vorhanden!</div>', unsafe_allow_html=True)
    
    # Speichern Button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("💾 **Alle Änderungen speichern**", type="primary", disabled=not st.session_state.unsaved_changes):
            with st.spinner("Speichere Änderungen..."):
                current_df = load_user_data(st.session_state.userid)
                if current_df is not None and not current_df.empty:
                    if save_all_changes(current_df):
                        st.success("✅ Alle Änderungen gespeichert!")
                        load_user_data.clear()  # Cache leeren
                        time.sleep(1)
                        st.rerun()
    
    # Lade Daten
    current_df = load_user_data(st.session_state.userid)
    
    if current_df is None:
        st.error("⏳ Google Sheets Limit erreicht. Bitte warte 1 Minute und lade die Seite neu.")
        st.stop()
    
    if not current_df.empty:
        # Gruppiere nach Workout
        workouts = current_df['Workout Name'].unique() if 'Workout Name' in current_df.columns else []
        
        for workout in workouts:
            st.subheader(workout)
            workout_data = current_df[current_df['Workout Name'] == workout]
            
            # Gruppiere nach Übung
            exercises = workout_data['Übung'].unique() if 'Übung' in workout_data.columns else []
            
            for exercise in exercises:
                exercise_data = workout_data[workout_data['Übung'] == exercise].sort_values('Satz-Nr.')
                
                with st.expander(f"{exercise}"):
                    # Zeige alle Sätze
                    for idx, row in exercise_data.iterrows():
                        st.markdown("---")
                        
                        # Trainer-Hinweis
                        trainer_comment = row.get('Hinweis vom Trainer', '')
                        if trainer_comment and trainer_comment.strip():
                            st.info(f"💬 Trainer: {trainer_comment}")
                        
                        col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
                        
                        row_idx = row['_row_index']  # Verwende den stabilen Index
                        
                        with col1:
                            st.write(f"**Satz {int(row.get('Satz-Nr.', 1))}**")
                        
                        with col2:
                            current_weight = get_value(row_idx, 'Gewicht', float(row.get('Gewicht', 0)))
                            new_weight = st.number_input(
                                "Gewicht (kg)",
                                value=current_weight,
                                step=2.5,
                                key=f"weight_{row_idx}",
                                on_change=lambda idx=row_idx, f='Gewicht': track_change(idx, f, st.session_state[f"weight_{idx}"])
                            )
                        
                        with col3:
                            current_reps = get_value(row_idx, 'Wdh', int(row.get('Wdh', 0)))
                            new_reps = st.number_input(
                                "Wiederholungen",
                                value=current_reps,
                                step=1,
                                key=f"reps_{row_idx}",
                                on_change=lambda idx=row_idx, f='Wdh': track_change(idx, f, st.session_state[f"reps_{idx}"])
                            )
                        
                        with col4:
                            current_status = get_value(row_idx, 'Erledigt', str(row.get('Erledigt', 'FALSE')).upper())
                            
                            if current_status == 'TRUE':
                                if st.button("✓ Erledigt", key=f"status_{row_idx}", type="primary"):
                                    track_change(row_idx, 'Erledigt', 'FALSE')
                                    st.rerun()
                            else:
                                if st.button("Erledigt", key=f"status_{row_idx}"):
                                    track_change(row_idx, 'Erledigt', 'TRUE')
                                    track_change(row_idx, 'Gewicht', new_weight)
                                    track_change(row_idx, 'Wdh', new_reps)
                                    st.rerun()
                        
                        # Nachricht an Trainer
                        current_msg = get_value(row_idx, 'Mitteilung an den Trainer', row.get('Mitteilung an den Trainer', ''))
                        new_message = st.text_input(
                            "Nachricht an Trainer",
                            value=current_msg,
                            key=f"msg_{row_idx}",
                            placeholder="z.B. Schulter schmerzt leicht",
                            on_change=lambda idx=row_idx, f='Mitteilung an den Trainer': track_change(idx, f, st.session_state[f"msg_{idx}"])
                        )
        
        # Reminder am Ende
        if st.session_state.unsaved_changes:
            st.warning("⚠️ Vergiss nicht, deine Änderungen zu speichern!")
            
    else:
        st.info("Kein aktiver Trainingsplan. Erstelle einen neuen Plan im Tab 'Neuer Plan'!")

# ---- Tab 2: Neuen Plan erstellen ----
with tab2:
    st.header("Neuen Trainingsplan erstellen")
    
    if not client:
        st.error("OpenAI API Key fehlt. Bitte in Streamlit Secrets konfigurieren.")
        st.stop()
    
    additional_goals = st.text_area("Zusätzliche Ziele/Wünsche (optional)")
    plan_name = st.text_input("Plan-Name (optional)", placeholder="z.B. Woche 1 - Push/Pull")
    
    if st.button("Plan erstellen", type="primary"):
        with st.spinner("KI erstellt deinen Plan..."):
            try:
                # Template-Daten mit Defaults
                template_data = {
                    'workout_summary': "Keine historischen Daten",
                    'additional_goals': additional_goals or "Allgemeine Fitness",
                    'Fitnesslevel': 'Mittel',
                    'Ziel': 'Muskelaufbau',
                    'Verfügbare_Tage': '3',
                    'Ausrüstung': 'Fitnessstudio'
                }
                
                prompt = prompt_template.safe_substitute(template_data)
                
                # OpenAI API Aufruf
                response = client.chat.completions.create(
                    model='gpt-4o-mini',
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=prompt_config.get('temperature', 0.7),
                    max_tokens=prompt_config.get('max_tokens', 2500)
                )
                
                plan_text = response.choices[0].message.content
                
                # Plan anzeigen
                st.success("Plan wurde erstellt!")
                with st.expander("Plan-Vorschau", expanded=True):
                    st.text(plan_text)
                
                # TODO: Plan aktivieren implementieren
                
            except Exception as e:
                st.error(f"Fehler: {str(e)}")

# ---- Tab 3: Historie ----
with tab3:
    st.info("Historie-Funktion wird in der nächsten Version verfügbar sein.")

st.markdown("---")
st.caption("v4.1 - Optimiert für minimale API Requests mit besserem Error Handling")
