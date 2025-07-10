import streamlit as st
import datetime
import gspread
import pandas as pd
import numpy as np
from oauth2client.service_account import ServiceAccountCredentials
from string import Template
import openai
import json

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"
PROMPT_TEMPLATE_PATH = "prompt_templates/update_plan.txt"
UPDATED_PLANS_SHEET = "Aktualisierte_Pläne"

# ---- Google Sheets Setup ----
@st.experimental_singleton
def get_ws():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["gcp_service_account"]), scopes
    )
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

# Sheets öffnen
ss = get_ws()
ws = ss.worksheet(WORKSHEET_NAME)
updated_ws = ss.worksheet(UPDATED_PLANS_SHEET)

# ---- OpenAI Setup ----
openai.api_key = st.secrets["openai"]["api_key"]

# ---- Prompt-Template laden mit Konfiguration ----
@st.experimental_memo
def load_prompt_and_config(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    config = {}
    idx = 0
    # Einlesen von Meta-Daten als Kommentare: # key: value
    while idx < len(lines) and lines[idx].startswith('#'):
        line = lines[idx][1:].strip()
        if ':' in line:
            key, val = lines[idx][1:].split(':', 1)
            if key.strip() in ['temperature', 'max_tokens']:
                config[key.strip()] = float(val.strip())
            else:
                config[key.strip()] = val.strip()
        idx += 1
    # Rest als Template
    template_text = '\n'.join(lines[idx:])
    return Template(template_text), config

prompt_template, prompt_config = load_prompt_and_config(PROMPT_TEMPLATE_PATH)

# ---- App UI ----
st.set_page_config(page_title="📋 Workout Tracker + Plan-Update", layout="wide")
st.title("📋 Workout Tracker (Google Sheets)")

# Login / UserID
if "userid" not in st.session_state:
    st.session_state.userid = None

uid = st.text_input("UserID", type="password")
if st.button("Login"):
    header = ws.row_values(1)
    try:
        idx_uid = header.index("UserID") + 1
        valid_ids = ws.col_values(idx_uid)[1:]
    except ValueError:
        st.error("Spalte 'UserID' nicht gefunden.")
    else:
        if uid in valid_ids:
            st.session_state.userid = uid
            st.success(f"Eingeloggt als {uid}")
        else:
            st.error("Ungültige UserID.")

if st.session_state.userid is None:
    st.stop()

# Daten laden
@st.experimental_memo
def load_data():
    rec = ws.get_all_records()
    df = pd.DataFrame(rec)
    for c in ["Gewicht", "Wdh"]:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    df['UserID'] = df['UserID'].astype(str)
    return df

df = load_data()
user_df = df[df['UserID'] == st.session_state.userid]

# Alte Workouts
with st.expander("Alte Workouts", expanded=False):
    # Workout-Tracker
    workouts = user_df["Workout Name"].dropna().unique()
    for workout in workouts:
        with st.expander(f"Workout: {workout}"):
            workout_df = user_df[user_df["Workout Name"] == workout]
            exercises = workout_df["Übung"].dropna().unique()
            for ex in exercises:
                with st.expander(f"Übung: {ex}"):
                    ex_df = workout_df[workout_df["Übung"] == ex].sort_values("Satz-Nr.")
                    for idx, row_data in ex_df.iterrows():
                        st.write(f"Satz {int(row_data['Satz-Nr.'])}: Gewicht: {row_data['Gewicht']} kg, Wdh: {row_data['Wdh']}, Erledigt: {row_data['Erledigt']}")
                        cols = st.columns([2,2,1,1])
                        new_g = cols[0].number_input("Gewicht", value=float(row_data['Gewicht']), step=0.25, key=f"g_{workout}_{ex}_{idx}")
                        new_r = cols[1].number_input("Wdh", value=int(row_data['Wdh']), key=f"r_{workout}_{ex}_{idx}")
                        erledigt = True if row_data['Erledigt'] else False
                        cols[2].checkbox("Erledigt", value=erledigt, key=f"d_{workout}_{ex}_{idx}", disabled=True)
                        if cols[3].button("Erledigt", key=f"done_{workout}_{ex}_{idx}"):
                            ws.update_cell(idx+2, df.columns.get_loc('Gewicht')+1, float(new_g))
                            ws.update_cell(idx+2, df.columns.get_loc('Wdh')+1, int(new_r))
                            ws.update_cell(idx+2, df.columns.get_loc('Erledigt')+1, True)
                            st.experimental_rerun()
                        if cols[3].button("Löschen", key=f"del_{workout}_{ex}_{idx}"):
                            ws.delete_rows(idx+2)
                            st.experimental_rerun()
                    if st.button(f"Neuen Satz zu {ex} hinzufügen", key=f"add_set_{workout}_{ex}"):
                        next_set = int(ex_df["Satz-Nr."] .max()) + 1 if not ex_df.empty else 1
                        header = ws.row_values(1)
                        row = ["", "", workout, ex, next_set, 0, 0, "", "", st.session_state.userid, "", False, "", ""]
                        while len(row) < len(header):
                            row.append("")
                        ws.append_row(row)
                        st.experimental_rerun()
            with st.form(f"add_ex_{workout}_bottom"):
                new_ex = st.text_input(f"Neue Übung für {workout}", key=f"ex_{workout}_bottom")
                if st.form_submit_button(f"Übung zu {workout} hinzufügen"):
                    if new_ex:
                        header = ws.row_values(1)
                        row = ["", "", workout, new_ex, 1, 0, 0, "", "", st.session_state.userid, "", False, "", ""]
                        while len(row) < len(header):
                            row.append("")
                        ws.append_row(row)
                        st.experimental_rerun()

# ---- Trainingsplan aktualisieren ----
st.header("Trainingsplan aktualisieren")
col1, col2 = st.columns(2)

if col1.button("Sofort ausführen"):
    # Archivierte Workouts und Fragebogen-Daten sammeln
    all_records = ws.get_all_records()
    archived = [r for r in all_records if str(r.get('UserID')) == st.session_state.userid and r.get('Status') == 'archiviert']
    import datetime as _dt
    # sortiere nach echtem Datum (YYYY-MM-DD)
    archived.sort(key=lambda x: _dt.datetime.strptime(x.get('Datum', '1900-01-01'), '%Y-%m-%d'))
    # Fragebogen-Daten
    quiz = ss.worksheet("fragebogen").get_all_records()
    qb = next((r for r in quiz if str(r.get('UserID')) == st.session_state.userid), {})
    # Prompt zusammenstellen und JSON-Antwort anfordern
    workout_list = "\n".join([
        f"- {w['Datum']}: {w['Übung']} ({w.get('Gewicht','')}kg x {w.get('Wdh','')} Wdh)"
        for w in archived
    ])
    data = {**qb, 'workout_list': workout_list, 'additional_goals': ''}
    prompt_text = prompt_template.safe_substitute(data)
    full_prompt = "Bitte gib deine Antwort ausschließlich als gültiges JSON zurück.\n" + prompt_text
    # ChatGPT-Aufruf mit Konfiguration aus Prompt-Datei
    temperature = prompt_config['temperature']
    max_tokens = int(prompt_config['max_tokens'])
    resp = openai.ChatCompletion.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': full_prompt}],
        temperature=temperature,
        max_tokens=max_tokens
    )
    raw = resp.choices[0].message.content
    try:
        plan_json = json.loads(raw)
    except json.JSONDecodeError:
        st.error("Antwort war kein gültiges JSON:")
        st.code(raw)
    else:
        # Als JSON im Sheet speichern oder verarbeiten
        today = datetime.date.today().isoformat()
        updated_ws.append_row([st.session_state.userid, today, json.dumps(plan_json)])
        st.success("Trainingsplan (JSON) aktualisiert und gespeichert!")
        st.json(plan_json)

col2.info(
    "Für automatische Ausführung richte einen externen Scheduler ein, der dieses Skript regelmäßig aufruft."
)
