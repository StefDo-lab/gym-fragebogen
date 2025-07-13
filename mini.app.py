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
    """Fetches all data from a worksheet. IMPORTANT: No caching for critical data."""
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

    # Define relevant keys for the AI
    relevant_keys = [
        "Vorname", "Nachname", "Geschlecht", "Größe (cm)", "Gewicht (kg)", 
        "Körperfettanteil (%)", "Krafttraining-Erfahrung", "Trainingsziele", 
        "Ziel-Details", "OP letzte 12-18 Monate", "OP-Details", 
        "Ausstrahlende Schmerzen", "Schmerz-Details", "Bandscheibenvorfall letzte 6-12 Monate",
        "Bandscheiben-Details", "Sonstige Gesundheitsprobleme", "Konkrete Ziele", 
        "Gesundheitszustand", "Einschränkungen", "Schmerzen/Beschwerden", "Stresslevel", 
        "Schlafdauer (h)", "Ernährung", "Motivationslevel", "Trainingshäufigkeit (pro Woche)"
    ]
    
    # Filter the profile to only include relevant keys that have a value
    filtered_profile = {key: user_profile.get(key) for key in relevant_keys if user_profile.get(key)}
    
    # Add the full name for easier use
    filtered_profile['FullName'] = f"{user_profile.get('Vorname', '')} {user_profile.get('Nachname', '')}".strip()
    
    return filtered_profile


def load_user_workouts():
    """Loads and filters the workouts of the logged-in user."""
    st.cache_data.clear()
    all_data = get_sheet_data(WORKSHEET_NAME)
    if all_data is None:
        return None
    
    if len(all_data) < 1:
        return pd.DataFrame()
        
    header = all_data[0]
    df_columns = header + ['_row_num']
    
    try:
        uid_col_idx = header.index("UserID")
    except ValueError:
        st.error("Spalte 'UserID' nicht in der Tabelle gefunden.")
        return None

    user_rows = [row + [i + 2] for i, row in enumerate(all_data[1:]) if len(row) > uid_col_idx and row[uid_col_idx] == st.session_state.userid]
    
    if not user_rows:
        return pd.DataFrame(columns=df_columns)

    df = pd.DataFrame(user_rows, columns=df_columns)
    
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
        st.cache_data.clear()
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
    """Converts an AI-generated text plan into structured table rows."""
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = "Allgemeines Training"
    lines = plan_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line: continue

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
                if sets_match: sets = int(sets_match.group(1))

                weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                if weight_match: weight = float(weight_match.group(1).replace(',', '.'))
                elif "körpergewicht" in details.lower() or "bw" in details.lower(): weight = 0.0

                reps_match = re.search(r'(\d+\s*-\s*\d+|\d+)\s*(?:Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match: reps = reps_match.group(1).strip()

                for satz in range(1, sets + 1):
                    rows.append({
                        'UserID': user_id, 'Datum': current_date, 'Name': user_name,
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
    # ... (Code for Tab 1 remains the same) ...
    pass

# ---- Tab 2: Neue Übung ----
with tab2:
    # ... (Code for Tab 2 remains the same) ...
    pass

# ---- Tab 3: Neuer Plan ----
with tab3:
    st.subheader("Neuen Trainingsplan mit KI erstellen")
    if not client:
        st.error("OpenAI API Key ist nicht konfiguriert.")
        st.stop()

    with st.expander("Deine Daten für die KI (bitte prüfen)", expanded=True):
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
