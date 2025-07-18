import streamlit as st
import datetime
import requests
import pandas as pd
import re
from openai import OpenAI
import io
import json
from supabase import create_client, Client

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

# Supabase Client für Auth
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="Workout Tracker",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="collapsed"  # Für mehr App-Feeling
)

# ---- PWA-Style Injection ----
def inject_mobile_styles():
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#FF4B4B">
    
    <style>
        /* Verstecke Streamlit-Elemente für App-Look */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden !important;}
        
        /* Reduziere Top-Padding */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            max-width: 100%;
        }
        
        /* Mobile-optimierte Buttons */
        .stButton > button {
            width: 100%;
            min-height: 50px;
            font-size: 16px;
            border-radius: 25px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        /* Bessere Touch-Targets */
        .stNumberInput > div > div > input {
            min-height: 45px;
            font-size: 18px;
            text-align: center;
        }
        
        /* iOS-Style Cards */
        .exercise-card {
            background: white;
            border-radius: 12px;
            padding: 16px;
            margin: 8px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        /* Bottom Navigation Style */
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: white;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
            padding: 8px;
            z-index: 999;
        }
        
        /* Safe Area für iOS */
        .main {
            padding-bottom: env(safe-area-inset-bottom);
        }
        
        /* Große Touch-Bereiche für Expander */
        .streamlit-expanderHeader {
            min-height: 50px;
            font-size: 18px;
        }
        
        /* Vibrant Colors */
        .stButton > button[kind="primary"] {
            background-color: #FF4B4B;
            color: white;
        }
        
        /* Success Animation */
        @keyframes success-pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .success-animation {
            animation: success-pulse 0.5s ease;
        }
    </style>
    
    <script>
        // Verhindere Zoom auf iOS
        document.addEventListener('touchstart', function(event) {
            if (event.touches.length > 1) {
                event.preventDefault();
            }
        });
        
        // Haptic Feedback (wo unterstützt)
        function triggerHaptic() {
            if (window.navigator && window.navigator.vibrate) {
                window.navigator.vibrate(10);
            }
        }
        
        // Local Storage Funktionen
        function saveToLocal(key, value) {
            localStorage.setItem(key, JSON.stringify(value));
        }
        
        function getFromLocal(key) {
            const value = localStorage.getItem(key);
            return value ? JSON.parse(value) : null;
        }
        
        // Offline-Erkennung
        window.addEventListener('online', () => {
            document.body.classList.remove('offline');
        });
        
        window.addEventListener('offline', () => {
            document.body.classList.add('offline');
            alert('Du bist offline. Änderungen werden gespeichert, sobald du wieder online bist.');
        });
    </script>
    """, unsafe_allow_html=True)

# Rufe das gleich am Anfang auf
inject_mobile_styles()

# ---- Installation Prompt ----
def show_install_prompt():
    if 'install_prompted' not in st.session_state:
        st.session_state.install_prompted = False
    
    if not st.session_state.install_prompted:
        with st.container():
            st.info("📱 **App installieren für bessere Erfahrung!**")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Installieren", type="primary"):
                    st.markdown("""
                    <script>
                    if (/iPhone|iPad|iPod/.test(navigator.userAgent)) {
                        alert('iOS: Tippe auf das Teilen-Symbol (□↑) und dann "Zum Home-Bildschirm"');
                    } else if (/Android/.test(navigator.userAgent)) {
                        alert('Android: Tippe auf die drei Punkte (⋮) und dann "App installieren"');
                    } else {
                        alert('Desktop: Nutze Chrome und klicke auf das Install-Symbol in der Adressleiste');
                    }
                    </script>
                    """, unsafe_allow_html=True)
                    st.session_state.install_prompted = True
            with col2:
                if st.button("Später"):
                    st.session_state.install_prompted = True
                    st.rerun()

# ---- OpenAI Setup ----
try:
    openai_key = st.secrets.get("openai_api_key", None)
    client = OpenAI(api_key=openai_key) if openai_key else None
except Exception as e:
    st.error(f"Fehler beim Initialisieren des OpenAI-Clients: {e}")
    client = None

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
        df["completed"] = df["completed"].astype(bool)
    
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
    
    # Erstelle Zusammenfassung
    summary = []
    if not df.empty:
        exercises = df['exercise'].unique()
        for exercise in exercises:
            ex_data = df[df['exercise'] == exercise]
            max_weight = ex_data['weight'].max()
            avg_reps = ex_data['reps'].mean()
            count = len(ex_data.groupby('date'))
            summary.append(f"- {exercise}: Max {max_weight:.1f}kg, Ø {avg_reps:.0f} Wdh, {count}x trainiert")
    
    return "\n".join(summary) if summary else "Keine Trainingshistorie gefunden.", df

def parse_ai_plan_to_rows(plan_text, user_uuid, user_name):
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = None  # Startet mit None statt "Allgemeines Training"
    lines = plan_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Verbesserte Erkennung von Workout-Namen
        # Suche nach **Text:** oder ähnlichen Mustern
        workout_patterns = [
            r'^\*\*(.+?):\*\*',  # **Workout Name:**
            r'^##\s*(.+)',       # ## Workout Name
            r'^###\s*(.+)',      # ### Workout Name
            r'^(.+):$'           # Workout Name:
        ]
        
        workout_found = False
        for pattern in workout_patterns:
            workout_match = re.match(pattern, line)
            if workout_match:
                current_workout = workout_match.group(1).strip()
                workout_found = True
                break
        
        if workout_found:
            continue
            
        # Wenn noch kein Workout definiert wurde, überspringe
        if current_workout is None:
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
                        'uuid': user_uuid, 
                        'date': current_date, 
                        'name': user_name,
                        'workout': current_workout,  # Verwendet den erkannten Workout-Namen
                        'exercise': exercise_name,
                        'set': satz, 
                        'weight': weight,
                        'reps': reps.split('-')[0] if '-' in str(reps) else reps,
                        'unit': 'kg', 
                        'type': '', 
                        'completed': False,
                        'messageToCoach': '', 
                        'messageFromCoach': explanation,
                        'rirSuggested': 0, 
                        'rirDone': 0, 
                        'generalStatementFrom': '', 
                        'generalStatementTo': '',
                        'dummy1': '', 'dummy2': '', 'dummy3': '', 'dummy4': '', 'dummy5': '',
                        'dummy6': '', 'dummy7': '', 'dummy8': '', 'dummy9': '', 'dummy10': ''
                    })
            except Exception as e:
                st.warning(f"Parsing-Fehler bei Übung '{line}': {e}")
            
            continue
    
    # Debug-Info
    if not rows and current_workout is None:
        st.warning("⚠️ Keine Workout-Namen gefunden. Bitte stelle sicher, dass die KI Workout-Namen im Format **Name:** generiert.")
    
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

def delete_exercise(user_uuid, workout_name, exercise_name):
    """Löscht alle Sätze einer Übung"""
    df = load_user_workouts(user_uuid)
    exercise_rows = df[(df['workout'] == workout_name) & (df['exercise'] == exercise_name)]
    
    success = True
    for _, row in exercise_rows.iterrows():
        if not delete_supabase_data(TABLE_WORKOUT, row['id']):
            success = False
    
    return success

def delete_workout(user_uuid, workout_name):
    """Löscht ein komplettes Workout"""
    df = load_user_workouts(user_uuid)
    workout_rows = df[df['workout'] == workout_name]
    
    success = True
    for _, row in workout_rows.iterrows():
        if not delete_supabase_data(TABLE_WORKOUT, row['id']):
            success = False
    
    return success

def archive_completed_workouts(user_uuid):
    """Archiviert alle erledigten Workouts und setzt sie zurück"""
    df = load_user_workouts(user_uuid)
    completed = df[df['completed'] == True]
    
    if completed.empty:
        return False, "Keine erledigten Workouts zum Archivieren"
    
    # Speichere in Archive
    success = True
    archived_count = 0
    reset_count = 0
    
    for _, row in completed.iterrows():
        archive_row = {
            'uuid': row['uuid'],
            'date': row['date'],
            'time': row.get('time'),
            'name': row['name'],
            'workout': row['workout'],
            'exercise': row['exercise'],
            'set': row['set'],
            'weight': row['weight'],
            'reps': row['reps'],
            'rirDone': row.get('rirDone', 0),
            'messageToCoach': row.get('messageToCoach', '')
        }
        
        if insert_supabase_data(TABLE_ARCHIVE, archive_row):
            archived_count += 1
            
            # Setze den Workout zurück (nicht löschen!)
            reset_update = {
                'completed': False,
                'messageToCoach': '',  # Lösche die Nachricht
                'time': None  # Setze Zeit zurück
            }
            
            if update_supabase_data(TABLE_WORKOUT, reset_update, row['id']):
                reset_count += 1
            else:
                success = False
        else:
            success = False
    
    return success, f"{archived_count} Einträge archiviert und {reset_count} zurückgesetzt"

def export_to_csv(df):
    """Exportiert DataFrame als CSV"""
    return df.to_csv(index=False).encode('utf-8')

# ---- Login/Auth Section ----
if 'userid' not in st.session_state:
    st.session_state['userid'] = None
    st.session_state['user_email'] = None

if not st.session_state.userid:
    # Zeige Install-Prompt beim ersten Besuch
    show_install_prompt()
    
    st.markdown("<h2 style='text-align: center;'>Willkommen beim Workout Tracker! 💪</h2>", unsafe_allow_html=True)
    
    # Nur Login, keine Registrierung (da diese im Fragebogen erfolgt)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("📝 Bitte melde dich mit deinem Account an. Falls du noch keinen Account hast, registriere dich bitte zuerst beim Fragebogen.")
        
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="deine@email.de")
            password = st.text_input("Passwort", type="password", placeholder="••••••••")
            
            if st.form_submit_button("Anmelden", type="primary", use_container_width=True):
                if email and password:
                    try:
                        # Supabase Auth Login
                        response = supabase.auth.sign_in_with_password({
                            "email": email,
                            "password": password
                        })
        
                        if response.user:
                            auth_uuid = response.user.id
                            st.session_state.user_email = email
    
                            # Hole die richtige UUID aus der questionaire Tabelle über die Email
                            user_profile_data = get_supabase_data(
                                TABLE_QUESTIONNAIRE, 
                                f"email=eq.{email}"
                            )
    
                            if user_profile_data and len(user_profile_data) > 0:
                                # Verwende die UUID aus der questionaire Tabelle
                                data_uuid = user_profile_data[0]['uuid']
                                st.session_state.userid = data_uuid
        
                                st.success("Erfolgreich angemeldet!")
                                st.rerun()  # Wichtig: st.rerun() ist jetzt wieder aktiv!
                            else:
                                st.error("Benutzerprofil nicht gefunden. Bitte erst Fragebogen ausfüllen!")
                        else:
                            st.error("Anmeldung fehlgeschlagen")

                            
                    except Exception as e:
                        if "Invalid login credentials" in str(e):
                            st.error("Ungültige Email oder Passwort")
                        else:
                            st.error(f"Fehler: {str(e)}")
                else:
                    st.warning("Bitte Email und Passwort eingeben")
        
        # Links zu Fragebogen und Passwort-Reset
        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown(
                "<p style='text-align: center;'>"
                "<a href='/fragebogen' target='_blank'>→ Zur Registrierung</a>"
                "</p>", 
                unsafe_allow_html=True
            )
        with col_right:
            st.markdown(
                "<p style='text-align: center;'>"
                "<a href='#' onclick='alert(\"Bitte kontaktiere den Support für einen Passwort-Reset.\")'>Passwort vergessen?</a>"
                "</p>", 
                unsafe_allow_html=True
            )
    
    st.stop()

# ---- Nach erfolgreichem Login ----
# Einfacher Titel ohne Header-Buttons
st.markdown("<h1 style='text-align: center; margin: 0;'>💪 Workout Tracker</h1>", unsafe_allow_html=True)

# Sidebar Info mit Email
st.sidebar.success(f"Eingeloggt als {st.session_state.get('user_email', st.session_state.userid)}")

# Logout-Button in der Sidebar
if st.sidebar.button("🚪 Abmelden"):
    try:
        supabase.auth.sign_out()
    except:
        pass
    st.session_state.userid = None
    st.session_state.user_email = None
    st.rerun()

# Mobile-optimierte Tabs
tab_names = ["🏋️ Training", "🤖 KI-Plan", "📊 Stats", "⚙️ Mehr"]
tab1, tab2, tab3, tab4 = st.tabs(tab_names)

with tab1:
    st.subheader("Deine Workouts")
    df = load_user_workouts(st.session_state.userid)
    
    # Hole Benutzername für neue Workouts
    profile = get_user_profile(st.session_state.userid)
    user_name = profile.get('name', 'Unbekannt')
    
    if df.empty:
        st.info("Keine Workouts gefunden. Füge dein erstes Workout hinzu!")
    else:
        # Export-Button
        col1, col2 = st.columns([4, 1])
        with col2:
            csv = export_to_csv(df)
            st.download_button(
                label="📥 Export CSV",
                data=csv,
                file_name=f"workout_{datetime.date.today()}.csv",
                mime="text/csv"
            )
        
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
                        
                        # Nachricht an den Coach
                        with st.expander("💬 Nachricht an Coach", expanded=False):
                            current_message = exercise_group.iloc[0].get('messageToCoach', '')
                            message = st.text_area(
                                "Feedback zur Übung",
                                value=current_message,
                                key=f"msg_{exercise_name}_{workout_name}",
                                placeholder="z.B. Gewicht war zu leicht, Technik-Fragen, etc."
                            )
                            if st.button("Nachricht senden", key=f"send_msg_{exercise_name}_{workout_name}"):
                                # Update alle Sätze dieser Übung mit der Nachricht
                                success = True
                                for _, row in exercise_group.iterrows():
                                    update = {"messageToCoach": message}
                                    if not update_supabase_data(TABLE_WORKOUT, update, row['id']):
                                        success = False
                                if success:
                                    st.success("Nachricht gesendet!")
                                    st.rerun()
                        
                        # Übung löschen Button am Ende
                        st.markdown("---")
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col3:
                            if st.button("🗑️ Übung löschen", key=f"del_ex_{exercise_name}_{workout_name}"):
                                if delete_exercise(st.session_state.userid, workout_name, exercise_name):
                                    st.success(f"Übung '{exercise_name}' gelöscht!")
                                    st.rerun()
                
                # Formular zum Hinzufügen einer neuen Übung in Expander
                with st.expander("➕ Neue Übung hinzufügen", expanded=False):
                    with st.form(key=f"add_exercise_form_{workout_name}"):
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
                
                # Workout löschen Button am Ende
                st.markdown("---")
                col1, col2, col3 = st.columns([3, 1, 1])
                with col3:
                    if st.button(f"🗑️ Workout löschen", key=f"del_workout_{workout_name}"):
                        if delete_workout(st.session_state.userid, workout_name):
                            st.success(f"Workout '{workout_name}' gelöscht!")
                            st.rerun()
    
    # Formular für neues Workout in Expander
    with st.expander("🆕 Neues Workout erstellen", expanded=False):
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
    st.subheader("🤖 Neuen Trainingsplan mit KI erstellen")
    
    if not client:
        st.error("OpenAI API Key ist nicht konfiguriert.")
    else:
        # Lade Profil und History
        profile = get_user_profile(st.session_state.userid)
        history_summary, _ = analyze_workout_history(st.session_state.userid)
        
        with st.expander("Deine Daten für die KI", expanded=True):
            if profile:
                st.info("Dein Profil wurde gefunden:")
                relevant_keys = ["name", "gender", "height", "weight", "experience", "goals", "health_issues"]
                profile_display = {k: v for k, v in profile.items() if k in relevant_keys and v}
                st.json(profile_display)
            
            st.text_area("Trainingshistorie:", value=history_summary, height=150, disabled=True)
        
        additional_info = st.text_area(
            "Zusätzliche Wünsche für den Plan:",
            placeholder="z.B. 3er Split, Fokus auf Oberkörper, keine Kniebeugen wegen Knieproblemen..."
        )
        
        col1, col2, col3 = st.columns(3)
        with col1:
            training_days = st.selectbox("Trainingstage pro Woche", [2, 3, 4, 5, 6], index=1)
        with col2:
            split_type = st.selectbox("Split-Typ", ["Ganzkörper", "2er Split", "3er Split", "Push/Pull/Legs", "Individuell"])
        with col3:
            focus = st.selectbox("Fokus", ["Ausgewogen", "Kraft", "Hypertrophie", "Kraftausdauer"])
        
        if st.button("🤖 Plan generieren", type="primary"):
            with st.spinner("KI erstellt deinen personalisierten Plan..."):
                # Erstelle Prompt
                if "Keine" in history_summary:
                    weight_instruction = "Setze alle Gewichte auf 0 kg, da keine Trainingshistorie vorhanden ist."
                else:
                    weight_instruction = "Basiere die Gewichte auf der Trainingshistorie."
                
                prompt = f"""
                Erstelle einen Trainingsplan für folgende Person:
                
                Profil: {profile}
                Trainingshistorie: {history_summary}
                Zusätzliche Wünsche: {additional_info}
                
                Erstelle GENAU {training_days} Trainingstage pro Woche.
                Split-Typ: {split_type}
                Fokus: {focus}
                
                WICHTIGE FORMATIERUNG:
                1. Jeder Trainingstag MUSS mit einem Workout-Namen beginnen im Format: **Name des Workouts:**
                2. Verwende aussagekräftige Namen wie:
                   - **Oberkörper Push:**
                   - **Unterkörper Pull:**
                   - **Ganzkörper A:**
                   - **Brust & Trizeps:**
                   NICHT nur "Workout-Name"!
                3. Format pro Übung: - Übungsname: X Sätze, Y Wdh, Z kg (Fokus: Kurze Erklärung)
                4. {weight_instruction}
                5. Keine zusätzlichen Erklärungen oder Texte am Ende
                
                Beispiel-Format:
                **Oberkörper Push:**
                - Bankdrücken: 3 Sätze, 8-10 Wdh, 60 kg (Fokus: Brustmuskulatur)
                - Schulterdrücken: 3 Sätze, 10-12 Wdh, 30 kg (Fokus: Vordere Schulter)
                
                Erstelle nur die Workouts mit den Übungen, sonst nichts.
                """
                
                try:
                    response = client.chat.completions.create(
                        model='gpt-4o-mini',
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        max_tokens=2000
                    )
                    
                    plan_text = response.choices[0].message.content
                    st.session_state['ai_plan'] = plan_text
                    st.session_state['ai_plan_rows'] = parse_ai_plan_to_rows(
                        plan_text,
                        st.session_state.userid,
                        profile.get('name', 'Unbekannt')
                    )
                    
                except Exception as e:
                    st.error(f"Fehler bei der KI-Generierung: {e}")
        
        # Zeige generierten Plan
        if 'ai_plan' in st.session_state and st.session_state['ai_plan']:
            st.markdown("### Generierter Plan")
            st.text_area("KI-Plan:", value=st.session_state['ai_plan'], height=400, disabled=True)
            
            if st.session_state.get('ai_plan_rows'):
                st.info(f"Der Plan enthält {len(st.session_state['ai_plan_rows'])} Sätze")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Plan aktivieren", type="primary"):
                        # Lösche aktuelle Workouts
                        df = load_user_workouts(st.session_state.userid)
                        if not df.empty:
                            for _, row in df.iterrows():
                                delete_supabase_data(TABLE_WORKOUT, row['id'])
                        
                        # Füge neue Workouts hinzu
                        success = True
                        for row_data in st.session_state['ai_plan_rows']:
                            if not insert_supabase_data(TABLE_WORKOUT, row_data):
                                success = False
                                break
                        
                        if success:
                            st.success("Neuer Plan wurde aktiviert!")
                            st.balloons()
                            del st.session_state['ai_plan']
                            del st.session_state['ai_plan_rows']
                            st.rerun()
                        else:
                            st.error("Fehler beim Aktivieren des Plans")
                
                with col2:
                    if st.button("❌ Plan verwerfen"):
                        del st.session_state['ai_plan']
                        del st.session_state['ai_plan_rows']
                        st.rerun()

with tab3:
    st.subheader("📈 Deine Trainingsanalyse")
    
    _, archive_df = analyze_workout_history(st.session_state.userid)
    
    if archive_df.empty:
        st.info("Noch keine archivierten Daten vorhanden. Trainiere und archiviere zuerst einige Workouts.")
    else:
        # Berechne Volumen
        archive_df['volume'] = archive_df['weight'] * archive_df['reps']
        
        # Übungsauswahl
        exercises = sorted(archive_df['exercise'].unique())
        selected_exercise = st.selectbox("Wähle eine Übung für die Analyse:", exercises)
        
        if selected_exercise:
            exercise_df = archive_df[archive_df['exercise'] == selected_exercise]
            
            # Konvertiere date zu datetime
            exercise_df['date'] = pd.to_datetime(exercise_df['date'])
            
            # Gruppiere nach Datum
            daily_stats = exercise_df.groupby('date').agg({
                'weight': 'max',
                'reps': 'mean',
                'volume': 'sum'
            }).reset_index()
            
            # Visualisierungen
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Gewichtsentwicklung")
                st.line_chart(daily_stats.set_index('date')['weight'])
            
            with col2:
                st.markdown("#### Volumen pro Training")
                st.bar_chart(daily_stats.set_index('date')['volume'])
            
            # Statistiken
            st.markdown("#### Statistiken")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Max Gewicht", f"{exercise_df['weight'].max():.1f} kg")
            with col2:
                st.metric("Ø Wiederholungen", f"{exercise_df['reps'].mean():.1f}")
            with col3:
                st.metric("Trainings", len(daily_stats))
            with col4:
                if len(daily_stats) > 1:
                    weight_change = daily_stats.iloc[-1]['weight'] - daily_stats.iloc[0]['weight']
                    st.metric("Fortschritt", f"{weight_change:+.1f} kg")

with tab4:
    st.subheader("⚙️ Verwaltung")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Archivierung")
        st.info("Erledigte Workouts werden normalerweise automatisch um 23:59 Uhr archiviert.")
        
        if st.button("📦 Manuell archivieren", type="primary"):
            success, message = archive_completed_workouts(st.session_state.userid)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.warning(message)
    
    with col2:
        st.markdown("### Daten-Export")
        
        # Export aktuelle Workouts
        df = load_user_workouts(st.session_state.userid)
        if not df.empty:
            csv = export_to_csv(df)
            st.download_button(
                label="📥 Aktuelle Workouts exportieren",
                data=csv,
                file_name=f"workouts_{datetime.date.today()}.csv",
                mime="text/csv"
            )
        
        # Export Archiv
        _, archive_df = analyze_workout_history(st.session_state.userid)
        if not archive_df.empty:
            csv_archive = export_to_csv(archive_df)
            st.download_button(
                label="📥 Trainingshistorie exportieren",
                data=csv_archive,
                file_name=f"training_history_{datetime.date.today()}.csv",
                mime="text/csv"
            )
