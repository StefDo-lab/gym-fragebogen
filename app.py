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
import traceback
# Füge am Anfang nach den Imports ein:
import time

# Ändere die open_sheets() Funktion:
def open_sheets():
    try:
        client = get_gspread_client()
        ss = client.open(SHEET_NAME)
        
        # Warte kurz zwischen Requests
        time.sleep(0.5)
        
        all_titles = [sh.title for sh in ss.worksheets()]
        sheets = {}
        
        # Nur die wichtigsten Sheets laden
        sheets['current_plan'] = ss.worksheet(WORKSHEET_NAME)
        
        # Andere Sheets lazy laden (nur wenn benötigt)
        sheets['archive'] = None
        sheets['fragebogen'] = None  
        sheets['plan_history'] = None
        
        return sheets, all_titles
        
    except Exception as e:
        if "quota" in str(e).lower():
            st.error("⏳ Google Sheets Limit erreicht. Bitte 1 Minute warten und Seite neu laden.")
            st.stop()
        else:
            raise e

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"  # Aktueller Plan
ARCHIVE_SHEET = "Workout_archiv"    # Historische Daten
FRAGEBOGEN_SHEET = "fragebogen"     # User-Profil
PLAN_HISTORY_SHEET = "Plan_Historie" # Alte Pläne
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

def open_sheets():
    client = get_gspread_client()
    ss = client.open(SHEET_NAME)
    
    all_titles = [sh.title for sh in ss.worksheets()]
    sheets = {}
    
    # Hauptsheet (aktueller Plan)
    try:
        sheets['current_plan'] = ss.worksheet(WORKSHEET_NAME)
    except Exception as e:
        raise RuntimeError(f"Hauptsheet '{WORKSHEET_NAME}' nicht gefunden. Verfügbare: {all_titles}")
    
    # Archiv Sheet
    try:
        sheets['archive'] = ss.worksheet(ARCHIVE_SHEET)
    except Exception:
        st.warning(f"Archiv-Sheet '{ARCHIVE_SHEET}' nicht gefunden.")
        sheets['archive'] = None
    
    # Fragebogen Sheet
    try:
        sheets['fragebogen'] = ss.worksheet(FRAGEBOGEN_SHEET)
    except Exception:
        sheets['fragebogen'] = ss.add_worksheet(title=FRAGEBOGEN_SHEET, rows=100, cols=10)
        sheets['fragebogen'].update('A1:H1', [['UserID', 'Ziel', 'Fitnesslevel', 'Verfügbare_Tage', 
                                               'Ausrüstung', 'Verletzungen', 'Präferenzen', 'Erstellt_am']])
        st.info("Fragebogen-Sheet wurde erstellt.")
    
    # Plan Historie Sheet
    try:
        sheets['plan_history'] = ss.worksheet(PLAN_HISTORY_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        sheets['plan_history'] = ss.add_worksheet(title=PLAN_HISTORY_SHEET, rows=100, cols=10)
        sheets['plan_history'].update('A1:D1', [['UserID', 'Datum', 'Plan_Name', 'Plan_Daten']])
        st.info("Plan-Historie Sheet wurde erstellt.")
    
    return sheets, all_titles

# Sheets initialisieren
try:
    worksheets, available_sheets = open_sheets()
    ws_current = worksheets['current_plan']
    ws_archive = worksheets['archive']
    ws_fragebogen = worksheets['fragebogen']
    ws_plan_history = worksheets['plan_history']
except Exception as e:
    st.error(f"Fehler beim Öffnen der Sheets: {e}")
    st.stop()

# ---- OpenAI Setup ----
def get_openai_key():
    # Versuche verschiedene Schreibweisen
    for key_name in ["openai_api_key", "OPENAI_API_KEY", "OpenAI_API_Key", "openai_key"]:
        if hasattr(st, 'secrets') and key_name in st.secrets:
            return st.secrets[key_name]
    
    # Fallback auf Umgebungsvariable
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    
    return None

openai_key = get_openai_key()

if not openai_key:
    st.warning("OpenAI API Key nicht in Secrets gefunden.")
    openai_key = st.text_input(
        "**API Key eingeben**", 
        type="password",
        key="openai_key_input"
    )
    if openai_key:
        st.info("Key wird nur für diese Sitzung verwendet.")

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

# ---- Prompt-Template laden ----
@st.cache_data
def load_prompt_and_config():
    prompt_content = load_template(PROMPT_TEMPLATE_PATH, DEFAULT_PROMPT_TEMPLATE)
    system_content = load_template(SYSTEM_PROMPT_PATH, DEFAULT_SYSTEM_PROMPT)
    
    # Erstelle Template-Dateien falls nicht vorhanden
    os.makedirs("prompt_templates", exist_ok=True)
    
    if not os.path.exists(PROMPT_TEMPLATE_PATH):
        with open(PROMPT_TEMPLATE_PATH, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_PROMPT_TEMPLATE)
    
    if not os.path.exists(SYSTEM_PROMPT_PATH):
        with open(SYSTEM_PROMPT_PATH, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_SYSTEM_PROMPT)
    
    return Template(prompt_content), system_content, {'temperature': 0.7, 'max_tokens': 2500}

prompt_template, system_prompt, prompt_config = load_prompt_and_config()

# ---- Hilfsfunktionen ----
def get_header_row(worksheet):
    try:
        all_values = worksheet.get_all_values()
        return all_values[0] if all_values else []
    except:
        return []

def col_letter(col_num):
    """Konvertiert Spaltennummer zu Buchstaben (1=A, 2=B, etc.)"""
    letter = ''
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        letter = chr(65 + remainder) + letter
    return letter

def analyze_workout_history(archive_df, user_id, days=30):
    """Analysiert die Workout-Historie und erstellt eine Zusammenfassung"""
    if archive_df.empty:
        return "Keine historischen Daten vorhanden."
    
    user_archive = archive_df[archive_df['UserID'].astype(str).str.strip() == str(user_id).strip()].copy()
    
    if 'Datum' in user_archive.columns:
        try:
            user_archive['Datum'] = pd.to_datetime(user_archive['Datum'])
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            user_archive = user_archive[user_archive['Datum'] >= cutoff_date]
        except:
            pass
    
    if user_archive.empty:
        return "Keine aktuellen Trainingsdaten vorhanden."
    
    summary = []
    if 'Übung' in user_archive.columns:
        exercise_counts = user_archive['Übung'].value_counts()
        
        for exercise in exercise_counts.index:
            ex_data = user_archive[user_archive['Übung'] == exercise]
            max_weight = ex_data['Gewicht'].max() if 'Gewicht' in ex_data.columns else 0
            avg_reps = ex_data['Wdh'].mean() if 'Wdh' in ex_data.columns else 0
            count = exercise_counts[exercise]
            summary.append(f"- {exercise}: Max {max_weight}kg, Ø {avg_reps:.0f} Wdh, {count}x")
    
    return "\n".join(summary)

def parse_ai_plan_to_rows(plan_text, user_id):
    """Konvertiert den KI-generierten Plan in Tabellenzeilen"""
    rows = []
    current_date = datetime.date.today()
    
    lines = plan_text.split('\n')
    current_workout = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Erkenne Workout-Namen
        if ':' in line and not line.startswith('-') and not line.startswith('•'):
            potential_workout = line.split(':')[0].strip()
            if len(potential_workout) < 50 and not any(char.isdigit() and 'kg' in line for char in line):
                current_workout = potential_workout
                continue
        
        # Erkenne Übungen
        if line.startswith('-') or line.startswith('•'):
            try:
                parts = line[1:].strip().split(':')
                if len(parts) >= 2:
                    exercise_name = parts[0].strip()
                    details = parts[1].strip()
                    
                    # Defaults
                    sets = 3
                    weight = 0
                    reps = "10"
                    
                    # Extrahiere Details mit Regex
                    sets_match = re.search(r'(\d+)\s*[Ss]ätze', details)
                    if sets_match:
                        sets = int(sets_match.group(1))
                    
                    weight_match = re.search(r'(\d+)\s*kg', details)
                    if weight_match:
                        weight = int(weight_match.group(1))
                    
                    reps_match = re.search(r'(\d+[-\d]*)\s*[Ww]dh', details)
                    if reps_match:
                        reps = reps_match.group(1)
                    
                    # Erstelle Zeilen für jeden Satz
                    for satz in range(1, sets + 1):
                        rows.append({
                            'UserID': user_id,
                            'Datum': current_date.isoformat(),
                            'Name': '',
                            'Workout Name': current_workout or f"Workout {len(rows)//10 + 1}",
                            'Übung': exercise_name,
                            'Satz-Nr.': satz,
                            'Gewicht': weight,
                            'Wdh': reps.split('-')[0] if '-' in str(reps) else reps,
                            'Einheit': 'kg',
                            'Typ': '',
                            'Erledigt': 'FALSE',
                            'Mitteilung an den Trainer': '',
                            'Hinweis vom Trainer': ''
                        })
            except:
                continue
    
    return rows

# ---- App UI ----
st.set_page_config(page_title="Workout Tracker", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS für mobile Optimierung
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
    [data-testid="metric-container"] {
        padding: 0.5rem;
    }
    .streamlit-expanderHeader {
        font-size: 1rem;
        padding: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("Workout Tracker")

# Login
if 'userid' not in st.session_state:
    st.session_state.userid = None

if not st.session_state.userid:
    uid = st.text_input("UserID", type="password")
    
    if st.button("Login"):
        header = get_header_row(ws_current)
        try:
            uid_col = header.index("UserID")
            all_values = ws_current.get_all_values()
            
            valid_ids = []
            for row in all_values[1:]:
                if len(row) > uid_col and row[uid_col]:
                    clean_id = str(row[uid_col]).strip()
                    if clean_id and clean_id not in valid_ids:
                        valid_ids.append(clean_id)
            
            clean_uid = uid.strip()
            
            if clean_uid in valid_ids:
                st.session_state.userid = clean_uid
                st.success(f"Eingeloggt als {clean_uid}")
                st.rerun()
            else:
                st.error(f"UserID '{clean_uid}' nicht gefunden.")
                
        except ValueError:
            st.error("Spalte 'UserID' nicht gefunden im Header.")
        except Exception as e:
            st.error(f"Login-Fehler: {e}")
    st.stop()

# ---- Hauptnavigation ----
tab1, tab2, tab3 = st.tabs(["Training", "Neuer Plan", "Historie"])

# ---- Tab 1: Aktueller Plan ----
with tab1:
    # Lade aktuelle Daten
    @st.cache_data(ttl=60)
    def load_current_plan():
        try:
            rec = ws_current.get_all_records()
            if not rec:
                return pd.DataFrame()
            df = pd.DataFrame(rec)
            
            for col in ["Gewicht", "Wdh", "Satz-Nr."]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            if 'UserID' in df.columns:
                df['UserID'] = df['UserID'].astype(str).str.strip()
            
            return df
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
            return pd.DataFrame()
    
    current_df = load_current_plan()
    
    if not current_df.empty:
        user_plan = current_df[current_df['UserID'] == st.session_state.userid.strip()]
        
        if not user_plan.empty:
            # Gruppiere nach Workout
            workouts = user_plan['Workout Name'].unique() if 'Workout Name' in user_plan.columns else []
            
            # Zeige Workouts
            for workout in workouts:
                st.subheader(workout)
                workout_data = user_plan[user_plan['Workout Name'] == workout]
                
                # Gruppiere nach Übung
                exercises = workout_data['Übung'].unique() if 'Übung' in workout_data.columns else []
                
                for exercise in exercises:
                    exercise_data = workout_data[workout_data['Übung'] == exercise].sort_values('Satz-Nr.')
                    
                    # Speichere Expander-Status
                    expander_key = f"expanded_{exercise}_{workout}"
                    if expander_key not in st.session_state:
                        st.session_state[expander_key] = False
                    
                    # Übung als Expander mit gespeichertem Status
                    with st.expander(f"{exercise}", expanded=st.session_state[expander_key]):
                        # Pin-Button um Expander offen zu halten
                        if st.button("📌 Offen halten" if not st.session_state[expander_key] else "📌 Schließen", 
                                    key=f"pin_{exercise}_{workout}"):
                            st.session_state[expander_key] = not st.session_state[expander_key]
                            st.rerun()
                        
                        # Zeige alle Sätze dieser Übung
                        for idx, row in exercise_data.iterrows():
                            st.markdown("---")
                            
                            # Trainer-Hinweis anzeigen wenn vorhanden
                            trainer_comment = row.get('Hinweis vom Trainer', '')
                            if trainer_comment and trainer_comment.strip():
                                st.info(f"💬 Trainer: {trainer_comment}")
                            
                            # Hauptzeile mit Inputs
                            col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 1, 0.5])
                            
                            with col1:
                                st.write(f"**Satz {int(row.get('Satz-Nr.', 1))}**")
                            
                            with col2:
                                new_weight = st.number_input(
                                    "Gewicht (kg)",
                                    value=float(row.get('Gewicht', 0)),
                                    step=2.5,
                                    key=f"weight_{idx}"
                                )
                            
                            with col3:
                                # Prüfe ob es Zeit oder Wiederholungen sind
                                einheit = row.get('Einheit', 'Wdh')
                                if einheit.lower() in ['sek', 'sec', 'min']:
                                    label = f"Zeit ({einheit})"
                                    step = 5 if einheit.lower() in ['sek', 'sec'] else 1
                                else:
                                    label = "Wiederholungen"
                                    step = 1
                                
                                new_reps = st.number_input(
                                    label,
                                    value=int(row.get('Wdh', 0)),
                                    step=step,
                                    key=f"reps_{idx}"
                                )
                            
                            with col4:
                                erledigt = str(row.get('Erledigt', 'FALSE')).upper()
                                if erledigt == 'TRUE':
                                    if st.button("✓ Erledigt", key=f"undo_{idx}", help="Als nicht erledigt markieren", type="primary"):
                                        row_num = idx + 2
                                        ws_current.update_cell(row_num, current_df.columns.get_loc('Erledigt') + 1, 'FALSE')
                                        st.cache_data.clear()
                                        st.rerun()
                                else:
                                    if st.button("Erledigt", key=f"done_{idx}"):
                                        row_num = idx + 2
                                        
                                        # Batch Update für bessere Performance
                                        try:
                                            batch_data = []
                                            
                                            # Gewicht Update
                                            gewicht_col = col_letter(current_df.columns.get_loc('Gewicht') + 1)
                                            batch_data.append({
                                                'range': f'{gewicht_col}{row_num}',
                                                'values': [[str(new_weight)]]
                                            })
                                            
                                            # Wiederholungen Update
                                            wdh_col = col_letter(current_df.columns.get_loc('Wdh') + 1)
                                            batch_data.append({
                                                'range': f'{wdh_col}{row_num}',
                                                'values': [[str(new_reps)]]
                                            })
                                            
                                            # Erledigt Update
                                            erledigt_col = col_letter(current_df.columns.get_loc('Erledigt') + 1)
                                            batch_data.append({
                                                'range': f'{erledigt_col}{row_num}',
                                                'values': [['TRUE']]
                                            })
                                            
                                            # Führe Batch Update aus
                                            ws_current.batch_update(batch_data)
                                            
                                            # Behalte Expander offen
                                            st.session_state[expander_key] = True
                                            
                                            st.cache_data.clear()
                                            st.rerun()
                                            
                                        except Exception as e:
                                            st.error(f"Update-Fehler: {e}")
                                            # Fallback auf einzelne Updates
                                            ws_current.update_cell(row_num, current_df.columns.get_loc('Gewicht') + 1, new_weight)
                                            ws_current.update_cell(row_num, current_df.columns.get_loc('Wdh') + 1, new_reps)
                                            ws_current.update_cell(row_num, current_df.columns.get_loc('Erledigt') + 1, 'TRUE')
                                            st.cache_data.clear()
                                            st.rerun()
                            
                            with col5:
                                if st.button("🗑️", key=f"del_set_{idx}", help="Satz löschen"):
                                    ws_current.delete_rows(idx + 2)
                                    st.cache_data.clear()
                                    st.rerun()
                            
                            # Nachricht an Trainer
                            user_message = row.get('Mitteilung an den Trainer', '')
                            new_message = st.text_input(
                                "Nachricht an Trainer",
                                value=user_message,
                                key=f"msg_{idx}",
                                placeholder="z.B. Schulter schmerzt leicht"
                            )
                            
                            # Speichere Nachricht wenn geändert
                            if new_message != user_message:
                                if st.button("💾 Nachricht speichern", key=f"save_msg_{idx}"):
                                    row_num = idx + 2
                                    msg_col = current_df.columns.get_loc('Mitteilung an den Trainer') + 1
                                    ws_current.update_cell(row_num, msg_col, new_message)
                                    st.success("Nachricht gespeichert!")
                                    st.cache_data.clear()
                                    st.rerun()
                        
                        # Optionen am Ende der Übung
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"+ Satz hinzufügen", key=f"add_set_{exercise}_{workout}"):
                                last_set = exercise_data.iloc[-1]
                                new_row = last_set.to_dict()
                                new_row['Satz-Nr.'] = int(last_set['Satz-Nr.']) + 1
                                new_row['Erledigt'] = 'FALSE'
                                
                                header = get_header_row(ws_current)
                                row_list = [''] * len(header)
                                for i, col in enumerate(header):
                                    if col in new_row:
                                        row_list[i] = str(new_row[col])
                                
                                ws_current.append_row(row_list)
                                st.cache_data.clear()
                                st.rerun()
                        
                        with col2:
                            if st.button(f"Übung löschen", key=f"del_ex_{exercise}_{workout}"):
                                for del_idx in sorted(exercise_data.index, reverse=True):
                                    ws_current.delete_rows(del_idx + 2)
                                st.cache_data.clear()
                                st.rerun()
            
            # Neue Übung hinzufügen
            st.markdown("---")
            with st.expander("+ Neue Übung hinzufügen"):
                new_exercise = st.text_input("Übungsname")
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_sets = st.number_input("Sätze", min_value=1, value=3)
                with col2:
                    new_weight = st.number_input("Gewicht (kg)", min_value=0.0, step=2.5)
                with col3:
                    new_reps = st.number_input("Wiederholungen", min_value=1, value=10)
                
                workout_for_new = st.selectbox("Zu Workout hinzufügen:", workouts)
                
                if st.button("Übung hinzufügen"):
                    if new_exercise:
                        header = get_header_row(ws_current)
                        for satz in range(1, new_sets + 1):
                            new_row = [''] * len(header)
                            for i, col_name in enumerate(header):
                                if col_name == 'UserID':
                                    new_row[i] = st.session_state.userid
                                elif col_name == 'Datum':
                                    new_row[i] = datetime.date.today().isoformat()
                                elif col_name == 'Workout Name':
                                    new_row[i] = workout_for_new
                                elif col_name == 'Übung':
                                    new_row[i] = new_exercise
                                elif col_name == 'Satz-Nr.':
                                    new_row[i] = str(satz)
                                elif col_name == 'Gewicht':
                                    new_row[i] = str(new_weight)
                                elif col_name == 'Wdh':
                                    new_row[i] = str(new_reps)
                                elif col_name == 'Erledigt':
                                    new_row[i] = 'FALSE'
                                elif col_name == 'Einheit':
                                    new_row[i] = 'kg'
                            ws_current.append_row(new_row)
                        st.success(f"'{new_exercise}' wurde hinzugefügt!")
                        st.cache_data.clear()
                        st.rerun()
        else:
            st.info("Kein aktiver Trainingsplan. Erstelle einen neuen Plan!")
    else:
        st.warning("Keine Daten gefunden.")

# ---- Tab 2: Neuen Plan erstellen ----
with tab2:
    st.header("Neuen Trainingsplan erstellen")
    
    if not client:
        st.error("OpenAI API Key fehlt. Bitte oben eingeben.")
        st.stop()
    
    # Lade Archivdaten
    archive_data = pd.DataFrame()
    if ws_archive:
        try:
            archive_records = ws_archive.get_all_records()
            if archive_records:
                archive_data = pd.DataFrame(archive_records)
                for col in ["Gewicht", "Wdh"]:
                    if col in archive_data.columns:
                        archive_data[col] = pd.to_numeric(archive_data[col], errors='coerce').fillna(0)
                if 'UserID' in archive_data.columns:
                    archive_data['UserID'] = archive_data['UserID'].astype(str).str.strip()
        except:
            pass
    
    # Zeige Historie
    if not archive_data.empty:
        with st.expander("Deine Trainingshistorie"):
            history_summary = analyze_workout_history(archive_data, st.session_state.userid)
            st.text(history_summary)
    
    additional_goals = st.text_area("Zusätzliche Ziele/Wünsche (optional)")
    plan_name = st.text_input("Plan-Name (optional)", placeholder="z.B. Woche 1 - Push/Pull")
    
    if st.button("Plan erstellen", type="primary"):
        with st.spinner("KI erstellt deinen Plan..."):
            try:
                # Hole Fragebogen-Daten
                fragebogen_data = {}
                if ws_fragebogen:
                    fb_records = ws_fragebogen.get_all_records()
                    user_profile = next((r for r in fb_records if str(r.get('UserID')).strip() == st.session_state.userid), {})
                    fragebogen_data = {k: v for k, v in user_profile.items() if k != 'UserID'}
                
                # Analysiere Historie
                workout_summary = analyze_workout_history(archive_data, st.session_state.userid) if not archive_data.empty else "Keine Daten"
                
                # Template-Daten
                template_data = {
                    'workout_summary': workout_summary,
                    'additional_goals': additional_goals or "Allgemeine Fitness",
                    'Fitnesslevel': fragebogen_data.get('Fitnesslevel', 'Mittel'),
                    'Ziel': fragebogen_data.get('Ziel', 'Muskelaufbau'),
                    'Verfügbare_Tage': fragebogen_data.get('Verfügbare_Tage', '3'),
                    'Ausrüstung': fragebogen_data.get('Ausrüstung', 'Fitnessstudio')
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
                
                # Speichere alten Plan
                if not current_df.empty:
                    old_plan_data = current_df[current_df['UserID'] == st.session_state.userid].to_dict('records')
                    if old_plan_data:
                        ws_plan_history.append_row([
                            st.session_state.userid,
                            datetime.date.today().isoformat(),
                            f"Alter Plan bis {datetime.date.today()}",
                            json.dumps(old_plan_data)
                        ])
                
                # Parse neuen Plan
                new_plan_rows = parse_ai_plan_to_rows(plan_text, st.session_state.userid)
                
                if new_plan_rows:
                    # Lösche alte Einträge
                    if not current_df.empty:
                        user_rows = current_df[current_df['UserID'] == st.session_state.userid].index
                        for idx in sorted(user_rows, reverse=True):
                            ws_current.delete_rows(idx + 2)
                    
                    # Füge neuen Plan ein
                    header = get_header_row(ws_current)
                    for row_data in new_plan_rows:
                        new_row = [''] * len(header)
                        for i, col_name in enumerate(header):
                            if col_name in row_data:
                                new_row[i] = str(row_data[col_name])
                        ws_current.append_row(new_row)
                    
                    # Speichere Plan-Text in Historie
                    ws_plan_history.append_row([
                        st.session_state.userid,
                        datetime.date.today().isoformat(),
                        plan_name or f"KI-Plan vom {datetime.date.today()}",
                        plan_text
                    ])
                    
                    st.success("Neuer Plan wurde aktiviert!")
                    st.cache_data.clear()
                    
                    with st.expander("Plan-Details"):
                        st.text(plan_text)
                    
                    st.rerun()
                else:
                    st.error("Konnte keinen Plan erstellen. Bitte versuche es erneut.")
                
            except Exception as e:
                st.error(f"Fehler: {str(e)}")
                if "quota" in str(e).lower():
                    st.error("API-Limit erreicht. Bitte später versuchen.")

# ---- Tab 3: Historie ----
with tab3:
    st.header("Plan-Historie")
    
    if ws_plan_history:
        history_records = ws_plan_history.get_all_records()
        user_history = [r for r in history_records if str(r.get('UserID')).strip() == st.session_state.userid]
        
        if user_history:
            user_history.sort(key=lambda x: x.get('Datum', ''), reverse=True)
            
            for plan in user_history[:10]:
                with st.expander(f"{plan.get('Plan_Name', 'Plan')} - {plan.get('Datum', '')}"):
                    plan_data = plan.get('Plan_Daten', '')
                    try:
                        if plan_data.startswith('[') or plan_data.startswith('{'):
                            data = json.loads(plan_data)
                            if isinstance(data, list):
                                exercises = {}
                                for item in data:
                                    ex_name = item.get('Übung', 'Unbekannt')
                                    if ex_name not in exercises:
                                        exercises[ex_name] = []
                                    exercises[ex_name].append(f"Satz {item.get('Satz-Nr.', '?')}: {item.get('Gewicht', 0)}kg x {item.get('Wdh', '?')}")
                                
                                for ex, sets in exercises.items():
                                    st.write(f"**{ex}**")
                                    for s in sets:
                                        st.write(f"  {s}")
                            else:
                                st.json(data)
                        else:
                            st.text(plan_data[:500] + "..." if len(plan_data) > 500 else plan_data)
                    except:
                        st.text(plan_data[:500] + "..." if len(plan_data) > 500 else plan_data)
        else:
            st.info("Noch keine Historie vorhanden.")

st.markdown("---")
st.caption("v3.3 - Optimiert für weniger API Requests")
