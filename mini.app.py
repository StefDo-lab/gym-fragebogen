import streamlit as st
import datetime
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
import time
import re

# ---- Configuration ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "Tabellenblatt1"
ARCHIVE_SHEET = "Workout_archiv"
FRAGEBOGEN_SHEET = "fragebogen"

# ---- App UI ----
st.set_page_config(page_title="Workout Tracker", layout="wide")
st.title("Workout Tracker")

# ---- Session State Initialization ----
def init_session_state():
    """Initializes the session state if not already done."""
    defaults = {
        'userid': None,
        'local_changes': {},
        'unsaved_changes': False,
        'user_data': None,
        'rows_to_delete': [],
        'rows_to_add': [],
        'plan_text': None,
        'new_plan_rows': []
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ---- OpenAI Setup ----
try:
    openai_key = st.secrets.get("openai_api_key", None)
    client = OpenAI(api_key=openai_key) if openai_key else None
except Exception as e:
    st.error(f"Fehler beim Initialisieren des OpenAI-Clients: {e}")
    client = None

# ---- Login & Logout ----
if st.session_state.userid:
    st.sidebar.info(f"Eingeloggt als: **{st.session_state.userid}**")
    if st.sidebar.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

if not st.session_state.userid:
    st.subheader("Login")
    uid = st.text_input("UserID", type="password")
    
    if st.button("Login"):
        if uid:
            st.session_state.userid = uid.strip()
            st.success(f"Eingeloggt als {st.session_state.userid}")
            st.rerun()
    st.stop()

# ---- Google Sheets Connection & Data Logic ----
@st.cache_resource
def get_gspread_client():
    """Establishes and caches an authorized connection to Google Sheets."""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            st.secrets["gcp_service_account"], scopes
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Fehler bei der Google-Authentifizierung: {e}")
        return None

def get_sheet_data(sheet_name):
    """Fetches all data from a worksheet. No Caching to ensure fresh data."""
    try:
        gspread_client = get_gspread_client()
        if not gspread_client: return None
        ss = gspread_client.open(SHEET_NAME)
        worksheet = ss.worksheet(sheet_name)
        return worksheet.get_all_values()
    except gspread.exceptions.WorksheetNotFound:
        st.warning(f"Arbeitsblatt '{sheet_name}' nicht gefunden.")
        return None
    except Exception as e:
        st.error(f"Fehler beim Laden von '{sheet_name}': {e}")
        return None

def get_main_worksheet():
    """Returns the gspread worksheet object for write operations."""
    try:
        gspread_client = get_gspread_client()
        if not gspread_client: return None
        ss = gspread_client.open(SHEET_NAME)
        return ss.worksheet(WORKSHEET_NAME)
    except Exception as e:
        st.error(f"Konnte Schreibzugriff auf Haupt-Arbeitsblatt nicht erhalten: {e}")
        return None

def get_user_profile(user_id):
    """Fetches and filters the user profile from the questionnaire sheet."""
    all_fb_data = get_sheet_data(FRAGEBOGEN_SHEET)
    if not all_fb_data:
        return {}
        
    header = all_fb_data[0]
    records = [dict(zip(header, row)) for row in all_fb_data[1:]]
    user_profile = next((r for r in records if r.get('UserID', '').strip() == user_id), {})

    relevant_keys = [
        "Vorname", "Nachname", "Geschlecht", "Größe (cm)", "Gewicht (kg)", 
        "Körperfettanteil (%)", "Krafttraining-Erfahrung", "Trainingsziele", 
        "Ziel-Details", "OP letzte 12-18 Monate", "OP-Details", 
        "Ausstrahlende Schmerzen", "Schmerz-Details", "Bandscheibenvorfall letzte 6-12 Monate",
        "Bandscheiben-Details", "Sonstige Gesundheitsprobleme", "Konkrete Ziele", 
        "Gesundheitszustand", "Einschränkungen", "Schmerzen/Beschwerden", "Stresslevel", 
        "Schlafdauer (h)", "Ernährung", "Motivationslevel", "Trainingshäufigkeit (pro Woche)"
    ]
    
    filtered_profile = {key: user_profile.get(key) for key in relevant_keys if user_profile.get(key)}
    
    filtered_profile['FullName'] = f"{user_profile.get('Vorname', '')} {user_profile.get('Nachname', '')}".strip()
    
    return filtered_profile


def load_user_workouts():
    """
    Loads and filters the workouts of the logged-in user.
    Only loads the plan with the most recent timestamp to avoid showing old data.
    """
    all_data = get_sheet_data(WORKSHEET_NAME)
    if all_data is None: return None
    if len(all_data) < 2: return pd.DataFrame()
        
    header = all_data[0]
    df_columns = header + ['_row_num']
    
    try:
        uid_col_idx = header.index("UserID")
        date_col_idx = header.index("Datum")
    except ValueError as e:
        st.error(f"Benötigte Spalte nicht gefunden: {e}")
        return None

    user_rows = [row + [i + 2] for i, row in enumerate(all_data[1:]) if len(row) > uid_col_idx and row[uid_col_idx] == st.session_state.userid]
    
    if not user_rows: return pd.DataFrame(columns=df_columns)

    valid_timestamps = [row[date_col_idx] for row in user_rows if len(row) > date_col_idx and row[date_col_idx]]
    if not valid_timestamps:
        return pd.DataFrame(user_rows, columns=df_columns)

    latest_timestamp = max(valid_timestamps)
    latest_plan_rows = [row for row in user_rows if len(row) > date_col_idx and row[date_col_idx] == latest_timestamp]

    df = pd.DataFrame(latest_plan_rows, columns=df_columns)
    
    for col in ['Gewicht', 'Wdh', 'Satz-Nr.']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df
        
def save_changes():
    """Saves all local changes (deletions, additions, updates)."""
    worksheet = get_main_worksheet()
    if not worksheet:
        return False, "Keine Verbindung zum Arbeitsblatt."
    
    try:
        # DELETE via Batch Update
        if st.session_state.rows_to_delete:
            requests = []
            for row_num in sorted(list(set(st.session_state.rows_to_delete)), reverse=True):
                requests.append({
                    "deleteDimension": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "ROWS",
                            "startIndex": row_num - 1,
                            "endIndex": row_num
                        }
                    }
                })
            
            if requests:
                worksheet.spreadsheet.batch_update({'requests': requests})
            st.session_state.rows_to_delete = []

        # ADD
        if st.session_state.rows_to_add:
            worksheet.append_rows(st.session_state.rows_to_add, value_input_option='USER_ENTERED')
            st.session_state.rows_to_add = []
        
        # UPDATE
        if st.session_state.local_changes:
            batch_updates = []
            header = worksheet.row_values(1)
            for (row_num, col_name), value in st.session_state.local_changes.items():
                try:
                    col_idx = header.index(col_name) + 1
                    batch_updates.append({
                        'range': gspread.utils.rowcol_to_a1(row_num, col_idx),
                        'values': [[str(value)]]
                    })
                except ValueError:
                    pass
            if batch_updates:
                worksheet.batch_update(batch_updates)
        
        st.session_state.local_changes = {}
        st.session_state.unsaved_changes = False
        st.session_state.user_data = None
        return True, "Änderungen erfolgreich gespeichert!"
        
    except gspread.exceptions.APIError as e:
        error_detail = e.response.json().get('error', {}).get('message', str(e))
        return False, f"Google Sheets API Fehler: {error_detail}"
    except Exception as e:
        return False, f"Allgemeiner Fehler beim Speichern: {e}"

def analyze_workout_history(user_id):
    """Analyzes the workout history from the archive."""
    all_data = get_sheet_data(ARCHIVE_SHEET)
    if not all_data or len(all_data) < 2: return "Keine Archiv-Daten verfügbar.", None
    
    header = all_data[0]
    records = [dict(zip(header, row)) for row in all_data[1:]]
    
    user_data_list = [r for r in records if r.get('UserID', '').strip() == user_id]
    if not user_data_list: return "Keine Trainingshistorie für diesen User gefunden.", None
    
    df = pd.DataFrame(user_data_list)
    # Data cleaning
    for col in ['Gewicht', 'Wdh']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['Datum'] = pd.to_datetime(df['Datum'], errors='coerce')
    df.dropna(subset=['Datum'], inplace=True)

    summary = []
    exercises = df['Übung'].unique()
    
    for exercise in exercises:
        ex_data = df[df['Übung'] == exercise]
        max_weight = ex_data['Gewicht'].max()
        avg_reps = ex_data['Wdh'].mean()
        count = len(ex_data.groupby('Datum'))
        summary.append(f"- {exercise}: Max {max_weight:.1f}kg, Ø {avg_reps:.0f} Wdh, {count}x trainiert")
    
    return "\n".join(summary), df

def parse_ai_plan_to_rows(plan_text, user_id, user_name):
    """
    Converts an AI-generated text plan into structured table rows.
    """
    rows = []
    timestamp = datetime.datetime.now().isoformat()
    current_workout = "Allgemeines Training"
    lines = plan_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line: continue

        # 1. Is it a Workout Title? (e.g., **Push Day:** or **Workout-Name:** Push Day)
        workout_match = re.match(r'^\*\*(.*?):\*\*', line)
        if workout_match:
            # Extract the part after a potential "Workout-Name:" label
            title_part = workout_match.group(1)
            if "Workout-Name" in title_part:
                current_workout = title_part.split(":", 1)[-1].strip()
            else:
                current_workout = title_part.strip()
            continue

        # 2. Is it an Exercise? (e.g., - Bench Press: ...)
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
                if sets_match: sets = int(sets_match.group(1))

                weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                if weight_match: weight = float(weight_match.group(1).replace(',', '.'))
                elif "körpergewicht" in details.lower() or "bw" in details.lower(): weight = 0.0

                reps_match = re.search(r'(\d+\s*-\s*\d+|\d+)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match: reps = reps_match.group(1).strip()

                for satz in range(1, sets + 1):
                    rows.append({
                        'UserID': user_id, 'Datum': timestamp, 'Name': user_name,
                        'Workout Name': current_workout, 'Übung': exercise_name,
                        'Satz-Nr.': satz, 'Gewicht': weight,
                        'Wdh': reps.split('-')[0] if '-' in str(reps) else reps,
                        'Einheit': 'kg', 'Typ': '', 'Erledigt': 'FALSE',
                        'Mitteilung an den Trainer': '', 'Hinweis vom Trainer': explanation
                    })
            except Exception as e:
                st.warning(f"⚠️ Parsing-Fehler bei Übung: '{line}'. Fehler: {e}")
            
            continue

    return rows

# ---- Main App Logic ----
if 'user_data' not in st.session_state or st.session_state.user_data is None:
    st.session_state.user_data = load_user_workouts()

df = st.session_state.user_data
tab1, tab2, tab3, tab4, tab5 = st.tabs(["💪 Training", "➕ Neue Übung", "🤖 Neuer Plan", "📈 Analyse", "⚙️ Management"])

# ---- Tab 1: Training ----
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Workouts neu laden", type="primary"):
            st.session_state.user_data = None
            st.rerun()
    with col2:
        if st.button("💾 Änderungen speichern", disabled=not st.session_state.unsaved_changes):
            success, message = save_changes()
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

    if st.session_state.unsaved_changes:
        st.warning("⚠️ Du hast ungespeicherte Änderungen! Bitte speichern.")

    if df is not None and not df.empty:
        workouts = df['Workout Name'].unique()
        
        for workout in workouts:
            st.subheader(workout)
            workout_data = df[df['Workout Name'] == workout]
            exercises = workout_data['Übung'].unique()
            
            for exercise in exercises:
                if not exercise or pd.isna(exercise):
                    continue

                with st.expander(f"**{exercise}**", expanded=False):
                    exercise_data = workout_data[workout_data['Übung'] == exercise].sort_values('Satz-Nr.')
                    
                    trainer_hint = exercise_data.iloc[0].get('Hinweis vom Trainer', '')
                    if trainer_hint and trainer_hint.strip():
                        st.info(f"💡 **Fokus:** {trainer_hint}")
                    
                    for _, row in exercise_data.iterrows():
                        row_num = row['_row_num']
                        if row_num in st.session_state.rows_to_delete: continue
                        
                        cols = st.columns([1, 2, 2, 1.5, 0.5])
                        cols[0].write(f"**Satz {int(row['Satz-Nr.'])}**")
                        
                        for i, (col_name, label, step) in enumerate([('Gewicht', 'Gewicht (kg)', 2.5), ('Wdh', 'Wiederholungen', 1)]):
                            with cols[i+1]:
                                key = (row_num, col_name)
                                current_val = st.session_state.local_changes.get(key, row[col_name])
                                new_val = st.number_input(label, value=float(current_val), step=float(step), key=f"{col_name[0]}_{row_num}")
                                if new_val != row[col_name]:
                                    st.session_state.local_changes[key] = new_val
                                    st.session_state.unsaved_changes = True
                        
                        with cols[3]:
                            key = (row_num, 'Erledigt')
                            is_done = st.session_state.local_changes.get(key, str(row.get('Erledigt', 'FALSE')).upper() == 'TRUE')
                            if st.toggle("Erledigt", value=is_done, key=f"done_{row_num}") != is_done:
                                st.session_state.local_changes[key] = 'TRUE' if not is_done else 'FALSE'
                                st.session_state.unsaved_changes = True
                                st.rerun()

                        with cols[4]:
                            if st.button("🗑️", key=f"del_{row_num}", help="Satz löschen"):
                                st.session_state.rows_to_delete.append(row_num)
                                st.session_state.unsaved_changes = True
                                st.rerun()
                    
                    st.markdown("---")
                    
                    # User comment input field
                    first_row_num = exercise_data.iloc[0]['_row_num']
                    msg_key = (first_row_num, 'Mitteilung an den Trainer')
                    current_msg = st.session_state.local_changes.get(msg_key, exercise_data.iloc[0].get('Mitteilung an den Trainer', ''))
                    
                    new_msg = st.text_input("Mitteilung an den Trainer", value=current_msg or '', key=f"msg_{exercise}_{workout}", placeholder="z.B. Schulter zwickt...")
                    
                    if new_msg != current_msg:
                        for _, row in exercise_data.iterrows():
                            st.session_state.local_changes[(row['_row_num'], 'Mitteilung an den Trainer')] = new_msg
                        st.session_state.unsaved_changes = True
                        st.rerun()

                    action_cols = st.columns([1, 1, 2])
                    with action_cols[0]:
                        if st.button(f"➕ Satz", key=f"add_set_{exercise}_{workout}"):
                            last_row = exercise_data.iloc[-1]
                            header = df.columns.drop('_row_num').tolist()
                            new_row_dict = {col: last_row.get(col, '') for col in header}
                            new_row_dict['Satz-Nr.'] = int(last_row['Satz-Nr.']) + 1
                            new_row_dict['Erledigt'] = 'FALSE'
                            st.session_state.rows_to_add.append([str(new_row_dict.get(col, '')) for col in header])
                            st.session_state.unsaved_changes = True
                            st.rerun()
                    
                    with action_cols[1]:
                        if st.button(f"❌ Übung", key=f"del_ex_{exercise}_{workout}"):
                            for r_num in exercise_data['_row_num']:
                                if r_num not in st.session_state.rows_to_delete:
                                    st.session_state.rows_to_delete.append(r_num)
                            st.session_state.unsaved_changes = True
                            st.rerun()

    elif df is not None:
        st.info("Du hast aktuell keine geplanten Workouts.")
    else:
        st.error("Workout-Daten konnten nicht geladen werden.")

# ---- Tab 2: Neue Übung ----
with tab2:
    st.subheader("Neue Übung manuell hinzufügen")
    if df is not None:
        user_profile = get_user_profile(st.session_state.userid)
        user_name = user_profile.get("FullName", st.session_state.userid)
        
        existing_workouts = list(df['Workout Name'].unique())
        
        with st.form("new_exercise_form"):
            workout_name_option = st.selectbox("Zu welchem Workout hinzufügen?", ["Neues Workout erstellen"] + existing_workouts)
            
            if workout_name_option == "Neues Workout erstellen":
                workout_name = st.text_input("Name des neuen Workouts", placeholder="z.B. Push Day")
            else:
                workout_name = workout_name_option

            exercise_name = st.text_input("Übungsname", placeholder="z.B. Bankdrücken")
            num_sets = st.number_input("Anzahl Sätze", min_value=1, value=3)
            default_weight = st.number_input("Start-Gewicht (kg)", min_value=0.0, value=20.0, step=2.5)
            default_reps = st.number_input("Wiederholungen pro Satz", min_value=1, value=10)

            submitted = st.form_submit_button("Übung hinzufügen", type="primary")

            if submitted and exercise_name and workout_name:
                worksheet = get_main_worksheet()
                header = worksheet.row_values(1)
                
                for satz in range(1, num_sets + 1):
                    new_row_dict = {
                        'UserID': st.session_state.userid, 'Name': user_name, 'Datum': datetime.datetime.now().isoformat(),
                        'Workout Name': workout_name, 'Übung': exercise_name, 'Satz-Nr.': str(satz),
                        'Gewicht': str(default_weight), 'Wdh': str(default_reps), 'Erledigt': 'FALSE',
                        'Einheit': 'kg'
                    }
                    row_values = [str(new_row_dict.get(col, '')) for col in header]
                    st.session_state.rows_to_add.append(row_values)
                
                st.session_state.unsaved_changes = True
                st.success(f"'{exercise_name}' wurde hinzugefügt! Bitte im Training-Tab speichern.")
                st.rerun()
    else:
        st.info("Lade zuerst deine Workouts im 'Training' Tab, um eine Übung hinzuzufügen.")

# ---- Tab 3: Neuer Plan ----
with tab3:
    st.subheader("Neuen Trainingsplan mit KI erstellen")
    if not client:
        st.error("OpenAI API Key ist nicht konfiguriert.")
        st.stop()

    with st.expander("Deine Daten für die KI (bitte prüfen)", expanded=True):
        # Always fetch fresh data for the AI
        history_summary, _ = analyze_workout_history(st.session_state.userid)
        st.text_area("Gefundene Trainingshistorie:", value=history_summary, height=150, disabled=True)
        
        fragebogen_data = get_user_profile(st.session_state.userid)
        if fragebogen_data:
            st.info("Dein Profil wurde gefunden und wird verwendet:")
            st.json({k: v for k, v in fragebogen_data.items() if k != 'FullName'})
        else:
            st.warning("Kein Profil für deine UserID gefunden. Es werden Standardwerte verwendet.")

    additional_goals = st.text_area("Zusätzliche Ziele/Wünsche:", placeholder="z.B. Fokus auf Oberkörper, 2er-Split...")
    
    if st.button("🤖 Plan mit KI generieren", type="primary"):
        
        if "Keine Trainingshistorie" in history_summary:
            weight_instruction = "Gib KEINE spezifischen Gewichte an. Setze das Gewicht für jede Übung auf 0 kg."
        else:
            weight_instruction = "Schlage realistische Startgewichte basierend auf der Trainingshistorie vor."

        prompt = f"""
        Erstelle einen detaillierten und strukturierten wöchentlichen Trainingsplan.

        **Benutzerprofil & Ziele:**
        {fragebogen_data}

        **Bisherige Leistungen (Zusammenfassung):**
        {history_summary}

        **HARD CONSTRAINTS (MUST be followed):**
        1. **Number of Workouts:** Create EXACTLY {fragebogen_data.get('Trainingshäufigkeit (pro Woche)', '3')} workout days. No more, no less.
        2. **Workout Names:** Each workout day MUST start with a title in the format `**Workout-Name:**` (e.g., `**Push Day:**`). Use functional and UNIQUE names (e.g., "Oberkörper A", "Oberkörper B").
        3. **Split:** Strictly follow the requested split from 'Spezifische Wünsche' if provided (e.g., Push/Pull/Legs).
        4. **Weights:** {weight_instruction}
        5. **Output Format:** The format for each exercise MUST be exactly: `- Übungsname: X Sätze, Y-Z Wdh, W kg (Fokus: Kurze Erklärung der Übung)`
        6. **No Extra Text:** Do NOT add any general advice, summaries, or other text at the end. Only output the workout titles and exercise lists.
        """
        with st.spinner("KI analysiert deine Daten und erstellt einen personalisierten Plan..."):
            try:
                response = client.chat.completions.create(model='gpt-4o-mini', messages=[{"role": "user", "content": prompt}], temperature=0.6, max_tokens=2000)
                st.session_state.plan_text = response.choices[0].message.content
                user_name = fragebogen_data.get("FullName", st.session_state.userid)
                st.session_state.new_plan_rows = parse_ai_plan_to_rows(st.session_state.plan_text, st.session_state.userid, user_name)
            except Exception as e:
                st.error(f"Fehler bei der Kommunikation mit der KI: {e}")
                st.session_state.plan_text = None
                st.session_state.new_plan_rows = []

    if st.session_state.plan_text:
        st.subheader("Vorschau des neuen Plans")
        if not st.session_state.new_plan_rows:
            st.error("Fehler: Die Antwort der KI konnte nicht in einen Plan umgewandelt werden.")
            st.text_area("KI-Antwort zur Analyse:", st.session_state.plan_text, height=300)
        else:
            st.markdown(f"Die KI hat einen Plan mit **{len(st.session_state.new_plan_rows)}** Sätzen erstellt.")
            with st.expander("📋 Plan-Details anzeigen"):
                st.text(st.session_state.plan_text)
            
            st.warning("**Achtung:** Das Aktivieren löscht alle deine aktuellen, nicht archivierten Workouts!")
            if st.button("✅ Diesen Plan aktivieren", type="primary"):
                with st.spinner("Aktiviere neuen Plan..."):
                    # Securely load the current user's data to get correct rows to delete
                    current_user_df = load_user_workouts()
                    if current_user_df is not None and not current_user_df.empty:
                        st.session_state.rows_to_delete.extend(current_user_df['_row_num'].tolist())
                    
                    worksheet = get_main_worksheet()
                    header = worksheet.row_values(1)
                    for row_data in st.session_state.new_plan_rows:
                        row_values = [str(row_data.get(col, '')) for col in header]
                        st.session_state.rows_to_add.append(row_values)
                    
                    success, message = save_changes()
                    if success:
                        st.success("Neuer Plan wurde erfolgreich aktiviert!")
                        st.balloons()
                        st.session_state.plan_text = None
                        st.session_state.new_plan_rows = []
                        st.rerun()
                    else:
                        st.error(f"Aktivierung fehlgeschlagen: {message}")
                        st.session_state.rows_to_delete = []
                        st.session_state.rows_to_add = []

# ---- Tab 4: Analyse ----
with tab4:
    st.subheader("📈 Deine Trainingsanalyse")
    
    _, archive_df = analyze_workout_history(st.session_state.userid)

    if archive_df is None or archive_df.empty:
        st.info("Noch keine archivierten Daten für die Analyse vorhanden. Absolviere und archiviere zuerst einige Workouts.")
    else:
        # Calculate Volume and 1RM for each set
        archive_df['Volumen'] = archive_df['Gewicht'] * archive_df['Wdh']
        archive_df['1RM'] = archive_df['Gewicht'] * (1 + archive_df['Wdh'] / 30)
        
        # --- Exercise-specific analysis ---
        st.markdown("### Analyse pro Übung")
        exercises = sorted(archive_df['Übung'].unique())
        selected_exercise = st.selectbox("Wähle eine Übung für die Detailanalyse:", exercises)

        if selected_exercise:
            exercise_df = archive_df[archive_df['Übung'] == selected_exercise]
            
            # Group by date to get daily stats
            daily_stats = exercise_df.groupby('Datum').agg(
                Gesamtvolumen=('Volumen', 'sum'),
                Max_1RM=('1RM', 'max')
            ).reset_index()

            if not daily_stats.empty:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### Volumen-Progression")
                    st.line_chart(daily_stats.rename(columns={'Datum':'index'}).set_index('index')['Gesamtvolumen'])
                
                with col2:
                    st.markdown("#### Maximalkraft-Entwicklung (1RM)")
                    st.line_chart(daily_stats.rename(columns={'Datum':'index'}).set_index('index')['Max_1RM'])
            else:
                st.warning(f"Keine Daten für die Übung '{selected_exercise}' gefunden.")

        # --- Overall analysis ---
        st.markdown("### Gesamtübersicht")
        weekly_volume = archive_df.set_index('Datum').resample('W-MON', label='left', closed='left')['Volumen'].sum().reset_index()
        weekly_volume['Woche'] = weekly_volume['Datum'].dt.strftime('%Y-%U')
        
        st.markdown("#### Wöchentliches Gesamtvolumen (alle Übungen)")
        st.bar_chart(weekly_volume.set_index('Woche')['Volumen'])


# ---- Tab 5: Daten Management ----
with tab5:
    st.subheader("Daten & Cache Management")
    if st.button("🔄 App-Cache leeren & neu laden"):
        st.cache_data.clear()
        st.cache_resource.clear()
        for key in list(st.session_state.keys()):
            if key != 'userid':
                del st.session_state[key]
        st.success("Cache geleert. App wird neu geladen.")
        st.rerun()
