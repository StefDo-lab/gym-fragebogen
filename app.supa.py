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
    if df.empty:
        st.info("Keine Workouts gefunden.")
    else:
        for workout_name, workout_group in df.groupby("workout"):
            with st.expander(f"🏋️ {workout_name}", expanded=True):
                for exercise_name, exercise_group in workout_group.groupby("exercise"):
                    with st.expander(f"💪 {exercise_name}", expanded=False):
                        # Nachricht vom Coach anzeigen, falls vorhanden
                        coach_msg = exercise_group.iloc[0]['messageFromCoach']
                        if coach_msg and coach_msg.strip():
                            st.info(f"💬 Hinweis vom Coach: {coach_msg}")
                        
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

with tab2:
    st.subheader("Deine Analyse")
    summary, hist_df = analyze_workout_history(st.session_state.userid)
    st.write(summary)
    if not hist_df.empty:
        st.dataframe(hist_df)
