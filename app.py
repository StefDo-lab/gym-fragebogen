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
WORKSHEET_NAME = "Tabellenblatt1"
PROMPT_TEMPLATE_PATH = "prompt_templates/update_plan.txt"
UPDATED_PLANS_SHEET = "Aktualisierte_Pläne"

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
    
    # Hole alle Sheet-Namen zur Diagnose
    all_titles = [sh.title for sh in ss.worksheets()]
    
    sheets = {}
    
    # Tracker Sheet
    try:
        sheets['tracker'] = ss.worksheet(WORKSHEET_NAME)
        # Teste sofort, ob das Sheet funktioniert
        test = sheets['tracker'].cell(1, 1).value  # Safer als row_values
    except Exception as e:
        raise RuntimeError(f"Tracker-Sheet '{WORKSHEET_NAME}' Fehler: {e}. Verfügbare: {all_titles}")
    
    # Fragebogen Sheet
    try:
        sheets['fragebogen'] = ss.worksheet("fragebogen")
    except Exception:
        raise RuntimeError(f"Fragebogen-Sheet 'fragebogen' nicht gefunden. Verfügbare: {all_titles}")
    
    # Updated Plans Sheet
    try:
        sheets['updated'] = ss.worksheet(UPDATED_PLANS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        sheets['updated'] = ss.add_worksheet(
            title=UPDATED_PLANS_SHEET, rows=100, cols=10
        )
        sheets['updated'].update('A1:C1', [['UserID', 'Datum', 'PlanJSON']])
    
    return sheets, all_titles

# Sheets initialisieren
try:
    worksheets, available_sheets = open_sheets()
    ws = worksheets['tracker']
    updated_ws = worksheets['updated']
    fragebogen_ws = worksheets['fragebogen']
except Exception as e:
    st.error(f"Fehler beim Öffnen der Sheets: {e}")
    st.stop()

# ---- OpenAI Setup ----
def get_openai_key():
    # 1. Versuche aus Streamlit Secrets
    if "openai_api_key" in st.secrets:
        return st.secrets["openai_api_key"]
    
    # 2. Versuche aus Umgebungsvariable
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    
    # 3. Fallback: Manuelle Eingabe
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
        st.error(
            "OpenAI API Key nicht gefunden. Bitte openai_api_key in Secrets setzen oder Umgebungsvariable OPENAI_API_KEY einrichten."
        )
        st.stop()

# OpenAI Client initialisieren
client = OpenAI(api_key=openai_key)

# ---- Prompt-Template laden mit Konfiguration ----
@st.cache_data
def load_prompt_and_config(path: str):
    if not os.path.exists(path):
        st.warning(f"Prompt-Template nicht gefunden: {path}. Verwende Standard-Template.")
        default = "Nutze folgende Daten, um einen Trainingsplan zu erstellen: ${workout_list}"
        return Template(default), {'temperature': 0.7, 'max_tokens': 1500}
    
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse Konfiguration aus Kommentaren
    lines = content.splitlines()
    config = {'temperature': 0.7, 'max_tokens': 1500}  # Defaults
    template_lines = []
    
    for line in lines:
        if line.startswith('#') and ':' in line:
            # Versuche Konfiguration zu parsen
            try:
                key, val = line[1:].split(':', 1)
                key = key.strip()
                val = val.strip()
                if key == 'temperature':
                    config['temperature'] = float(val)
                elif key == 'max_tokens':
                    config['max_tokens'] = int(val)
            except:
                template_lines.append(line)
        else:
            template_lines.append(line)
    
    template_text = "\n".join(template_lines)
    return Template(template_text), config

prompt_template, prompt_config = load_prompt_and_config(PROMPT_TEMPLATE_PATH)

# ---- Hilfsfunktionen ----
def get_header_row(worksheet):
    """Sicherer Zugriff auf Header-Zeile"""
    try:
        # Methode 1: get_all_values und erste Zeile
        all_values = worksheet.get_all_values()
        if all_values:
            return all_values[0]
        else:
            return []
    except Exception as e:
        st.error(f"Fehler beim Lesen der Header-Zeile: {e}")
        return []

# ---- App UI ----
st.set_page_config(page_title="📋 Workout Tracker + Plan-Update", layout="wide")
st.title("📋 Workout Tracker (Google Sheets)")

# Debug: Liste alle Tabellenblätter
with st.expander("📄 Verfügbare Tabellenblätter", expanded=False):
    st.write(available_sheets)

# Login / UserID
if 'userid' not in st.session_state:
    st.session_state.userid = None

uid = st.text_input("UserID", type="password")
if st.button("Login"):
    header = get_header_row(ws)
    if not header:
        st.error("Konnte Header nicht lesen")
        st.stop()
    
    try:
        uid_col = header.index("UserID") + 1
        all_values = ws.get_all_values()
        valid_ids = [row[uid_col-1] for row in all_values[1:] if len(row) > uid_col-1]
    except ValueError:
        st.error("Spalte 'UserID' nicht gefunden.")
    except Exception as e:
        st.error(f"Fehler beim Login: {e}")
    else:
        if uid in valid_ids:
            st.session_state.userid = uid
            st.success(f"Eingeloggt als {uid}")
            st.rerun()
        else:
            st.error("Ungültige UserID.")

if not st.session_state.userid:
    st.stop()

# Daten laden
@st.cache_data(ttl=300)  # 5 Minuten Cache
def load_data():
    try:
        rec = ws.get_all_records()
        if not rec:
            return pd.DataFrame()
        df = pd.DataFrame(rec)
        
        # Datentypen konvertieren
        for col in ["Gewicht", "Wdh"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        if 'UserID' in df.columns:
            df['UserID'] = df['UserID'].astype(str)
        
        return df
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.warning("Keine Daten gefunden.")
    user_df = pd.DataFrame()
else:
    user_df = df[df['UserID'] == st.session_state.userid]

# ---- Alte Workouts ----
with st.expander("Alte Workouts", expanded=False):
    if not user_df.empty and "Workout Name" in user_df.columns:
        workouts = user_df["Workout Name"].dropna().unique()
        for workout in workouts:
            with st.expander(f"Workout: {workout}"):
                workout_df = user_df[user_df["Workout Name"] == workout]
                if "Übung" in workout_df.columns:
                    exercises = workout_df["Übung"].dropna().unique()
                    for ex in exercises:
                        with st.expander(f"Übung: {ex}"):
                            ex_df = workout_df[workout_df["Übung"] == ex]
                            if "Satz-Nr." in ex_df.columns:
                                ex_df = ex_df.sort_values("Satz-Nr.")
                            
                            for idx, row in ex_df.iterrows():
                                # Zeige Satz-Info
                                satz_nr = int(row.get('Satz-Nr.', 0)) if pd.notna(row.get('Satz-Nr.')) else 0
                                gewicht = row.get('Gewicht', 0)
                                wdh = int(row.get('Wdh', 0)) if pd.notna(row.get('Wdh')) else 0
                                
                                st.write(f"Satz {satz_nr}: {gewicht}kg x {wdh}")
                                
                                cols = st.columns([2, 2, 1, 1])
                                new_w = cols[0].number_input(
                                    "Gewicht", 
                                    value=float(gewicht), 
                                    step=0.25, 
                                    key=f"w_{idx}"
                                )
                                new_r = cols[1].number_input(
                                    "Wdh", 
                                    value=int(wdh), 
                                    key=f"r_{idx}"
                                )
                                
                                if cols[2].button("✔ Erledigt", key=f"done_{idx}"):
                                    try:
                                        # Finde die richtige Zeile im Sheet (idx + 2 wegen Header)
                                        row_num = idx + 2
                                        
                                        # Update Gewicht
                                        if 'Gewicht' in df.columns:
                                            col_num = df.columns.get_loc('Gewicht') + 1
                                            ws.update_cell(row_num, col_num, new_w)
                                        
                                        # Update Wiederholungen
                                        if 'Wdh' in df.columns:
                                            col_num = df.columns.get_loc('Wdh') + 1
                                            ws.update_cell(row_num, col_num, new_r)
                                        
                                        # Update Erledigt Status
                                        if 'Erledigt' in df.columns:
                                            col_num = df.columns.get_loc('Erledigt') + 1
                                            ws.update_cell(row_num, col_num, True)
                                        
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Fehler beim Aktualisieren: {e}")
                                
                                if cols[3].button("Löschen", key=f"del_{idx}"):
                                    try:
                                        ws.delete_rows(idx + 2)
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Fehler beim Löschen: {e}")
    else:
        st.info("Keine Workouts gefunden.")

# ---- Trainingsplan aktualisieren ----
st.header("Trainingsplan aktualisieren")
additional_goals = st.text_area("Zusätzliche Ziele/Wünsche (optional)")

col1, col2 = st.columns(2)

if col1.button("Sofort ausführen"):
    with st.spinner("Erstelle Trainingsplan..."):
        try:
            # Debug: Zeige ob API Key vorhanden
            st.write(f"API Key vorhanden: {'Ja' if openai_key else 'Nein'}")
            st.write(f"API Key Länge: {len(openai_key) if openai_key else 0}")
            
            # Hole archivierte Workouts
            all_rec = ws.get_all_records()
            archived = [
                r for r in all_rec 
                if r.get('Status') == 'archiviert' and r.get('UserID') == st.session_state.userid
            ]
            
            # Debug: Zeige Anzahl archivierter Workouts
            st.write(f"Gefundene archivierte Workouts: {len(archived)}")
            
            # Wenn keine archivierten Workouts, zeige Warnung
            if not archived:
                st.warning("Keine archivierten Workouts gefunden. Bitte erst Workouts archivieren.")
                st.stop()
            
            # Sortiere nach Datum
            archived.sort(key=lambda x: datetime.datetime.strptime(
                x.get('Datum', '1900-01-01'), '%Y-%m-%d'
            ))
            
            # Hole Fragebogen-Daten
            qb = fragebogen_ws.get_all_records()
            user_qb = next(
                (r for r in qb if r.get('UserID') == st.session_state.userid), 
                {}
            )
            
            # Erstelle Workout-Liste
            workout_list = "\n".join([
                f"- {w['Datum']}: {w['Übung']} ({w.get('Gewicht', '')}kg x {w.get('Wdh', '')} Wdh)"
                for w in archived
            ])
            
            # Daten für Template
            data = {
                **user_qb, 
                'workout_list': workout_list, 
                'additional_goals': additional_goals
            }
            
            # Prompt erstellen
            prompt = prompt_template.safe_substitute(data)
            
            # Vereinfachter Prompt für besseres JSON
            system_prompt = """Du bist ein Fitness-Trainer. Erstelle einen Trainingsplan als JSON.
            
Antworte NUR mit einem gültigen JSON-Objekt in diesem Format:
{
  "trainingsplan": {
    "woche1": {
      "tag1": [
        {"übung": "Kniebeuge", "sätze": 3, "wiederholungen": "8-10", "gewicht": "80kg"},
        {"übung": "Bankdrücken", "sätze": 3, "wiederholungen": "8-10", "gewicht": "60kg"}
      ]
    }
  }
}

Keine zusätzlichen Erklärungen, nur JSON!"""
            
            # OpenAI API Aufruf
            temp = prompt_config.get('temperature', 0.7)
            tokens = int(prompt_config.get('max_tokens', 1500))
            
            # Debug: Zeige Prompt
            with st.expander("Debug: Prompt an ChatGPT"):
                st.text(prompt[:500] + "..." if len(prompt) > 500 else prompt)
            
            response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temp,
                max_tokens=tokens
            )
            
            raw = response.choices[0].message.content
            
            # Debug: Zeige Roh-Antwort
            with st.expander("Debug: ChatGPT Antwort"):
                st.code(raw)
            
            # Versuche JSON zu extrahieren (falls Text drumherum)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                raw = json_match.group()
            
            # JSON parsen
            try:
                plan = json.loads(raw)
                
                # Plan speichern
                updated_ws.append_row([
                    st.session_state.userid, 
                    datetime.date.today().isoformat(), 
                    json.dumps(plan)
                ])
                st.success("Plan aktualisiert und gespeichert!")
                st.json(plan)
                
            except json.JSONDecodeError as e:
                st.error(f"Ungültiges JSON: {e}")
                st.code(raw)
                
        except Exception as e:
            st.error(f"Fehler bei der Plan-Erstellung: {str(e)}")
            st.code(traceback.format_exc())

col2.info("Für regelmäßige Updates richte einen externen Scheduler ein.")

# ---- Neues Workout/Übung hinzufügen ----
st.header("Neues Workout/Übung hinzufügen")

# Debug: Zeige Spaltenstruktur
with st.expander("Debug: Spaltenstruktur"):
    header = get_header_row(ws)
    st.write("Spalten im Sheet:", header)
    st.write("Anzahl Spalten:", len(header))

col1, col2 = st.columns(2)
with col1:
    new_workout = st.text_input("Workout Name")
    new_exercise = st.text_input("Übung")
    
with col2:
    new_sets = st.number_input("Anzahl Sätze", min_value=1, value=3)
    new_weight = st.number_input("Gewicht (kg)", min_value=0.0, step=0.25)
    new_reps = st.number_input("Wiederholungen", min_value=1, value=10)

if st.button("Workout hinzufügen"):
    if new_workout and new_exercise:
        try:
            # Hole Header für Spalten-Mapping
            header = get_header_row(ws)
            
            # Erstelle neue Zeilen basierend auf tatsächlicher Struktur
            for satz in range(1, new_sets + 1):
                new_row = [''] * len(header)  # Leere Zeile mit richtiger Länge
                
                # Fülle nur die Spalten die existieren
                for i, col_name in enumerate(header):
                    if col_name == 'UserID':
                        new_row[i] = st.session_state.userid
                    elif col_name == 'Datum':
                        new_row[i] = datetime.date.today().isoformat()
                    elif col_name == 'Workout Name':
                        new_row[i] = new_workout
                    elif col_name == 'Übung':
                        new_row[i] = new_exercise
                    elif col_name == 'Satz-Nr.':
                        new_row[i] = satz
                    elif col_name == 'Gewicht':
                        new_row[i] = new_weight
                    elif col_name == 'Wdh':
                        new_row[i] = new_reps
                    elif col_name == 'Erledigt':
                        new_row[i] = False
                    elif col_name == 'Status':
                        new_row[i] = 'aktiv'
                
                # Zeile hinzufügen
                ws.append_row(new_row)
            
            st.success(f"Workout '{new_workout}' mit {new_sets} Sätzen hinzugefügt!")
            st.cache_data.clear()
            st.rerun()
            
        except Exception as e:
            st.error(f"Fehler beim Hinzufügen: {str(e)}")
            st.code(traceback.format_exc())
    else:
        st.error("Bitte Workout Name und Übung eingeben.")

# ---- Footer ----
st.markdown("---")
st.caption("Workout Tracker v2.0 - Mit Google Sheets Integration und AI-gestützter Trainingsplanung")
