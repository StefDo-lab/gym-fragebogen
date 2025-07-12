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
if 'user_data' not in st.session_state:
    st.session_state.user_data = None

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
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
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

def load_user_workouts():
    """Lädt nur die Workouts des eingeloggten Users"""
    worksheet = get_worksheet()
    if not worksheet:
        return None
    
    try:
        # Hole alle Daten
        all_data = worksheet.get_all_values()
        if len(all_data) < 2:
            return None
        
        header = all_data[0]
        rows = all_data[1:]
        
        # Finde UserID Spalte
        uid_col = header.index("UserID")
        
        # Filtere nach User
        user_rows = []
        for i, row in enumerate(rows):
            if row[uid_col] == st.session_state.userid:
                user_rows.append(row + [i + 2])  # Füge Zeilennummer hinzu
        
        if not user_rows:
            return None
        
        # Erstelle DataFrame
        df = pd.DataFrame(user_rows, columns=header + ['_row_num'])
        
        # Konvertiere Datentypen
        for col in ['Gewicht', 'Wdh', 'Satz-Nr.']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
        
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")
        return None

def save_changes():
    """Speichert alle lokalen Änderungen"""
    if not st.session_state.local_changes:
        return True
    
    worksheet = get_worksheet()
    if not worksheet:
        return False
    
    try:
        batch_updates = []
        
        for (row_num, col_name), value in st.session_state.local_changes.items():
            # Finde Spalten-Buchstabe
            header = worksheet.row_values(1)
            col_idx = header.index(col_name) + 1
            col_letter = chr(64 + col_idx) if col_idx <= 26 else 'A' + chr(64 + col_idx - 26)
            
            batch_updates.append({
                'range': f'{col_letter}{row_num}',
                'values': [[str(value)]]
            })
        
        # Batch Update
        if batch_updates:
            worksheet.batch_update(batch_updates)
        
        st.session_state.local_changes = {}
        st.session_state.unsaved_changes = False
        return True
        
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
        return False

# ---- Hauptnavigation ----
tab1, tab2 = st.tabs(["Training", "Daten Management"])

with tab1:
    # Lade-Button und Speicher-Button in einer Zeile
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("📥 Workouts laden", type="primary"):
            with st.spinner("Lade Workouts..."):
                st.session_state.user_data = load_user_workouts()
                if st.session_state.user_data is not None:
                    st.success("Workouts geladen!")
                else:
                    st.warning("Keine Workouts gefunden")
    
    with col2:
        if st.button("💾 Speichern", disabled=not st.session_state.unsaved_changes):
            if save_changes():
                st.success("Gespeichert!")
                st.session_state.user_data = load_user_workouts()
    
    # Zeige Workouts
    if st.session_state.user_data is not None:
        df = st.session_state.user_data
        
        # Ungespeicherte Änderungen Indikator
        if st.session_state.unsaved_changes:
            st.warning(f"⚠️ {len(st.session_state.local_changes)} ungespeicherte Änderungen")
        
        # Gruppiere nach Workout
        workouts = df['Workout Name'].unique()
        
        for workout in workouts:
            st.subheader(workout)
            workout_data = df[df['Workout Name'] == workout]
            
            # Gruppiere nach Übung
            exercises = workout_data['Übung'].unique()
            
            for exercise in exercises:
                with st.expander(f"**{exercise}**"):
                    exercise_data = workout_data[workout_data['Übung'] == exercise].sort_values('Satz-Nr.')
                    
                    for idx, row in exercise_data.iterrows():
                        col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
                        
                        row_num = row['_row_num']
                        
                        with col1:
                            st.write(f"**Satz {int(row['Satz-Nr.'])}**")
                        
                        with col2:
                            # Gewicht
                            key = (row_num, 'Gewicht')
                            current_weight = st.session_state.local_changes.get(key, row['Gewicht'])
                            
                            new_weight = st.number_input(
                                "Gewicht",
                                value=float(current_weight),
                                step=2.5,
                                key=f"w_{row_num}"
                            )
                            
                            if new_weight != row['Gewicht']:
                                st.session_state.local_changes[key] = new_weight
                                st.session_state.unsaved_changes = True
                        
                        with col3:
                            # Wiederholungen
                            key = (row_num, 'Wdh')
                            current_reps = st.session_state.local_changes.get(key, row['Wdh'])
                            
                            new_reps = st.number_input(
                                "Wdh",
                                value=int(current_reps),
                                step=1,
                                key=f"r_{row_num}"
                            )
                            
                            if new_reps != row['Wdh']:
                                st.session_state.local_changes[key] = new_reps
                                st.session_state.unsaved_changes = True
                        
                        with col4:
                            # Erledigt Status
                            key = (row_num, 'Erledigt')
                            current_status = st.session_state.local_changes.get(key, row.get('Erledigt', 'FALSE'))
                            
                            if current_status == 'TRUE':
                                btn_label = "✓ Erledigt"
                                btn_type = "primary"
                            else:
                                btn_label = "Erledigt"
                                btn_type = "secondary"
                            
                            if st.button(btn_label, key=f"done_{row_num}", type=btn_type):
                                new_status = 'FALSE' if current_status == 'TRUE' else 'TRUE'
                                st.session_state.local_changes[key] = new_status
                                st.session_state.local_changes[(row_num, 'Gewicht')] = new_weight
                                st.session_state.local_changes[(row_num, 'Wdh')] = new_reps
                                st.session_state.unsaved_changes = True
                                st.rerun()
    else:
        st.info("Klicke auf '📥 Workouts laden' um deine Trainingsdaten zu sehen")

with tab2:
    st.subheader("Debug & Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Cache leeren"):
            st.session_state.worksheet = None
            st.session_state.user_data = None
            st.session_state.local_changes = {}
            st.session_state.unsaved_changes = False
            st.success("Cache geleert")
    
    with col2:
        if st.button("🔍 Session State anzeigen"):
            st.write(st.session_state)

st.markdown("---")
st.caption("v6.0 - Workout Anzeige mit Batch-Speicherung")
