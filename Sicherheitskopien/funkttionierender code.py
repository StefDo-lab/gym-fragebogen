import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import numpy as np

SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"

@st.cache_resource
def get_ws():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scopes)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)

ws = get_ws()

st.title("📋 Workout Tracker (Google Sheets)")

if "userid" not in st.session_state:
    st.session_state.userid = None
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

uid = st.text_input("UserID", type="password")
if st.button("Login"):
    header = ws.row_values(1)
    try:
        idx = header.index("UserID") + 1
        valid_ids = ws.col_values(idx)[1:]
    except ValueError:
        st.error("Spalte 'UserID' nicht gefunden.")
    else:
        if uid in valid_ids:
            st.session_state.userid = uid
            st.success(f"Eingeloggt als {uid}")
            rec = ws.get_all_records()
            df = pd.DataFrame(rec)
            for c in ["Gewicht", "Wdh"]:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            df['UserID'] = df['UserID'].astype(str)
            st.session_state.df = df
        else:
            st.error("Ungültige UserID.")

if st.session_state.userid is None:
    st.stop()

def reload_data():
    rec = ws.get_all_records()
    df2 = pd.DataFrame(rec)
    for c in ["Gewicht", "Wdh"]:
        df2[c] = pd.to_numeric(df2[c], errors='coerce').fillna(0)
    df2['UserID'] = df2['UserID'].astype(str)
    st.session_state.df = df2

reload_data()

df = st.session_state.df.copy()
user_df = df[df['UserID'] == st.session_state.userid]

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
                    # Der Haken ist immer gesetzt, wenn erledigt wurde
                    erledigt = True if row_data['Erledigt'] else False
                    cols[2].checkbox("Erledigt", value=erledigt, key=f"d_{workout}_{ex}_{idx}", disabled=True)
                    if cols[3].button("Erledigt", key=f"done_{workout}_{ex}_{idx}"):
                        ws.update_cell(idx+2, df.columns.get_loc('Gewicht')+1, float(new_g))
                        ws.update_cell(idx+2, df.columns.get_loc('Wdh')+1, int(new_r))
                        ws.update_cell(idx+2, df.columns.get_loc('Erledigt')+1, True)
                        reload_data()
                        st.success("Satz erledigt!")
                        st.rerun()
                    # Satz löschen
                    if cols[3].button("Löschen", key=f"del_{workout}_{ex}_{idx}"):
                        ws.delete_rows(idx+2)
                        reload_data()
                        st.success("Satz gelöscht!")
                        st.rerun()
                # ---- NEUEN SATZ HINZUFÜGEN ----
                if st.button(f"Neuen Satz zu {ex} hinzufügen", key=f"add_set_{workout}_{ex}"):
                    next_set = int(ex_df["Satz-Nr."].max()) + 1 if not ex_df.empty else 1
                    header = ws.row_values(1)
                    row = ["", "", workout, ex, int(next_set), 0, 0, "", "", st.session_state.userid, "", False, "", ""]
                    row = [int(x) if isinstance(x, (np.integer,)) else float(x) if isinstance(x, (np.floating,)) else str(x) if isinstance(x, (pd.Timestamp,)) else x for x in row]
                    while len(row) < len(header):
                        row.append("")
                    ws.append_row(row)
                    reload_data()
                    st.success(f"Satz {next_set} zu '{ex}' hinzugefügt.")
                    st.rerun()
        # ---- NEUE ÜBUNG UNTEN HINZUFÜGEN ----
        with st.form(f"add_ex_{workout}_bottom"):
            new_ex = st.text_input(f"Neue Übung für {workout}", key=f"ex_{workout}_bottom")
            if st.form_submit_button(f"Übung zu {workout} hinzufügen"):
                if new_ex:
                    header = ws.row_values(1)
                    row = ["", "", workout, new_ex, 1, 0, 0, "", "", st.session_state.userid, "", False, "", ""]
                    row = [int(x) if isinstance(x, (np.integer,)) else float(x) if isinstance(x, (np.floating,)) else str(x) if isinstance(x, (pd.Timestamp,)) else x for x in row]
                    while len(row) < len(header):
                        row.append("")
                    ws.append_row(row)
                    reload_data()
                    st.success(f"Übung '{new_ex}' zu '{workout}' hinzugefügt.")
                    st.rerun()

# ---- NEUES WORKOUT UNTEN HINZUFÜGEN ----
with st.form("add_workout_bottom"):
    st.subheader("Neues Workout hinzufügen")
    new_workout = st.text_input("Workout Name (unten)", key="workout_bottom")
    if st.form_submit_button("Workout anlegen (unten)"):
        if new_workout:
            header = ws.row_values(1)
            row = ["", "", new_workout, "", 1, 0, 0, "", "", st.session_state.userid, "", False, "", ""]
            row = [int(x) if isinstance(x, (np.integer,)) else float(x) if isinstance(x, (np.floating,)) else str(x) if isinstance(x, (pd.Timestamp,)) else x for x in row]
            while len(row) < len(header):
                row.append("")
            ws.append_row(row)
            reload_data()
            st.success(f"Workout '{new_workout}' angelegt.")
            st.rerun()
