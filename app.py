import streamlit as st
import datetime
import gspread
import pandas as pd
import numpy as np
from oauth2client.service_account import ServiceAccountCredentials
from string import Template
import openai
import json
import os

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"  # exakt wie im Spreadsheet-Tabellenblatt-Titel  # ggf. genau wie im Google Sheet-Tabellenblatt-Titel anpassen
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

@st.cache_data
def open_sheets():
    client = get_gspread_client()
    ss = client.open(SHEET_NAME)
    sheets = {}
    # Debug: liste aller verfügbaren Sheets
    all_titles = [sh.title for sh in ss.worksheets()]
    st.write("Verfügbare Tabellenblätter:", all_titles)
    try:
        sheets['tracker'] = ss.worksheet(WORKSHEET_NAME)
    except Exception:
        st.error(f"Tracker-Sheet '{WORKSHEET_NAME}' nicht gefunden. Verfügbare: {all_titles}")
        st.stop()
    try:
        sheets['fragebogen'] = ss.worksheet("fragebogen")
    except Exception:
        st.error(f"Fragebogen-Sheet 'fragebogen' nicht gefunden. Verfügbare: {all_titles}")
        st.stop()
    try:
        sheets['updated'] = ss.worksheet(UPDATED_PLANS_SHEET)
    except gspread.exceptions.WorksheetNotFound:
        sheets['updated'] = ss.add_worksheet(
            title=UPDATED_PLANS_SHEET, rows=1, cols=3
        )
        sheets['updated'].append_row(['UserID', 'Datum', 'PlanJSON'])
    return sheets

worksheets = open_sheets()
ws = worksheets['tracker']
updated_ws = worksheets['updated']

# ---- OpenAI Setup ----
try:
    openai_key = st.secrets["openai_api_key"]
except KeyError:
    openai_key = os.getenv("OPENAI_API_KEY")
# Fallback: temporäre Eingabe des Keys über UI
if not openai_key:
    openai_key = st.text_input("**API Key fehlt** – bitte OpenAI API Key eingeben (wird nicht gespeichert)", type="password")
    if openai_key:
        st.warning("Key nur temporär genutzt. Für Dauerbetrieb bitte in Secrets speichern.")
if not openai_key:
    st.error(
        "OpenAI API Key nicht gefunden. Bitte openai_api_key in Secrets setzen oder Umgebungsvariable OPENAI_API_KEY einrichten."
    )
    st.stop()
openai.api_key = openai_key

# ---- Prompt-Template laden mit Konfiguration ----
@st.cache_data
def load_prompt_and_config(path: str):
    if not os.path.exists(path):
        st.error(f"Prompt-Template nicht gefunden: {path}")
        default = "Nutze folgende Daten, um einen Trainingsplan zu erstellen: ${workout_list}"
        return Template(default), {'temperature': 0.7, 'max_tokens': 1500}
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    config = {}
    idx = 0
    while idx < len(lines) and lines[idx].startswith('#'):
        key, val = lines[idx][1:].split(':', 1)
        config[key.strip()] = float(val.strip())
        idx += 1
    template_text = "\n".join(lines[idx:])
    return Template(template_text), config

prompt_template, prompt_config = load_prompt_and_config(PROMPT_TEMPLATE_PATH)

# ---- App UI ----
st.set_page_config(page_title="📋 Workout Tracker + Plan-Update", layout="wide")
st.title("📋 Workout Tracker (Google Sheets)")

# Login / UserID
if 'userid' not in st.session_state:
    st.session_state.userid = None
uid = st.text_input("UserID", type="password")
if st.button("Login"):
    header = ws.row_values(1)
    try:
        uid_col = header.index("UserID") + 1
        valid_ids = ws.col_values(uid_col)[1:]
    except ValueError:
        st.error("Spalte 'UserID' nicht gefunden.")
    else:
        if uid in valid_ids:
            st.session_state.userid = uid
            st.success(f"Eingeloggt als {uid}")
        else:
            st.error("Ungültige UserID.")
if not st.session_state.userid:
    st.stop()

# Daten laden
@st.cache_data
def load_data():
    rec = ws.get_all_records()
    df = pd.DataFrame(rec)
    for col in ["Gewicht", "Wdh"]:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['UserID'] = df['UserID'].astype(str)
    return df

df = load_data()
user_df = df[df['UserID'] == st.session_state.userid]

# ---- Alte Workouts ----
with st.expander("Alte Workouts", expanded=False):
    workouts = user_df["Workout Name"].dropna().unique()
    for workout in workouts:
        with st.expander(f"Workout: {workout}"):
            workout_df = user_df[user_df["Workout Name"] == workout]
            exercises = workout_df["Übung"].dropna().unique()
            for ex in exercises:
                with st.expander(f"Übung: {ex}"):
                    ex_df = workout_df[workout_df["Übung"] == ex].sort_values("Satz-Nr.")
                    for idx, row in ex_df.iterrows():
                        st.write(f"Satz {int(row['Satz-Nr.'])}: {row['Gewicht']}kg x {row['Wdh']}")
                        cols = st.columns([2,2,1,1])
                        new_w = cols[0].number_input("Gewicht", value=row['Gewicht'], step=0.25, key=f"w_{idx}")
                        new_r = cols[1].number_input("Wdh", value=int(row['Wdh']), key=f"r_{idx}")
                        if cols[2].button("✔ Erledigt", key=f"done_{idx}"):
                            ws.update_cell(idx+2, df.columns.get_loc('Gewicht')+1, new_w)
                            ws.update_cell(idx+2, df.columns.get_loc('Wdh')+1, new_r)
                            ws.update_cell(idx+2, df.columns.get_loc('Erledigt')+1, True)
                            st.experimental_rerun()
                        if cols[3].button("Löschen", key=f"del_{idx}"):
                            ws.delete_rows(idx+2)
                            st.experimental_rerun()

# ---- Trainingsplan aktualisieren ----
st.header("Trainingsplan aktualisieren")
additional_goals = st.text_area("Zusätzliche Ziele/Wünsche (optional)")
col1, col2 = st.columns(2)
if col1.button("Sofort ausführen"):
    all_rec = ws.get_all_records()
    archived = [r for r in all_rec if r.get('Status')=='archiviert' and r.get('UserID')==st.session_state.userid]
    archived.sort(key=lambda x: datetime.datetime.strptime(x.get('Datum','1900-01-01'), '%Y-%m-%d'))
    qb = worksheets['fragebogen'].get_all_records()
    user_qb = next((r for r in qb if r.get('UserID')==st.session_state.userid), {})
    workout_list = "\n".join([
        f"- {w['Datum']}: {w['Übung']} ({w.get('Gewicht','')}kg x {w.get('Wdh','')} Wdh)"
        for w in archived
    ])
    data = {**user_qb, 'workout_list': workout_list, 'additional_goals': additional_goals}
    prompt = prompt_template.safe_substitute(data)
    full_prompt = "Bitte gib deine Antwort ausschließlich als gültiges JSON zurück.\n" + prompt
    temp = prompt_config.get('temperature', 0.7)
    tokens = int(prompt_config.get('max_tokens', 1500))
    resp = openai.ChatCompletion.create(
        model='gpt-4o-mini',
        messages=[{'role':'user','content': full_prompt}],
        temperature=temp,
        max_tokens=tokens
    )
    raw = resp.choices[0].message.content
    try:
        plan = json.loads(raw)
    except Exception:
        st.error("Ungültiges JSON:")
        st.code(raw)
    else:
        updated_ws.append_row([st.session_state.userid, datetime.date.today().isoformat(), json.dumps(plan)])
        st.success("Plan aktualisiert und gespeichert!")
        st.json(plan)
col2.info("Für regelmäßige Updates richte externen Scheduler ein.")
