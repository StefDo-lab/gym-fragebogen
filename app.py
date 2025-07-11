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

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"  # Aktueller Plan
ARCHIVE_SHEET = "Workout_archiv"    # Historische Daten
FRAGEBOGEN_SHEET = "fragebogen"     # User-Profil
PLAN_HISTORY_SHEET = "Plan_Historie" # Alte Pläne (umbenennt von Aktualisierte_Pläne)
PROMPT_TEMPLATE_PATH = "prompt_templates/update_plan.txt"

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
    if "openai_api_key" in st.secrets:
        return st.secrets["openai_api_key"]
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    return None

openai_key = get_openai_key()

if not openai_key:
    openai_key = st.text_input(
        "**API Key fehlt** – bitte OpenAI API Key eingeben (wird nicht gespeichert)", 
        type="password",
        key="openai_key_input"
    )
    if openai_key:
        st.warning("Key nur temporär genutzt. Für Dauerbetrieb bitte in Secrets speichern.")
    else:
        st.error("OpenAI API Key nicht gefunden.")
        st.stop()

client = OpenAI(api_key=openai_key)

# ---- Standard Prompt Template ----
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

Erstelle einen progressiven 4-Wochen-Plan, der auf den bisherigen Leistungen aufbaut.
Berücksichtige die Regeneration und steigere die Intensität angemessen.
"""

# ---- Prompt-Template laden ----
@st.cache_data
def load_prompt_and_config(path: str):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Template(content), {'temperature': 0.7, 'max_tokens': 2000}
        except:
            pass
    return Template(DEFAULT_PROMPT_TEMPLATE), {'temperature': 0.7, 'max_tokens': 2000}

prompt_template, prompt_config = load_prompt_and_config(PROMPT_TEMPLATE_PATH)

# ---- Hilfsfunktionen ----
def get_header_row(worksheet):
    try:
        all_values = worksheet.get_all_values()
        return all_values[0] if all_values else []
    except:
        return []

def analyze_workout_history(archive_df, user_id, days=30):
    """Analysiert die Workout-Historie und erstellt eine Zusammenfassung"""
    if archive_df.empty:
        return "Keine historischen Daten vorhanden."
    
    # Filtere nach User und letzten X Tagen
    user_archive = archive_df[archive_df['UserID'] == user_id].copy()
    
    if 'Datum' in user_archive.columns:
        try:
            user_archive['Datum'] = pd.to_datetime(user_archive['Datum'])
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            user_archive = user_archive[user_archive['Datum'] >= cutoff_date]
        except:
            pass
    
    if user_archive.empty:
        return "Keine aktuellen Trainingsdaten vorhanden."
    
    # Erstelle Zusammenfassung
    summary = []
    
    # Gruppiere nach Übung und zeige Fortschritt
    if 'Übung' in user_archive.columns:
        for exercise in user_archive['Übung'].unique():
            ex_data = user_archive[user_archive['Übung'] == exercise]
            
            # Finde max Gewicht und durchschnittliche Wiederholungen
            max_weight = ex_data['Gewicht'].max() if 'Gewicht' in ex_data.columns else 0
            avg_reps = ex_data['Wdh'].mean() if 'Wdh' in ex_data.columns else 0
            count = len(ex_data)
            
            summary.append(f"- {exercise}: Max {max_weight}kg, Ø {avg_reps:.0f} Wdh, {count}x trainiert")
    
    return "\n".join(summary)

# ---- App UI ----
st.set_page_config(page_title="📋 Workout Tracker + KI Trainingsplaner", layout="wide")
st.title("📋 Workout Tracker + KI Trainingsplaner")

# Login
if 'userid' not in st.session_state:
    st.session_state.userid = None

uid = st.text_input("UserID", type="password")
if st.button("Login"):
    header = get_header_row(ws_current)
    try:
        uid_col = header.index("UserID") + 1
        all_values = ws_current.get_all_values()
        valid_ids = list(set([row[uid_col-1] for row in all_values[1:] if len(row) > uid_col-1 and row[uid_col-1]]))
        
        if uid in valid_ids:
            st.session_state.userid = uid
            st.success(f"Eingeloggt als {uid}")
            st.rerun()
        else:
            st.error("Ungültige UserID.")
    except Exception as e:
        st.error(f"Login-Fehler: {e}")

if not st.session_state.userid:
    st.stop()

# ---- Hauptnavigation ----
tab1, tab2, tab3, tab4 = st.tabs(["📊 Aktueller Plan", "🤖 Neuen Plan erstellen", "📚 Plan-Historie", "📈 Statistiken"])

# ---- Tab 1: Aktueller Plan ----
with tab1:
    st.header("Dein aktueller Trainingsplan")
    
    # Lade aktuelle Daten
    @st.cache_data(ttl=300)
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
                df['UserID'] = df['UserID'].astype(str)
            
            return df
        except:
            return pd.DataFrame()
    
    current_df = load_current_plan()
    
    if not current_df.empty:
        user_plan = current_df[current_df['UserID'] == st.session_state.userid]
        
        if not user_plan.empty:
            # Gruppiere nach Workout
            workouts = user_plan['Workout Name'].unique() if 'Workout Name' in user_plan.columns else []
            
            for workout in workouts:
                with st.expander(f"💪 {workout}", expanded=True):
                    workout_data = user_plan[user_plan['Workout Name'] == workout]
                    
                    # Zeige Übungen
                    exercises = workout_data['Übung'].unique() if 'Übung' in workout_data.columns else []
                    
                    for exercise in exercises:
                        st.subheader(f"🏋️ {exercise}")
                        exercise_data = workout_data[workout_data['Übung'] == exercise]
                        
                        # Zeige Sätze in Spalten
                        cols = st.columns(len(exercise_data))
                        for idx, (_, row) in enumerate(exercise_data.iterrows()):
                            with cols[idx]:
                                satz_nr = int(row.get('Satz-Nr.', idx+1))
                                gewicht = row.get('Gewicht', 0)
                                wdh = int(row.get('Wdh', 0))
                                erledigt = row.get('Erledigt', False)
                                
                                st.metric(f"Satz {satz_nr}", f"{gewicht}kg x {wdh}")
                                
                                if erledigt in [True, 'TRUE', 'true', 1]:
                                    st.success("✅ Erledigt")
                                else:
                                    if st.button("Als erledigt markieren", key=f"done_{row.name}"):
                                        # Update im Sheet
                                        row_num = row.name + 2  # +2 wegen Header und 0-Index
                                        col_num = current_df.columns.get_loc('Erledigt') + 1
                                        ws_current.update_cell(row_num, col_num, 'TRUE')
                                        st.cache_data.clear()
                                        st.rerun()
        else:
            st.info("Kein aktiver Trainingsplan gefunden. Erstelle einen neuen Plan im nächsten Tab!")
    else:
        st.warning("Keine Daten im aktuellen Plan gefunden.")

# ---- Tab 2: Neuen Plan erstellen ----
with tab2:
    st.header("🤖 KI-gestützten Trainingsplan erstellen")
    
    # Lade Archivdaten für Analyse
    archive_data = pd.DataFrame()
    if ws_archive:
        try:
            archive_records = ws_archive.get_all_records()
            if archive_records:
                archive_data = pd.DataFrame(archive_records)
                for col in ["Gewicht", "Wdh"]:
                    if col in archive_data.columns:
                        archive_data[col] = pd.to_numeric(archive_data[col], errors='coerce').fillna(0)
        except:
            st.warning("Konnte Archivdaten nicht laden.")
    
    # Zeige Workout-Historie
    if not archive_data.empty:
        with st.expander("📊 Deine Trainingshistorie (letzte 30 Tage)"):
            history_summary = analyze_workout_history(archive_data, st.session_state.userid)
            st.text(history_summary)
    
    # Zusätzliche Ziele
    additional_goals = st.text_area(
        "Zusätzliche Ziele/Wünsche", 
        placeholder="z.B. Fokus auf Oberkörper, mehr Ausdauer, Vorbereitung für Wettkampf...",
        height=100
    )
    
    # Plan-Name
    plan_name = st.text_input("Plan-Name (optional)", placeholder="z.B. Sommer-Shred 2024")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚀 Neuen Plan erstellen", type="primary"):
            with st.spinner("KI erstellt deinen personalisierten Trainingsplan..."):
                try:
                    # Hole Benutzerprofil aus Fragebogen
                    fragebogen_data = {}
                    if ws_fragebogen:
                        fb_records = ws_fragebogen.get_all_records()
                        user_profile = next((r for r in fb_records if r.get('UserID') == st.session_state.userid), {})
                        fragebogen_data = {k: v for k, v in user_profile.items() if k != 'UserID'}
                    
                    # Analysiere Workout-Historie
                    workout_summary = analyze_workout_history(archive_data, st.session_state.userid) if not archive_data.empty else "Keine Daten"
                    
                    # Daten für Template
                    template_data = {
                        'workout_summary': workout_summary,
                        'additional_goals': additional_goals or "Allgemeine Fitness verbessern",
                        'Fitnesslevel': fragebogen_data.get('Fitnesslevel', 'Unbekannt'),
                        'Ziel': fragebogen_data.get('Ziel', 'Unbekannt'),
                        'Verfügbare_Tage': fragebogen_data.get('Verfügbare_Tage', 'Unbekannt'),
                        'Ausrüstung': fragebogen_data.get('Ausrüstung', 'Unbekannt')
                    }
                    
                    # Prompt erstellen
                    prompt = prompt_template.safe_substitute(template_data)
                    
                    # System Prompt für strukturierte Ausgabe
                    system_prompt = """Du bist ein professioneller Fitness-Trainer. 
Erstelle einen detaillierten 4-Wochen-Trainingsplan.

WICHTIG: Strukturiere den Plan so, dass er direkt in eine Tabelle übertragen werden kann.
Jede Zeile sollte eine Übung sein mit: Workout Name, Übung, Satz-Nr., Gewicht (Vorschlag), Wiederholungen

Beispiel-Format:
Woche 1 - Tag 1 - Push Day:
- Bankdrücken: 3 Sätze, 60kg, 8-10 Wdh
- Schulterdrücken: 3 Sätze, 30kg, 10-12 Wdh

Erstelle einen kompletten Plan für 4 Wochen mit progressiver Steigerung."""
                    
                    # OpenAI API Aufruf
                    response = client.chat.completions.create(
                        model='gpt-4o-mini',
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=prompt_config.get('temperature', 0.7),
                        max_tokens=prompt_config.get('max_tokens', 2000)
                    )
                    
                    plan_text = response.choices[0].message.content
                    
                    # Speichere alten Plan in Historie
                    if not current_df.empty:
                        old_plan_data = current_df[current_df['UserID'] == st.session_state.userid].to_dict('records')
                        if old_plan_data:
                            ws_plan_history.append_row([
                                st.session_state.userid,
                                datetime.date.today().isoformat(),
                                f"Alter Plan bis {datetime.date.today()}",
                                json.dumps(old_plan_data)
                            ])
                    
                    # Parse den neuen Plan und konvertiere in Tabellenformat
                    new_plan_rows = parse_ai_plan_to_rows(plan_text, st.session_state.userid)
                    
                    if new_plan_rows:
                        # Lösche alte Einträge des Users aus aktuellem Plan
                        if not current_df.empty:
                            user_rows = current_df[current_df['UserID'] == st.session_state.userid].index
                            for idx in sorted(user_rows, reverse=True):
                                ws_current.delete_rows(idx + 2)  # +2 wegen Header und 0-Index
                        
                        # Füge neuen Plan ein
                        header = get_header_row(ws_current)
                        for row_data in new_plan_rows:
                            new_row = [''] * len(header)
                            for i, col_name in enumerate(header):
                                if col_name in row_data:
                                    new_row[i] = str(row_data[col_name])
                            ws_current.append_row(new_row)
                        
                        # Speichere Plan auch in Historie
                        ws_plan_history.append_row([
                            st.session_state.userid,
                            datetime.date.today().isoformat(),
                            plan_name or f"KI-Plan vom {datetime.date.today()}",
                            plan_text
                        ])
                        
                        st.success("✅ Neuer Trainingsplan wurde erstellt und aktiviert!")
                        st.cache_data.clear()
                        
                        # Zeige Plan-Vorschau
                        with st.expander("📋 Plan-Details", expanded=True):
                            st.text(plan_text)
                        
                        st.rerun()
                    else:
                        st.error("Konnte Plan nicht verarbeiten.")
                        with st.expander("Roher Plan-Text"):
                            st.text(plan_text)
                    
                except Exception as e:
                    st.error(f"Fehler: {str(e)}")
                    st.code(traceback.format_exc())
    
    with col2:
        st.info("Der neue Plan ersetzt deinen aktuellen Plan. Der alte Plan wird in der Historie gespeichert.")

# ---- Tab 3: Plan-Historie ----
with tab3:
    st.header("📚 Deine Plan-Historie")
    
    if ws_plan_history:
        history_records = ws_plan_history.get_all_records()
        user_history = [r for r in history_records if r.get('UserID') == st.session_state.userid]
        
        if user_history:
            # Sortiere nach Datum (neueste zuerst)
            user_history.sort(key=lambda x: x.get('Datum', ''), reverse=True)
            
            for plan in user_history:
                with st.expander(f"📅 {plan.get('Plan_Name', 'Unbenannt')} - {plan.get('Datum', '')}"):
                    plan_data = plan.get('Plan_Daten', '')
                    
                    # Wenn es JSON ist, zeige strukturiert
                    try:
                        if plan_data.startswith('[') or plan_data.startswith('{'):
                            data = json.loads(plan_data)
                            st.json(data)
                        else:
                            st.text(plan_data)
                    except:
                        st.text(plan_data)
                    
                    # Option zum Wiederherstellen
                    if st.button(f"Plan wiederherstellen", key=f"restore_{plan.get('Datum')}"):
                        st.info("Diese Funktion kommt bald!")
        else:
            st.info("Noch keine Plan-Historie vorhanden.")

# ---- Tab 4: Statistiken ----
with tab4:
    st.header("📈 Deine Trainingsstatistiken")
    
    if not archive_data.empty:
        user_archive = archive_data[archive_data['UserID'] == st.session_state.userid]
        
        if not user_archive.empty:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_workouts = len(user_archive)
                st.metric("Gesamt Workouts", total_workouts)
            
            with col2:
                if 'Gewicht' in user_archive.columns:
                    total_weight = user_archive['Gewicht'].sum()
                    st.metric("Gesamt bewegt (kg)", f"{total_weight:,.0f}")
            
            with col3:
                unique_exercises = user_archive['Übung'].nunique() if 'Übung' in user_archive.columns else 0
                st.metric("Verschiedene Übungen", unique_exercises)
            
            # Fortschritts-Chart
            if 'Übung' in user_archive.columns and 'Datum' in user_archive.columns:
                st.subheader("Gewichtsprogression")
                
                # Wähle Übung
                exercises = user_archive['Übung'].unique()
                selected_exercise = st.selectbox("Wähle eine Übung:", exercises)
                
                if selected_exercise:
                    exercise_data = user_archive[user_archive['Übung'] == selected_exercise].copy()
                    if 'Gewicht' in exercise_data.columns:
                        try:
                            exercise_data['Datum'] = pd.to_datetime(exercise_data['Datum'])
                            exercise_data = exercise_data.sort_values('Datum')
                            
                            # Gruppiere nach Datum und nimm Max-Gewicht
                            daily_max = exercise_data.groupby('Datum')['Gewicht'].max().reset_index()
                            
                            st.line_chart(daily_max.set_index('Datum'))
                        except:
                            st.warning("Konnte Fortschritt nicht darstellen.")
    else:
        st.info("Noch keine Trainingsdaten vorhanden.")

# ---- Hilfsfunktion zum Parsen des KI-Plans ----
def parse_ai_plan_to_rows(plan_text, user_id):
    """Konvertiert den KI-generierten Plan in Tabellenzeilen"""
    rows = []
    current_date = datetime.date.today()
    
    # Einfacher Parser - kann je nach KI-Output angepasst werden
    lines = plan_text.split('\n')
    current_workout = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Erkenne Workout-Namen (z.B. "Tag 1 - Push Day:")
        if 'Tag' in line and ':' in line:
            current_workout = line.split(':')[0].strip()
            continue
        
        # Erkenne Übungen (z.B. "- Bankdrücken: 3 Sätze, 60kg, 8-10 Wdh")
        if line.startswith('-') or line.startswith('•'):
            try:
                # Parse Übungszeile
                parts = line[1:].strip().split(':')
                if len(parts) >= 2:
                    exercise_name = parts[0].strip()
                    details = parts[1].strip()
                    
                    # Extrahiere Sätze, Gewicht und Wiederholungen
                    sets = 3  # Default
                    weight = 0
                    reps = "10"
                    
                    # Suche nach Zahlen
                    import re
                    
                    # Sätze
                    sets_match = re.search(r'(\d+)\s*[Ss]ätze', details)
                    if sets_match:
                        sets = int(sets_match.group(1))
                    
                    # Gewicht
                    weight_match = re.search(r'(\d+)\s*kg', details)
                    if weight_match:
                        weight = int(weight_match.group(1))
                    
                    # Wiederholungen
                    reps_match = re.search(r'(\d+[-\d]*)\s*[Ww]dh', details)
                    if reps_match:
                        reps = reps_match.group(1)
                    
                    # Erstelle Zeilen für jeden Satz
                    for satz in range(1, sets + 1):
                        rows.append({
                            'UserID': user_id,
                            'Datum': current_date.isoformat(),
                            'Workout Name': current_workout or f"Workout {len(rows)//10 + 1}",
                            'Übung': exercise_name,
                            'Satz-Nr.': satz,
                            'Gewicht': weight,
                            'Wdh': reps.split('-')[0] if '-' in str(reps) else reps,
                            'Erledigt': 'FALSE',
                            'Status': 'aktiv'
                        })
            except:
                continue
    
    return rows

st.markdown("---")
st.caption("Workout Tracker v3.0 - KI-gestützte Trainingsplanung")