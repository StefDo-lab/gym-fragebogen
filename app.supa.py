import streamlit as st
import datetime
import requests
import pandas as pd
import re

# ---- Configuration ----
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_service_role_key"]
TABLE_WORKOUT = "workouts"
TABLE_ARCHIVE = "workout_history"
TABLE_QUESTIONNAIRE = "questionaire"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

st.set_page_config(page_title="Workout Tracker", layout="wide")
st.title("Workout Tracker")

def get_supabase_data(table, filters=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if filters:
        url += f"?{filters}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Fehler beim Abrufen der Daten aus {table}: {response.text}")
        return []

def insert_supabase_data(table, data):
    response = requests.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=data)
    return response.status_code == 201

def update_supabase_data(table, updates, row_id):
    response = requests.patch(f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}", headers=HEADERS, json=updates)
    if response.status_code != 204:
        st.error(f"Update-Fehler: {response.text}")
    return response.status_code == 204

def delete_supabase_data(table, row_id):
    response = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}", headers=HEADERS)
    return response.status_code == 204

def get_user_profile(user_uuid):
    data = get_supabase_data(TABLE_QUESTIONNAIRE, f"uuid=eq.{user_uuid}")
    return data[0] if data else {}

def load_user_workouts(user_uuid):
    data = get_supabase_data(TABLE_WORKOUT, f"uuid=eq.{user_uuid}")
    df = pd.DataFrame(data) if data else pd.DataFrame()
    if "weight" in df.columns:
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
    if "reps" in df.columns:
        df["reps"] = pd.to_numeric(df["reps"], errors="coerce").fillna(0)
    if "completed" in df.columns:
        df["completed"] = df["completed"].apply(lambda x: True if x is True else False)
    
    # Sortiere nach ID, um die ursprüngliche Reihenfolge beizubehalten
    if not df.empty and 'id' in df.columns:
        df = df.sort_values('id')
    
    return df

def analyze_workout_history(user_uuid):
    data = get_supabase_data(TABLE_ARCHIVE, f"uuid=eq.{user_uuid}")
    if not data:
        return "Keine Archiv-Daten verfügbar.", pd.DataFrame()
    df = pd.DataFrame(data)
    if "weight" in df.columns:
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
    if "reps" in df.columns:
        df["reps"] = pd.to_numeric(df["reps"], errors="coerce").fillna(0)
    return f"{len(df)} Einträge gefunden.", df

def parse_ai_plan_to_rows(plan_text, user_uuid, user_name):
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = "Allgemeines Training"
    lines = plan_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        workout_match = re.match(r'^\*\*(.+?):\*\*', line)
        if workout_match:
            current_workout = workout_match.group(1).strip()
            continue
        exercise_match = re.match(r'^\s*[-*]\s*(.+?):\s*(.*)', line)
        if exercise_match:
            exercise_name = exercise_match.group(1).strip()
            details = exercise_match.group(2).strip()
            try:
                sets, weight, reps, explanation = 3, 0.0, "10", ""
                explanation_match = re.search(r'\((?:Erklärung|Fokus):\s*(.+?)\)', details)
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                    details = details.replace(explanation_match.group(0), '').strip()
                sets_match = re.search(r'(\d+)\s*(?:x|[Ss]ätze|[Ss]ets)', details)
                if sets_match:
                    sets = int(sets_match.group(1))
                weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                if weight_match:
                    weight = float(weight_match.group(1).replace(',', '.'))
                elif "körpergewicht" in details.lower() or "bw" in details.lower():
                    weight = 0.0
                reps_match = re.search(r'(\d+\s*-\s*\d+|\d+)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match:
                    reps = reps_match.group(1).strip()
                for satz in range(1, sets + 1):
                    rows.append({
                        'uuid': user_uuid, 'date': current_date, 'name': user_name,
                        'workout': current_workout, 'exercise': exercise_name,
                        'set': satz, 'weight': weight,
                        'reps': reps.split('-')[0] if '-' in str(reps) else reps,
                        'unit': 'kg', 'type': '', 'completed': False,
                        'messageToCoach': '', 'messageFromCoach': explanation,
                        'rirSuggested': 0, 'rirDone': 0, 'generalStatementFrom': '', 'generalStatementTo': '',
                        'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
                        'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
                    })
            except Exception as e:
                st.warning(f"Parsing-Fehler bei Übung '{line}': {e}")
            continue
    return rows

def add_set_to_exercise(user_uuid, exercise_data, new_set_number):
    """Fügt einen neuen Satz zu einer Übung hinzu"""
    new_row = {
        'uuid': user_uuid,
        'date': str(exercise_data['date']),
        'name': str(exercise_data['name']),
        'workout': str(exercise_data['workout']),
        'exercise': str(exercise_data['exercise']),
        'set': int(new_set_number),
        'weight': float(exercise_data['weight']),
        'reps': str(exercise_data['reps']),
        'unit': 'kg',
        'type': '',
        'completed': False,
        'messageToCoach': '',
        'messageFromCoach': str(exercise_data.get('messageFromCoach', '')),
        'rirSuggested': 0,
        'rirDone': 0,
        'time': None,
        'generalStatementFrom': '',
        'generalStatementTo': '',
        'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
        'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
    }
    return insert_supabase_data(TABLE_WORKOUT, new_row)

def add_exercise_to_workout(user_uuid, workout_name, exercise_name, sets=3, weight=0, reps="10"):
    """Fügt eine neue Übung zu einem Workout hinzu"""
    # Hole die aktuellen Daten für dieses Workout
    df = load_user_workouts(user_uuid)
    workout_data = df[df['workout'] == workout_name].iloc[0] if not df[df['workout'] == workout_name].empty else None
    
    if workout_data is None:
        st.error("Workout nicht gefunden")
        return False
    
    success = True
    for set_num in range(1, sets + 1):
        new_row = {
            'uuid': user_uuid,
            'date': str(workout_data['date']),
            'name': str(workout_data['name']),
            'workout': workout_name,
            'exercise': exercise_name,
            'set': set_num,
            'weight': weight,
            'reps': str(reps),
            'unit': 'kg',
            'type': '',
            'completed': False,
            'messageToCoach': '',
            'messageFromCoach': '',
            'rirSuggested': 0,
            'rirDone': 0,
            'time': None,
            'generalStatementFrom': '',
            'generalStatementTo': '',
            'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
            'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
        }
        if not insert_supabase_data(TABLE_WORKOUT, new_row):
            success = False
            break
    
    return success

def add_workout(user_uuid, user_name, workout_name, exercise_name, sets=3, weight=0, reps="10"):
    """Fügt ein neues Workout mit einer ersten Übung hinzu"""
    current_date = datetime.date.today().isoformat()
    
    success = True
    for set_num in range(1, sets + 1):
        new_row = {
            'uuid': user_uuid,
            'date': current_date,
            'name': user_name,
            'workout': workout_name,
            'exercise': exercise_name,
            'set': set_num,
            'weight': weight,
            'reps': str(reps),
            'unit': 'kg',
            'type': '',
            'completed': False,
            'messageToCoach': '',
            'messageFromCoach': '',
            'rirSuggested': 0,
            'rirDone': 0,
            'time': None,
            'generalStatementFrom': '',
            'generalStatementTo': '',
            'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
            'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
        }
        if not insert_supabase_data(TABLE_WORKOUT, new_row):
            success = False
            break
    
    return success

if 'userid' not in st.session_state:
    st.session_state['userid'] = None
if not st.session_state.userid:
    uid = st.text_input("UserID", type="password")
    if st.button("Login"):
        st.session_state.userid = uid.strip()
        st.rerun()
    st.stop()

st.sidebar.success(f"Eingeloggt als {st.session_state.userid}")

tab1, tab2 = st.tabs(["💪 Training", "📈 Analyse"])

with tab1:
    st.subheader("Deine Workouts")
    df = load_user_workouts(st.session_state.userid)
    
    # Hole Benutzername für neue Workouts
    profile = get_user_profile(st.session_state.userid)
    user_name = profile.get('name', 'Unbekannt')
    
    if df.empty:
        st.info("Keine Workouts gefunden. Füge dein erstes Workout hinzu!")
    else:
        # Gruppiere nach Workout, behalte aber die Reihenfolge bei
        workout_order = df.groupby('workout').first().sort_values('id').index
        
        for workout_name in workout_order:
            workout_group = df[df['workout'] == workout_name]
            with st.expander(f"🏋️ {workout_name}", expanded=True):
                # Gruppiere nach Übung, behalte aber die Reihenfolge bei
                exercise_order = workout_group.groupby('exercise').first().sort_values('id').index
                
                for exercise_name in exercise_order:
                    exercise_group = workout_group[workout_group['exercise'] == exercise_name]
                    with st.expander(f"💪 {exercise_name}", expanded=False):
                        # Nachricht vom Coach anzeigen, falls vorhanden
                        coach_msg = exercise_group.iloc[0]['messageFromCoach']
                        if coach_msg and coach_msg.strip():
                            st.info(f"💬 Hinweis vom Coach: {coach_msg}")
                        
                        # Sortiere Sätze nach Satz-Nummer
                        exercise_group = exercise_group.sort_values('set')
                        
                        for idx, row in exercise_group.iterrows():
                            completed = row['completed']
                            bg_color = "#d4edda" if completed else "#f8f9fa"
                            
                            with st.container():
                                st.markdown(
                                    f"""<div style='background-color: {bg_color}; 
                                    padding: 15px; 
                                    border-radius: 8px; 
                                    margin-bottom: 10px;
                                    border: 1px solid {"#c3e6cb" if completed else "#dee2e6"};'>""", 
                                    unsafe_allow_html=True
                                )
                                
                                col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 2])
                                
                                with col1:
                                    st.markdown(f"**Satz {row['set']}**")
                                
                                with col2:
                                    # Bearbeitbares Gewicht
                                    new_weight = st.number_input(
                                        "Gewicht (kg)", 
                                        value=float(row['weight']), 
                                        min_value=0.0,
                                        step=0.5,
                                        key=f"weight_{row['id']}",
                                        disabled=completed
                                    )
                                
                                with col3:
                                    # Bearbeitbare Wiederholungen
                                    try:
                                        reps_value = int(row['reps'])
                                    except:
                                        reps_value = 10
                                    
                                    new_reps = st.number_input(
                                        "Wiederholungen", 
                                        value=reps_value,
                                        min_value=1,
                                        step=1,
                                        key=f"reps_{row['id']}",
                                        disabled=completed
                                    )
                                
                                with col4:
                                    # RIR (Reps in Reserve)
                                    try:
                                        rir_value = int(row['rirDone']) if row['rirDone'] else 0
                                    except:
                                        rir_value = 0
                                    
                                    rir_done = st.number_input(
                                        "RIR", 
                                        value=rir_value,
                                        min_value=0,
                                        max_value=10,
                                        step=1,
                                        key=f"rir_{row['id']}",
                                        help="Reps in Reserve - Wie viele Wiederholungen hättest du noch schaffen können?",
                                        disabled=completed
                                    )
                                
                                with col5:
                                    if not completed:
                                        # Speichern und als erledigt markieren
                                        if st.button("✅ Speichern & Erledigt", key=f"save_{row['id']}"):
                                            update = {
                                                "weight": new_weight,
                                                "reps": str(new_reps),
                                                "rirDone": rir_done,
                                                "completed": True,
                                                "time": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                            }
                                            
                                            success = update_supabase_data(TABLE_WORKOUT, update, row['id'])
                                            if success:
                                                st.success("Gespeichert!")
                                                st.rerun()
                                            else:
                                                st.error("Fehler beim Speichern")
                                    else:
                                        # Option zum Zurücksetzen
                                        if st.button("↩️ Zurücksetzen", key=f"reset_{row['id']}"):
                                            update = {"completed": False}
                                            success = update_supabase_data(TABLE_WORKOUT, update, row['id'])
                                            if success:
                                                st.rerun()
                                
                                st.markdown("</div>", unsafe_allow_html=True)
                        
                        # Buttons für Satzverwaltung NACH allen Sätzen
                        col_add, col_del, col_space = st.columns([1, 1, 3])
                        with col_add:
                            if st.button("➕ Satz hinzufügen", key=f"add_set_{exercise_name}_{workout_name}"):
                                last_set = exercise_group.iloc[-1]
                                new_set_number = exercise_group['set'].max() + 1
                                if add_set_to_exercise(st.session_state.userid, last_set.to_dict(), new_set_number):
                                    st.success("Satz hinzugefügt!")
                                    st.rerun()
                        
                        with col_del:
                            if len(exercise_group) > 1:
                                if st.button("➖ Letzten Satz löschen", key=f"del_set_{exercise_name}_{workout_name}"):
                                    last_set_id = exercise_group.iloc[-1]['id']
                                    if delete_supabase_data(TABLE_WORKOUT, last_set_id):
                                        st.success("Satz gelöscht!")
                                        st.rerun()
                        
                        # Optionale Nachricht an den Coach für die gesamte Übung
                        with st.expander("💬 Nachricht an Coach", expanded=False):
                            message = st.text_area(
                                "Feedback zur Übung",
                                key=f"msg_{exercise_name}_{workout_name}",
                                placeholder="z.B. Gewicht war zu leicht, Technik-Fragen, etc."
                            )
                            if st.button("Nachricht senden", key=f"send_msg_{exercise_name}_{workout_name}"):
                                # Hier könntest du die Nachricht für alle Sätze dieser Übung speichern
                                st.info("Nachricht-Funktion wird noch implementiert")
                
                # Formular zum Hinzufügen einer neuen Übung NACH allen Übungen
                st.markdown("---")
                with st.form(key=f"add_exercise_form_{workout_name}"):
                    st.markdown("**Neue Übung hinzufügen:**")
                    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                    with col1:
                        new_exercise_name = st.text_input("Übungsname", placeholder="z.B. Bizeps Curls")
                    with col2:
                        new_exercise_sets = st.number_input("Sätze", min_value=1, value=3)
                    with col3:
                        new_exercise_weight = st.number_input("Gewicht", min_value=0.0, value=0.0, step=0.5)
                    with col4:
                        new_exercise_reps = st.number_input("Wdh", min_value=1, value=10)
                    
                    if st.form_submit_button("➕ Übung hinzufügen"):
                        if new_exercise_name:
                            if add_exercise_to_workout(
                                st.session_state.userid, 
                                workout_name, 
                                new_exercise_name, 
                                new_exercise_sets, 
                                new_exercise_weight, 
                                str(new_exercise_reps)
                            ):
                                st.success(f"Übung '{new_exercise_name}' hinzugefügt!")
                                st.rerun()
                        else:
                            st.error("Bitte gib einen Übungsnamen ein")
    
    # Formular für neues Workout GANZ UNTEN
    st.markdown("---")
    st.markdown("### Neues Workout erstellen")
    with st.form(key="add_workout_form"):
        col1, col2 = st.columns([2, 3])
        with col1:
            new_workout_name = st.text_input("Workout Name", placeholder="z.B. Oberkörper Tag")
        with col2:
            st.markdown("**Erste Übung:**")
        
        col3, col4, col5, col6 = st.columns([3, 1, 1, 1])
        with col3:
            first_exercise_name = st.text_input("Übungsname", placeholder="z.B. Bankdrücken")
        with col4:
            first_exercise_sets = st.number_input("Sätze", min_value=1, value=3)
        with col5:
            first_exercise_weight = st.number_input("Gewicht", min_value=0.0, value=0.0, step=0.5)
        with col6:
            first_exercise_reps = st.number_input("Wdh", min_value=1, value=10)
        
        if st.form_submit_button("🆕 Workout erstellen"):
            if new_workout_name and first_exercise_name:
                if add_workout(
                    st.session_state.userid,
                    user_name,
                    new_workout_name,
                    first_exercise_name,
                    first_exercise_sets,
                    first_exercise_weight,
                    str(first_exercise_reps)
                ):
                    st.success(f"Workout '{new_workout_name}' erstellt!")
                    st.rerun()
            else:
                st.error("Bitte gib sowohl einen Workout-Namen als auch eine erste Übung ein")

with tab2:
    st.subheader("Deine Analyse")
    summary, hist_df = analyze_workout_history(st.session_state.userid)
    st.write(summary)
    if not hist_df.empty:
        st.dataframe(hist_df)
