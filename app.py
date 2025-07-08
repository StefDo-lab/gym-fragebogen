import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# ---- KONFIGURATION ----
SHEET_NAME = "Workout Tabelle"       # Name deines Google Sheets
WORKSHEET_NAME = "Tabellenblatt1"    # Name des Arbeitsblatts (Tab unten)

# ---- AUTHENTIFIZIERUNG über Service-Account ----
@st.cache_resource
def get_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scopes)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME)
    return sheet.worksheet(WORKSHEET_NAME)

worksheet = get_worksheet()

# ---- APP-HEADER ----
st.title("📋 Workout Tracker (Google Sheets)")

# ---- LOGIN via UserID (dynamisch) ----
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    uid = st.text_input("Deine UserID", type="password")
    login_clicked = st.button("Login")
    if login_clicked:
        header = worksheet.row_values(1)
        col_userid = header.index("UserID") + 1
        all_user_ids = worksheet.col_values(col_userid)[1:]
        if uid in all_user_ids:
            st.session_state.userid = uid
            st.session_state.authenticated = True
            st.success(f"Eingeloggt als {uid}")
        else:
            st.error("Ungültige UserID oder kein Zugriff auf Workouts.")
    if not st.session_state.authenticated:
        st.stop()

# ---- HAUPTBEREICH nach Login ----
# Daten aus Google Sheet laden
records = worksheet.get_all_records()
df = pd.DataFrame(records)

# Konvertiere Gewicht und Wdh zu numerischen Werten
# und fülle fehlende Werte
df["Gewicht"] = pd.to_numeric(df["Gewicht"], errors="coerce").fillna(0)
df["Wdh"] = pd.to_numeric(df["Wdh"], errors="coerce").fillna(0).astype(int)

# Filter nach UserID
df["UserID"] = df["UserID"].astype(str)
user_df = df[df["UserID"] == st.session_state.userid]

if user_df.empty:
    st.warning("Keine Workouts gefunden.")
else:
    user_df["Datum"] = pd.to_datetime(user_df["Datum"], errors="coerce")
    for (datum, workout_name), group in user_df.groupby(["Datum", "Workout Name"]):
        with st.expander(f"{datum.date()} – {workout_name}"):
            for idx, row in group.iterrows():
                gewicht = st.number_input(
                    f"{row['Übung']} (Satz {row['Satz-Nr.']}) – Gewicht",
                    value=row['Gewicht'], key=f"g_{idx}")
                wdh = st.number_input(
                    "Wdh",
                    value=row['Wdh'], key=f"w_{idx}")
                erledigt = st.checkbox(
                    "✅ Erledigt",
                    value=row['Erledigt'], key=f"e_{idx}")

                if st.button("Speichern", key=f"s_{idx}"):
                    header = worksheet.row_values(1)
                    row_number = idx + 2
                    col_gewicht = header.index("Gewicht") + 1
                    col_wdh = header.index("Wdh") + 1
                    col_erledigt = header.index("Erledigt") + 1

                    worksheet.update_cell(row_number, col_gewicht, gewicht)
                    worksheet.update_cell(row_number, col_wdh, wdh)
                    worksheet.update_cell(row_number, col_erledigt, erledigt)
                    st.success("✅ Gespeichert")
