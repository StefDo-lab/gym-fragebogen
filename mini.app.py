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

# ---- Session State Initialisierung ----
def init_session_state():
    """Initialisiert den Session State, falls noch nicht geschehen."""
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

# ---- Login ----
if not st.session_state.userid:
    st.subheader("Login")
    uid = st.text_input("UserID", type="password")
    
    if st.button("Login"):
        if uid:
            st.session_state.userid = uid.strip()
            st.success(f"Eingeloggt als {st.session_state.userid}")
            st.rerun()
    st.stop()

# ---- Google Sheets Verbindung ----
@st.cache_resource
def get_gspread_client():
    """Stellt eine autorisierte Verbindung zu Google Sheets her und cached sie."""
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

@st.cache_data(ttl=300)
def get_sheet_data(sheet_name):
    """Holt alle Daten aus einem Arbeitsblatt und cached sie."""
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
    """Gibt das gspread worksheet-Objekt für Schreibvorgänge zurück."""
    try:
        gspread_client = get_gspread_client()
        if not gspread_client: return None
        ss = gspread_client.open(SHEET_NAME)
        return ss.worksheet(WORKSHEET_NAME)
    except Exception as e:
        st.error(f"Konnte Schreibzugriff auf Haupt-Arbeitsblatt nicht erhalten: {e}")
        return None


def load_user_workouts():
    """Lädt und filtert die Workouts des eingeloggten Benutzers."""
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
    """Speichert alle lokalen Änderungen (Löschen, Hinzufügen, Aktualisieren)."""
    worksheet = get_main_worksheet()
    if not worksheet:
        return False, "Keine Verbindung zum Arbeitsblatt."
    
    try:
        # LÖSCHEN via Batch Update
        if st.session_state.rows_to_delete:
            st.write(f"Bereite Löschung von {len(st.session_state.rows_to_delete)} Zeilen vor...")
            requests = []
            # Sortieren, damit die Indizes beim konzeptionellen Löschen korrekt bleiben
            for row_num in sorted(list(set(st.session_state.rows_to_delete)), reverse=True):
                requests.append({
                    "deleteDimension": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "ROWS",
                            "startIndex": row_num - 1, # API ist 0-indexed
                            "endIndex": row_num
                        }
                    }
                })
            
            if requests:
                worksheet.spreadsheet.batch_update({'requests': requests})
            st.session_state.rows_to_delete = []

        # HINZUFÜGEN
        if st.session_state.rows_to_add:
            st.write(f"Füge {len(st.session_state.rows_to_add)} neue Zeilen hinzu...")
            worksheet.append_rows(st.session_state.rows_to_add, value_input_option='USER_ENTERED')
            st.session_state.rows_to_add = []
        
        # AKTUALISIEREN
        if st.session_state.local_changes:
            st.write(f"Aktualisiere {len(st.session_state.local_changes)} Zellen...")
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
                    pass # Spalte ignorieren, falls nicht gefunden
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
    """Analysiert die Workout-Historie aus dem Archiv."""
    all_data = get_sheet_data(ARCHIVE_SHEET)
    if not all_data: return "Keine Archiv-Daten verfügbar."
    
    header = all_data[0]
    records = [dict(zip(header, row)) for row in all_data[1:]]
    
    user_data_list = [r for r in records if r.get('UserID', '').strip() == user_id]
    if not user_data_list: return "Keine Trainingshistorie für diesen User gefunden."
    
    df = pd.DataFrame(user_data_list)
    summary = []
    for col in ['Gewicht', 'Wdh']:
         if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    exercises = df['Übung'].value_counts()
    
    for exercise, count in exercises.items():
        ex_data = df[df['Übung'] == exercise]
        max_weight = ex_data['Gewicht'].max()
        avg_reps = ex_data['Wdh'].mean()
        summary.append(f"- {exercise}: Max {max_weight:.1f}kg, Ø {avg_reps:.0f} Wdh, {count}x trainiert")
    
    return "\n".join(summary[:10])

def parse_ai_plan_to_rows(plan_text, user_id):
    """Konvertiert einen KI-generierten Textplan in strukturierte Tabellenzeilen."""
    rows = []
    current_date = datetime.date.today().isoformat()
    current_workout = "Allgemeines Training"
    lines = plan_text.split('\n')

    for line in lines:
        line = line.strip()
        if not line or "hinweise:" in line.lower() or "wichtig:" in line.lower():
            continue

        exercise_match = re.match(r'^\s*[-*]\s*(.+?):\s*(.*)', line)
        if exercise_match:
            exercise_name = exercise_match.group(1).strip()
            details = exercise_match.group(2).strip()
            
            try:
                sets = 3
                weight = 0.0
                reps = "10"

                sets_match = re.search(r'(\d+)\s*(x|[Ss]ätze|[Ss]ets)', details)
                if sets_match:
                    sets = int(sets_match.group(1))

                weight_match = re.search(r'(\d+[\.,]?\d*)\s*kg', details)
                if weight_match:
                    weight = float(weight_match.group(1).replace(',', '.'))
                elif "körpergewicht" in details.lower() or "bw" in details.lower():
                    weight = 0.0

                reps_match = re.search(r'(\d+\s*-\s*\d+|\d+)\s*(Wdh|Wiederholungen|reps)', details, re.IGNORECASE)
                if reps_match:
                    reps = reps_match.group(1).strip()

                for satz in range(1, sets + 1):
                    rows.append({
                        'UserID': user_id, 'Datum': current_date, 'Name': '',
                        'Workout Name': current_workout, 'Übung': exercise_name,
                        'Satz-Nr.': satz, 'Gewicht': weight,
                        'Wdh': reps.split('-')[0] if '-' in str(reps) else reps,
                        'Einheit': 'kg', 'Typ': '', 'Erledigt': 'FALSE',
                        'Mitteilung an den Trainer': '', 'Hinweis vom Trainer': ''
                    })
            except Exception as e:
                st.warning(f"⚠️ Parsing-Fehler bei Übung: '{line}'. Fehler: {e}")
            
            continue

        if ":" in line:
            potential_workout_name = line.replace('*', '').split(':', 1)[0].strip()
            if potential_workout_name:
                current_workout = potential_workout_name

    return rows

# ---- Haupt-App-Logik ----
if 'user_data' not in st.session_state or st.session_state.user_data is None:
    st.session_state.user_data = load_user_workouts()

df = st.session_state.user_data
tab1, tab2, tab3, tab4 = st.tabs(["💪 Training", "➕ Neue Übung", "🤖 Neuer Plan", "⚙️ Management"])

# ---- Tab 1: Training ----
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Workouts neu laden", type="primary"):
            st.session_state.user_data = None
            st.cache_data.clear()
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
                with st.expander(f"**{exercise}**", expanded=False):
                    exercise_data = workout_data[workout_data['Übung'] == exercise].sort_values('Satz-Nr.')
                    
                    trainer_hint = exercise_data.iloc[0].get('Hinweis vom Trainer', '')
                    if trainer_hint and trainer_hint.strip():
                        st.info(f"💬 **Trainer-Hinweis:** {trainer_hint}")
                    
                    for _, row in exercise_data.iterrows():
                        row_num = row['_row_num']
                        if row_num in st.session_state.rows_to_delete:
                            continue
                        
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
                            new_is_done = st.toggle("Erledigt", value=is_done, key=f"done_{row_num}")
                            if new_is_done != is_done:
                                st.session_state.local_changes[key] = 'TRUE' if new_is_done else 'FALSE'
                                st.session_state.unsaved_changes = True
                                st.rerun()

                        with cols[4]:
                            if st.button("🗑️", key=f"del_{row_num}", help="Satz löschen"):
                                st.session_state.rows_to_delete.append(row_num)
                                st.session_state.unsaved_changes = True
                                st.rerun()
                    
                    st.markdown("---")
                    
                    action_cols = st.columns([1, 1, 2])
                    with action_cols[0]:
                        if st.button(f"➕ Satz hinzufügen", key=f"add_set_{exercise}_{workout}"):
                            last_row = exercise_data.iloc[-1]
                            header = df.columns.drop('_row_num').tolist()
                            new_row_dict = {col: last_row.get(col, '') for col in header}
                            new_row_dict['Satz-Nr.'] = int(last_row['Satz-Nr.']) + 1
                            new_row_dict['Erledigt'] = 'FALSE'
                            st.session_state.rows_to_add.append([str(new_row_dict.get(col, '')) for col in header])
                            st.session_state.unsaved_changes = True
                            st.rerun()
                    
                    with action_cols[1]:
                        if st.button(f"❌ Übung löschen", key=f"del_ex_{exercise}_{workout}"):
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
                        'UserID': st.session_state.userid, 'Datum': datetime.date.today().isoformat(),
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
        history_summary = analyze_workout_history(st.session_state.userid)
        st.text_area("Gefundene Trainingshistorie:", value=history_summary, height=150, disabled=True)
        
        fragebogen_data = {}
        all_fb_data = get_sheet_data(FRAGEBOGEN_SHEET)
        if all_fb_data:
            header = all_fb_data[0]
            records = [dict(zip(header, row)) for row in all_fb_data[1:]]
            user_profile = next((r for r in records if r.get('UserID', '').strip() == st.session_state.userid), None)
            if user_profile:
                st.info("Dein Profil wurde gefunden und wird verwendet:")
                st.json({k: v for k, v in user_profile.items() if k != 'UserID' and v})
                fragebogen_data = user_profile
            else:
                st.warning("Kein Profil für deine UserID gefunden. Es werden Standardwerte verwendet.")
        else:
            st.warning("Kein Fragebogen-Sheet gefunden. Es werden Standardwerte verwendet.")

    additional_goals = st.text_area("Zusätzliche Ziele/Wünsche:", placeholder="z.B. Fokus auf Oberkörper...")
    
    if st.button("🤖 Plan mit KI generieren", type="primary"):
        prompt = f"""
        Erstelle einen detaillierten und strukturierten wöchentlichen Trainingsplan.

        **Benutzerprofil & Ziele:**
        - Fitnesslevel: {fragebogen_data.get('Fitnesslevel', 'Mittel')}
        - Hauptziel: {fragebogen_data.get('Ziel', 'Muskelaufbau')}
        - Verfügbare Tage pro Woche: {fragebogen_data.get('Verfügbare_Tage', '3')}
        - Ausrüstung: {fragebogen_data.get('Ausrüstung', 'Fitnessstudio')}
        - Spezifische Wünsche: {additional_goals or "Allgemeine Fitness verbessern"}

        **Bisherige Leistungen (Zusammenfassung):**
        {history_summary}

        **ANWEISUNGEN FÜR DAS AUSGABEFORMAT (SEHR WICHTIG):**
        1. Jeder Workout-Tag MUSS mit einem Titel beginnen, der mit einem Doppelpunkt endet. Beispiel: `**Tag 1: Kraft Oberkörper:**`
        2. Jede Übung für diesen Tag MUSS in einer neuen Zeile stehen und mit einem Bindestrich beginnen. Beispiel: `- Bankdrücken: ...`
        3. Das Format für jede Übung MUSS exakt so aussehen: `- Übungsname: X Sätze, Y-Z Wdh, W kg`
        4. Füge am Ende KEINE allgemeinen Hinweise, Zusammenfassungen oder zusätzliche Erklärungen hinzu. Gib NUR die Workout-Titel und die Übungslisten aus.
        """
        with st.spinner("KI analysiert deine Daten und erstellt einen personalisierten Plan..."):
            try:
                response = client.chat.completions.create(model='gpt-4o-mini', messages=[{"role": "user", "content": prompt}], temperature=0.6, max_tokens=2000)
                st.session_state.plan_text = response.choices[0].message.content
                st.session_state.new_plan_rows = parse_ai_plan_to_rows(st.session_state.plan_text, st.session_state.userid)
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
                    if df is not None and not df.empty:
                        st.session_state.rows_to_delete.extend(df['_row_num'].tolist())
                    
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

# ---- Tab 4: Daten Management ----
with tab4:
    st.subheader("Daten & Cache Management")
    if st.button("🔄 App-Cache leeren & neu laden"):
        st.cache_data.clear()
        st.cache_resource.clear()
        for key in list(st.session_state.keys()):
            if key != 'userid':
                del st.session_state[key]
        st.success("Cache geleert. App wird neu geladen.")
        st.rerun()
