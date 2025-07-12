import streamlit as st
import datetime
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import time

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"

# ---- App UI ----
st.set_page_config(page_title="Workout Tracker", layout="wide")
st.title("Workout Tracker")

# ---- Session State ----
if 'userid' not in st.session_state:
    st.session_state.userid = None
if 'worksheet' not in st.session_state:
    st.session_state.worksheet = None
if 'local_changes' not in st.session_state:
    st.session_state.local_changes = {}
if 'unsaved_changes' not in st.session_state:
    st.session_state.unsaved_changes = False

# ---- Login ----
if not st.session_state.userid:
    st.subheader("Login")
    uid = st.text_input("UserID", type="password")
    
    if st.button("Login"):
        if uid:
            st.session_state.userid = uid.strip()
            st.success(f"Eingeloggt als {uid.strip()}")
            st.rerun()
    st.stop()

# ---- Google Sheets Verbindung ----
def get_worksheet():
    if st.session_state.worksheet is None:
        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                st.secrets["gcp_service_account"], scopes
            )
            client = gspread.authorize(creds)
            ss = client.open(SHEET_NAME)
            st.session_state.worksheet = ss.worksheet(WORKSHEET_NAME)
        except Exception as e:
            st.error(f"Fehler beim Verbinden: {e}")
            return None
    return st.session_state.worksheet

# ---- Hauptnavigation ----
tab1, tab2 = st.tabs(["Training", "Daten laden"])

with tab1:
    st.info("Klicke auf 'Daten laden' um dein Workout zu sehen")
    
    # Zeige lokale Änderungen
    if st.session_state.unsaved_changes:
        st.warning(f"⚠️ {len(st.session_state.local_changes)} ungespeicherte Änderungen")
        
        if st.button("💾 Alle Änderungen speichern", type="primary"):
            worksheet = get_worksheet()
            if worksheet:
                try:
                    # Hier würde der Save-Code kommen
                    st.success("Gespeichert! (Demo)")
                    st.session_state.local_changes = {}
                    st.session_state.unsaved_changes = False
                except Exception as e:
                    st.error(f"Fehler: {e}")

with tab2:
    st.subheader("Daten Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Workout Daten laden", type="primary"):
            worksheet = get_worksheet()
            if worksheet:
                try:
                    with st.spinner("Lade Daten..."):
                        # Minimaler Test-Request
                        header = worksheet.row_values(1)
                        st.success(f"Header geladen: {len(header)} Spalten")
                        
                        # Zeige Header
                        st.write("Gefundene Spalten:")
                        st.write(header)
                        
                except Exception as e:
                    if "quota" in str(e).lower():
                        st.error("⏳ API Limit erreicht. Bitte warte 60 Sekunden.")
                    else:
                        st.error(f"Fehler: {e}")
    
    with col2:
        if st.button("🔄 Cache leeren"):
            st.session_state.worksheet = None
            st.success("Cache geleert")

st.markdown("---")
st.caption("v5.0 - Minimale Test-Version")
