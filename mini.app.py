import streamlit as st
import datetime
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
import time
import re

# ---- Konfiguration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"
ARCHIVE_SHEET = "Workout_archiv"
FRAGEBOGEN_SHEET = "fragebogen"

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
if 'rows_to_delete' not in st.session_state:
    st.session_state.rows_to_delete = []
if 'rows_to_add' not in st.session_state:
    st.session_state.rows_to_add = []

# ---- OpenAI Setup ----
openai_key = st.secrets.get("openai_api_key", None)
if openai_key:
    client = OpenAI(api_key=openai_key)
else:
    client = None

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

def get_sheet(sheet_name):
    """Holt ein spezifisches Sheet"""
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
        return ss.worksheet(sheet_name)
    except:
        return None

def load_user_workouts():
    """Lädt nur die Workouts des eingeloggten Users"""
    worksheet = get_worksheet()
    if not worksheet:
        return None
    
    try:
        all_data = worksheet.get_all_values()
        if len(all_data) < 2:
            return None
        
        header = all_data[0]
        rows = all_data[1:]
        
        uid_col = header.index("UserID")
        
        user_rows = []
        for i, row in enumerate(rows):
            if row[uid_col] == st.session_state.userid:
                user_rows.append(row + [i + 2])
        
        if not user_rows:
            return None
        
        df = pd.DataFrame(user_rows, columns=header + ['_row_num'])
        
        for col in ['Gewicht', 'Wdh', 'Satz-Nr.']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df
        
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")
        return None

def save_changes():
    """Speichert alle lokalen Änderungen"""
    worksheet = get_worksheet()
    if not worksheet:
        return False
    
    try:
        # 1. Lösche markierte Zeilen
        if st.session_state.rows_to_delete:
            for row_num in sorted(st.session_state.rows_to_delete, reverse=True):
                worksheet.delete_rows(row_num)
            st.session_state.rows_to_delete = []
        
        # 2. Füge neue Zeilen hinzu
        if st.session_state.rows_to_add:
            for new_row in st.session_state.rows_to_add:
                worksheet.append_row(new_row)
            st.session_state.rows_to_add = []
        
        # 3. Update bestehende Zeilen
        if st.session_state.local_changes:
            batch_updates = []
            
            for (row_num, col_name), value in st.session_state.local_changes.items():
                if row_num in st.session_state.rows_to_delete:
                    continue
                    
                header = worksheet.row_values(1)
                col_idx = header.index(col_name) + 1
                col_letter = chr(64 + col_idx) if col_idx <= 26 else 'A' + chr(64 + col_idx - 26)
                
                batch_updates.append({
                    'range': f'{col_letter}{row_num}',
                    'values': [[str(value)]]
                })
            
            if batch_updates:
                worksheet.batch_update(batch_updates)
        
        st.session_state.local_changes = {}
        st.session_state.unsaved_changes = False
        return True
        
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")
        return False

def analyze_workout_history(user_id, days=30):
    """Analysiert die Workout-Historie"""
    archive_sheet = get_sheet(ARCHIVE_SHEET)
    if not archive_sheet:
        return "Keine historischen Daten verfügbar."
    
    try:
        archive_data = archive_sheet.get_all_records()
        if not archive_data:
            return "Keine historischen Daten vorhanden."
        
        df = pd.DataFrame(archive_data)
        user_data = df[df['UserID'] == user_id]
        
        if user_data.empty:
            return "Keine Trainingsdaten vorhanden."
        
        summary = []
        exercises = user_data['Übung'].value_counts()
        
        for exercise, count in exercises.items():
            ex_data = user_data[user_data['Übung'] == exercise]
            max_weight = ex_data['Gewicht'].max() if 'Gewicht' in ex_data else 0
            avg_reps = ex_data['Wdh'].mean() if 'Wdh' in ex_data else 0
            summary.append(f"- {exercise}: Max {max_weight}kg, Ø {avg_reps:.0f} Wdh, {count}x trainiert")
        
        return "\n".join(summary[:10])
        
    except:
        return "Fehler beim Laden der Historie."

def parse_ai_plan_to_rows(plan_text, user_id):
    """Konvertiert KI-generierten Plan in Tabellenzeilen"""
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
                    
                    # Extrahiere Details
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

# ---- Hauptnavigation ----
tab1, tab2, tab3, tab4 = st.tabs(["Training", "Neue Übung", "Neuer Plan", "Daten Management"])

# ---- Tab 1: Training ----
with tab1:
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
    
    if st.session_state.user_data is not None:
        df = st.session_state.user_data
        
        if st.session_state.unsaved_changes:
            st.warning(f"⚠️ Ungespeicherte Änderungen vorhanden!")
        
        workouts = df['Workout Name'].unique()
        
        for workout in workouts:
            st.subheader(workout)
            workout_data = df[df['Workout Name'] == workout]
            
            exercises = workout_data['Übung'].unique()
            
            for exercise in exercises:
                with st.expander(f"**{exercise}**", expanded=True):
                    exercise_data = workout_data[workout_data['Übung'] == exercise].sort_values('Satz-Nr.')
                    
                    # Trainer-Hinweise
                    first_row = exercise_data.iloc[0]
                    trainer_hint = first_row.get('Hinweis vom Trainer', '')
                    if trainer_hint and trainer_hint.strip():
                        st.info(f"💬 **Trainer-Hinweis:** {trainer_hint}")
                    
                    # Sätze anzeigen
                    for idx, row in exercise_data.iterrows():
                        row_num = row['_row_num']
                        
                        if row_num in st.session_state.rows_to_delete:
                            continue
                        
                        col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 1, 0.5])
                        
                        with col1:
                            st.write(f"**Satz {int(row['Satz-Nr.'])}**")
                        
                        with col2:
                            key = (row_num, 'Gewicht')
                            current_weight = st.session_state.local_changes.get(key, row['Gewicht'])
                            
                            new_weight = st.number_input(
                                "Gewicht (kg)",
                                value=float(current_weight),
                                step=2.5,
                                key=f"w_{row_num}"
                            )
                            
                            if new_weight != row['Gewicht']:
                                st.session_state.local_changes[key] = new_weight
                                st.session_state.unsaved_changes = True
                        
                        with col3:
                            key = (row_num, 'Wdh')
                            current_reps = st.session_state.local_changes.get(key, row['Wdh'])
                            
                            new_reps = st.number_input(
                                "Wiederholungen",
                                value=int(current_reps),
                                step=1,
                                key=f"r_{row_num}"
                            )
                            
                            if new_reps != row['Wdh']:
                                st.session_state.local_changes[key] = new_reps
                                st.session_state.unsaved_changes = True
                        
                        with col4:
                            key = (row_num, 'Erledigt')
                            current_status = st.session_state.local_changes.get(key, row.get('Erledigt', 'FALSE'))
                            
                            if current_status == 'TRUE':
                                if st.button("✓ Erledigt", key=f"done_{row_num}", type="primary"):
                                    st.session_state.local_changes[key] = 'FALSE'
                                    st.session_state.unsaved_changes = True
                                    st.rerun()
                            else:
                                if st.button("Erledigt", key=f"done_{row_num}"):
                                    st.session_state.local_changes[key] = 'TRUE'
                                    st.session_state.local_changes[(row_num, 'Gewicht')] = new_weight
                                    st.session_state.local_changes[(row_num, 'Wdh')] = new_reps
                                    st.session_state.unsaved_changes = True
                                    st.rerun()
                        
                        with col5:
                            if st.button("🗑️", key=f"del_{row_num}", help="Satz löschen"):
                                st.session_state.rows_to_delete.append(row_num)
                                st.session_state.unsaved_changes = True
                                st.rerun()
                    
                    st.markdown("---")
                    
                    # Buttons und Nachricht
                    col1, col2, col3 = st.columns([1, 1, 2])
                    
                    with col1:
                        if st.button(f"➕ Satz", key=f"add_set_{exercise}_{workout}"):
                            last_row = exercise_data.iloc[-1]
                            header = list(df.columns[:-1])
                            new_row = [''] * len(header)
                            
                            for i, col in enumerate(header):
                                if col == 'Satz-Nr.':
                                    new_row[i] = str(int(last_row['Satz-Nr.']) + 1)
                                elif col == 'Erledigt':
                                    new_row[i] = 'FALSE'
                                elif col == 'Mitteilung an den Trainer':
                                    new_row[i] = ''
                                elif col in last_row:
                                    new_row[i] = str(last_row[col])
                            
                            st.session_state.rows_to_add.append(new_row)
                            st.session_state.unsaved_changes = True
                            st.rerun()
                    
                    with col2:
                        if st.button(f"🗑️ Übung", key=f"del_ex_{exercise}_{workout}"):
                            for _, row in exercise_data.iterrows():
                                if row['_row_num'] not in st.session_state.rows_to_delete:
                                    st.session_state.rows_to_delete.append(row['_row_num'])
                            st.session_state.unsaved_changes = True
                            st.rerun()
                    
                    with col3:
                        first_row_num = exercise_data.iloc[0]['_row_num']
                        msg_key = (first_row_num, 'Mitteilung an den Trainer')
                        current_msg = st.session_state.local_changes.get(msg_key, exercise_data.iloc[0].get('Mitteilung an den Trainer', ''))
                        
                        new_msg = st.text_input(
                            "💭 Nachricht an Trainer",
                            value=current_msg or '',
                            key=f"msg_{exercise}_{workout}",
                            placeholder="z.B. Schulter zwickt bei dieser Übung"
                        )
                        
                        if new_msg != exercise_data.iloc[0].get('Mitteilung an den Trainer', ''):
                            for _, row in exercise_data.iterrows():
                                st.session_state.local_changes[(row['_row_num'], 'Mitteilung an den Trainer')] = new_msg
                            st.session_state.unsaved_changes = True
                    
                    # Fortschritt
                    completed_sets = sum(1 for _, r in exercise_data.iterrows() 
                                       if st.session_state.local_changes.get((r['_row_num'], 'Erledigt'), r.get('Erledigt', 'FALSE')) == 'TRUE')
                    total_sets = len(exercise_data) - len([r for r in st.session_state.rows_to_delete if r in exercise_data['_row_num'].values])
                    
                    progress_text = f"📊 {completed_sets}/{total_sets} Sätze erledigt"
                    if completed_sets == total_sets and total_sets > 0:
                        st.success(f"✅ {progress_text}")
                    else:
                        st.caption(progress_text)
    else:
        st.info("Klicke auf '📥 Workouts laden' um deine Trainingsdaten zu sehen")

# ---- Tab 2: Neue Übung ----
with tab2:
    st.subheader("Neue Übung hinzufügen")
    
    if st.session_state.user_data is not None:
        df = st.session_state.user_data
        workouts = df['Workout Name'].unique()
        
        col1, col2 = st.columns(2)
        
        with col1:
            workout_name = st.selectbox("Workout auswählen", workouts)
            exercise_name = st.text_input("Übungsname", placeholder="z.B. Bankdrücken")
            num_sets = st.number_input("Anzahl Sätze", min_value=1, value=3)
        
        with col2:
            default_weight = st.number_input("Start-Gewicht (kg)", min_value=0.0, value=20.0, step=2.5)
            default_reps = st.number_input("Wiederholungen", min_value=1, value=10)
        
        if st.button("Übung hinzufügen", type="primary"):
            if exercise_name and workout_name:
                worksheet = get_worksheet()
                header = worksheet.row_values(1)
                
                for satz in range(1, num_sets + 1):
                    new_row = [''] * len(header)
                    for i, col in enumerate(header):
                        if col == 'UserID':
                            new_row[i] = st.session_state.userid
                        elif col == 'Datum':
                            new_row[i] = datetime.date.today().isoformat()
                        elif col == 'Workout Name':
                            new_row[i] = workout_name
                        elif col == 'Übung':
                            new_row[i] = exercise_name
                        elif col == 'Satz-Nr.':
                            new_row[i] = str(satz)
                        elif col == 'Gewicht':
                            new_row[i] = str(default_weight)
                        elif col == 'Wdh':
                            new_row[i] = str(default_reps)
                        elif col == 'Erledigt':
                            new_row[i] = 'FALSE'
                        elif col == 'Einheit':
                            new_row[i] = 'kg'
                    
                    st.session_state.rows_to_add.append(new_row)
                
                st.session_state.unsaved_changes = True
                st.success(f"'{exercise_name}' wurde hinzugefügt! Klicke auf 'Speichern' um die Änderungen zu übernehmen.")
    else:
        st.info("Lade zuerst deine Workouts im 'Training' Tab")

# ---- Tab 3: Neuer Plan ----
with tab3:
    st.subheader("Neuen Trainingsplan erstellen")
    
    if not client:
        st.error("OpenAI API Key fehlt!")
        st.stop()
    
    # Zeige Workout-Historie
    with st.expander("📊 Deine Trainingshistorie"):
        history = analyze_workout_history(st.session_state.userid)
        st.text(history)
    
    # Zeige Fragebogen-Daten
    fragebogen_data = {}
    fragebogen_sheet = get_sheet(FRAGEBOGEN_SHEET)
    if fragebogen_sheet:
        try:
            fb_data = fragebogen_sheet.get_all_records()
            user_profile = next((r for r in fb_data if r.get('UserID') == st.session_state.userid), {})
            if user_profile:
                with st.expander("📋 Deine Profildaten"):
                    for key, value in user_profile.items():
                        if key != 'UserID' and value:
                            st.write(f"**{key}:** {value}")
                fragebogen_data = user_profile
        except:
            pass
    
    # Eingabefeld für zusätzliche Wünsche
    additional_goals = st.text_area(
        "Zusätzliche Ziele/Wünsche",
        placeholder="z.B. Fokus auf Oberkörper, mehr Kraftausdauer, Vorbereitung für Wettkampf...",
        height=100
    )
    
    if st.button("🤖 Plan mit KI erstellen", type="primary"):
        with st.spinner("KI erstellt deinen personalisierten Plan..."):
            try:
                # Sammle alle Informationen
                workout_summary = analyze_workout_history(st.session_state.userid)
                
                # Erstelle Prompt
                prompt = f"""
                Erstelle einen personalisierten Trainingsplan basierend auf:
                
                BENUTZERPROFIL:
                - Fitnesslevel: {fragebogen_data.get('Fitnesslevel', 'Mittel')}
                - Ziele: {fragebogen_data.get('Ziel', 'Allgemeine Fitness')}
                - Verfügbare Tage: {fragebogen_data.get('Verfügbare_Tage', '3')}
                - Ausrüstung: {fragebogen_data.get('Ausrüstung', 'Fitnessstudio')}
                
                BISHERIGE LEISTUNGEN:
                {workout_summary}
                
                ZUSÄTZLICHE WÜNSCHE:
                {additional_goals or 'Keine speziellen Wünsche'}
                
                Erstelle einen Wochenplan mit verschiedenen Workouts.
                """
                
                system_prompt = """
                Erstelle einen strukturierten Trainingsplan mit eindeutigen Workout-Namen.
                
                Format:
                Workout-Name:
                - Übung: Anzahl Sätze, Gewicht kg, Wiederholungen Wdh
                
                Beispiel:
                Push Day A:
                - Bankdrücken: 4 Sätze, 80kg, 8-10 Wdh
                - Schulterdrücken: 3 Sätze, 40kg, 10-12 Wdh
                
                Wichtig: Jedes Workout braucht einen eindeutigen Namen!
                """
                
                # OpenAI API Call
                response = client.chat.completions.create(
                    model='gpt-4o-mini',
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                )
                
                plan_text = response.choices[0].message.content
                
                # Zeige Plan
                st.success("Plan wurde erstellt!")
                with st.expander("📋 Plan-Vorschau", expanded=True):
                    st.text(plan_text)
                
                # Parse Plan direkt
                new_rows = parse_ai_plan_to_rows(plan_text, st.session_state.userid)
                
                if new_rows:
                    st.info(f"Plan enthält {len(new_rows)} Sätze")
                    
                    # Plan aktivieren Button
                    if st.button("✅ Plan aktivieren und in Google Sheets speichern", type="primary"):
                        worksheet = get_worksheet()
                        header = worksheet.row_values(1)
                        
                        # Lösche alte Einträge des Users
                        with st.spinner("Lösche alte Einträge..."):
                            all_data = worksheet.get_all_values()
                            rows_to_delete = []
                            for i, row in enumerate(all_data[1:], 2):
                                if row[header.index("UserID")] == st.session_state.userid:
                                    rows_to_delete.append(i)
                            
                            for row_num in sorted(rows_to_delete, reverse=True):
                                worksheet.delete_rows(row_num)
                        
                        # Füge neue Zeilen ein
                        with st.spinner("Füge neuen Plan ein..."):
                            for row_data in new_rows:
                                new_row = [''] * len(header)
                                for i, col_name in enumerate(header):
                                    if col_name in row_data:
                                        new_row[i] = str(row_data[col_name])
                                worksheet.append_row(new_row)
                                time.sleep(0.1)  # Kleine Pause zwischen Zeilen
                        
                        st.success("✅ Neuer Plan wurde aktiviert!")
                        st.balloons()
                        
                        # Clear cache
                        st.session_state.user_data = None
                        st.info("Gehe zum 'Training' Tab und lade deine Workouts neu!")
                else:
                    st.error("Konnte keinen Plan aus der KI-Antwort erstellen")
                        
            except Exception as e:
                st.error(f"Fehler: {str(e)}")
                st.write("Debug Info:")
                st.write(e)

# ---- Tab 4: Daten Management ----
with tab4:
    st.subheader("Debug & Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Cache leeren"):
            st.session_state.worksheet = None
            st.session_state.user_data = None
            st.session_state.local_changes = {}
            st.session_state.unsaved_changes = False
            st.session_state.rows_to_delete = []
            st.session_state.rows_to_add = []
            st.success("Cache geleert")
    
    with col2:
        if st.button("🔍 Session State anzeigen"):
            st.json({k: v for k, v in st.session_state.items() if k != 'user_data'})

st.markdown("---")
st.caption("v8.1 - Mit funktionierender KI-Planerstellung")
