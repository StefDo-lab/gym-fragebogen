# ui_components.py
# This file contains functions that render parts of the Streamlit UI.

import streamlit as st
import datetime
import uuid
import time
from collections import defaultdict
from supabase_utils import (
    supabase_auth_client, insert_questionnaire_data, 
    load_user_workouts, replace_user_workouts, update_workout_set
)
from ai_utils import get_chat_response, parse_ai_plan_to_rows

# --- General UI Components ---
def inject_mobile_styles():
    """Injects CSS to make the app look more like a native mobile app."""
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden !important;}
        .block-container { padding-top: 1rem; }
    </style>
    """, unsafe_allow_html=True)

def display_milo_logo():
    """Displays the Coach Milo logo."""
    # HINWEIS: Bitte eine gültige, öffentlich zugängliche URL für das Logo verwenden.
    logo_url = "https://raw.githubusercontent.com/USER/REPO/BRANCH/logo.png" 
    st.image(logo_url, width=120)

# --- Page Rendering Functions ---

def display_login_page():
    """Displays the login and registration forms."""
    # display_milo_logo() # Optional
    st.title("Willkommen bei Coach Milo")
    st.info("Dein persönlicher KI-Coach, der dich wirklich versteht.")

    mode = st.radio("Wähle eine Option:", ["Einloggen", "Registrieren"], horizontal=True, label_visibility="collapsed")

    if mode == "Einloggen":
        with st.form("login_form"):
            email = st.text_input("E-Mail")
            password = st.text_input("Passwort", type="password")
            if st.form_submit_button("Einloggen", type="primary", use_container_width=True):
                try:
                    res = supabase_auth_client.auth.sign_in_with_password({"email": email, "password": password})
                    if res.user:
                        st.session_state.user = res.user
                        st.success("Login erfolgreich!")
                        time.sleep(1)
                        st.rerun()
                except Exception:
                    st.error("Login fehlgeschlagen. Bitte prüfe deine Eingaben.")
    
    elif mode == "Registrieren":
        with st.form("register_form"):
            email = st.text_input("E-Mail")
            password = st.text_input("Passwort", type="password")
            if st.form_submit_button("Account erstellen", use_container_width=True):
                try:
                    res = supabase_auth_client.auth.sign_up({"email": email, "password": password})
                    if res.user:
                        st.success("Registrierung erfolgreich! Bitte bestätige deine E-Mail und logge dich dann ein.")
                except Exception as e:
                    st.error(f"Registrierung fehlgeschlagen. Ist die E-Mail schon vergeben?")

def display_questionnaire_page():
    """Displays the questionnaire form for new users."""
    # display_milo_logo() # Optional
    st.header("Lerne deinen Coach Milo kennen")
    st.info("Hallo! Ich bin Milo. Um den perfekten Plan für dich zu erstellen, muss ich dich erst ein wenig kennenlernen.")

    with st.form("fitness_fragebogen"):
        st.header("Persönliche Daten")
        forename = st.text_input("Vorname *")
        # ... (füge hier alle anderen Fragebogenfelder ein) ...
        
        abgeschickt = st.form_submit_button("Meine Antworten an Milo senden")

        if abgeschickt:
            if not forename: # Beispiel für eine Validierung
                st.error("Bitte fülle alle Pflichtfelder (*) aus.")
            else:
                # Erstelle das Datenpaket für die 'questionaire' Tabelle
                data_payload = {
                    "auth_user_id": st.session_state.user.id,
                    "uuid": str(uuid.uuid4()), # Behalte eine separate UUID für den Fragebogen, falls benötigt
                    "forename": forename,
                    "email": st.session_state.user.email,
                    # ... (füge hier alle anderen Daten für das Payload ein) ...
                }
                response = insert_questionnaire_data(data_payload)
                if response:
                    st.success("Danke! Milo hat deine Daten erhalten. Du wirst jetzt zur App weitergeleitet.")
                    st.balloons()
                    # Profil im Session State setzen, um erneute Abfrage zu verhindern
                    st.session_state.user_profile = data_payload 
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Fehler beim Speichern des Fragebogens.")

def render_chat_tab(user_profile, history_summary):
    """Renders the interactive chat UI for plan generation."""
    st.header("Planung mit Milo")

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hallo! Ich bin Milo. Wollen wir einen neuen Trainingsplan erstellen? Sag mir einfach, was du dir vorstellst (z.B. 'einen 3er-Split für Muskelaufbau')."}]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Was möchtest du trainieren?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Milo denkt nach..."):
                # Beim ersten Mal senden wir das Profil mit
                if len(st.session_state.messages) == 2: 
                    full_initial_prompt = f"""
Hier sind die Hintergrundinformationen über den Nutzer {user_profile.get('forename', '')}. Erstelle basierend darauf und seiner Anfrage den ersten Plan.
---
BENUTZERPROFIL:
{user_profile}
---
AKTUELLE ANFRAGE DES NUTZERS:
{prompt}
"""
                    temp_history = [{"role": "user", "content": full_initial_prompt}]
                    response = get_chat_response(temp_history)
                else:
                    response = get_chat_response(st.session_state.messages)
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.latest_plan_text = response

    if 'latest_plan_text' in st.session_state and st.session_state.latest_plan_text:
        st.divider()
        if st.button("Diesen Plan aktivieren", type="primary", use_container_width=True):
            with st.spinner("Plan wird aktiviert..."):
                auth_user_id = st.session_state.user.id
                
                # Die neue, robuste Parsing-Funktion aufrufen
                new_rows = parse_ai_plan_to_rows(st.session_state.latest_plan_text, auth_user_id)
                
                if not new_rows:
                    st.error("Der Plan konnte nicht verarbeitet werden. Das Format der KI-Antwort war unerwartet. Bitte versuche, den Plan neu zu generieren.")
                else:
                    # Alte Workouts löschen und neue einfügen
                    response = replace_user_workouts(auth_user_id, new_rows)
                    if response:
                        st.success("Dein neuer Plan ist jetzt aktiv!")
                        st.balloons()
                        # Chat zurücksetzen
                        del st.session_state.messages
                        del st.session_state.latest_plan_text
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Es gab ein Problem beim Speichern des neuen Plans.")

def display_training_tab(auth_user_id: str):
    """Displays the current workout plan."""
    st.header("Dein Training heute")
    workouts_data = load_user_workouts(auth_user_id)
    
    if not workouts_data:
        st.info("Du hast noch keinen aktiven Trainingsplan. Erstelle einen neuen Plan im 'Chat mit Milo'-Tab!")
        return

    # Workouts nach Tag gruppieren
    workouts_by_day = defaultdict(list)
    for w in workouts_data:
        workouts_by_day[w['day']].append(w)

    for day, exercises in workouts_by_day.items():
        with st.expander(f"**{day}**", expanded=True):
            # Übungen innerhalb eines Tages gruppieren
            exercises_by_name = defaultdict(list)
            for ex in exercises:
                exercises_by_name[ex['exercise_name']].append(ex)

            for ex_name, sets in exercises_by_name.items():
                st.markdown(f"##### {ex_name}")
                # Annahme: Die Sätze sind bereits nach `created_at` sortiert
                total_sets = sets[0]['sets']
                completed_sets = sets[0]['completed_sets']
                
                # Zeige alle Sätze an, aber nur der nächste unvollständige ist aktiv
                for i in range(1, total_sets + 1):
                    is_completed = i <= completed_sets
                    is_next_set = i == completed_sets + 1
                    
                    cols = st.columns([1, 2, 2, 2])
                    
                    with cols[0]:
                        st.write(f"Satz {i}")
                    
                    if is_completed:
                        with cols[1]: st.write(f"Gewicht: {sets[i-1].get('weight_done', 'k.A.')} kg")
                        with cols[2]: st.write(f"Wdh: {sets[i-1].get('reps_done', 'k.A.')}")
                        with cols[3]: st.button("Erledigt ✅", key=f"done_{sets[i-1]['id']}", disabled=True, use_container_width=True)
                    elif is_next_set:
                        # Aktiver Satz
                        current_set_data = sets[i-1]
                        with cols[1]:
                            weight_done = st.number_input("Gewicht (kg)", value=float(current_set_data['weight']), key=f"w_{current_set_data['id']}", min_value=0.0, step=0.5, label_visibility="collapsed")
                        with cols[2]:
                            reps_done = st.number_input("Wdh", value=int(current_set_data['reps'].split('-')[0]), key=f"r_{current_set_data['id']}", min_value=0, step=1, label_visibility="collapsed")
                        with cols[3]:
                            if st.button("Abschließen", key=f"save_{current_set_data['id']}", type="primary", use_container_width=True):
                                updates = {
                                    "weight_done": weight_done, 
                                    "reps_done": reps_done,
                                    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }
                                # Update für diesen einen Satz
                                if update_workout_set(current_set_data['id'], updates):
                                     # Update der 'completed_sets' Zählung für die gesamte Übung
                                    update_workout_set(current_set_data['id'], {"completed_sets": i})
                                    st.rerun()
                    else: # Zukünftiger Satz
                        with cols[1]: st.write(f"Ziel: {sets[i-1]['weight']} kg")
                        with cols[2]: st.write(f"Ziel: {sets[i-1]['reps']} Wdh")
                        with cols[3]: st.button("Ausstehend", key=f"pending_{sets[i-1]['id']}", disabled=True, use_container_width=True)

                st.divider()


def display_main_app_page(user_profile):
    """Displays the main workout tracker UI with tabs."""
    st.title(f"Willkommen, {user_profile.get('forename', 'Athlet')}!")
    
    auth_user_id = st.session_state.user.id
    
    tab1, tab2, tab3, tab4 = st.tabs(["💪 Training", "🤖 Chat mit Milo", "📈 Stats", "👤 Profil"])

    with tab1:
        display_training_tab(auth_user_id)

    with tab2:
        history_summary = "Keine Trainingshistorie vorhanden." # Placeholder
        render_chat_tab(user_profile, history_summary)

    with tab3:
        st.header("Deine Fortschritte")
        st.info("Dieser Bereich wird bald deine Trainingsstatistiken anzeigen.")
    
    with tab4:
        st.header("Dein Profil")
        st.write(f"**Name:** {user_profile.get('forename', '')}")
        st.write(f"**E-Mail:** {user_profile.get('email', '')}")
        st.info("Hier kannst du bald deine Profildaten bearbeiten.")
        if st.button("Logout"):
            supabase_auth_client.auth.sign_out()
            # Clear all session state on logout
            for key in st.session_state.keys():
                del st.session_state[key]
            st.rerun()
