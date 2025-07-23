# ui_components.py
# This file contains functions that render parts of the Streamlit UI.

import streamlit as st
import datetime
import uuid
import time
import pandas as pd
from supabase_utils import (
    supabase_auth_client, insert_questionnaire_data, 
    load_user_workouts, replace_user_workouts, update_workout_set
)
from ai_utils import get_chat_response, parse_ai_plan_to_rows

# --- General UI Components ---
def inject_mobile_styles():
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
    # HINWEIS: Bitte eine gültige, öffentlich zugängliche URL für das Logo verwenden.
    st.image("https://raw.githubusercontent.com/USER/REPO/BRANCH/logo.png", width=120)

# --- Page Rendering Functions ---

def display_login_page():
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
                except Exception:
                    st.error("Registrierung fehlgeschlagen. Ist die E-Mail schon vergeben?")

def display_questionnaire_page():
    st.header("Lerne deinen Coach Milo kennen")
    st.info("Hallo! Ich bin Milo. Um den perfekten Plan für dich zu erstellen, muss ich dich erst ein wenig kennenlernen.")
    with st.form("fitness_fragebogen"):
        st.header("Persönliche Daten")
        forename = st.text_input("Vorname *")
        surename = st.text_input("Nachname *")
        # ... (füge hier alle anderen Fragebogenfelder ein) ...
        abgeschickt = st.form_submit_button("Meine Antworten an Milo senden")
        if abgeschickt:
            if not (forename and surename):
                st.error("Bitte fülle alle Pflichtfelder (*) aus.")
            else:
                data_payload = {
                    "auth_user_id": st.session_state.user.id,
                    "uuid": str(uuid.uuid4()),
                    "forename": forename, "surename": surename,
                    "email": st.session_state.user.email,
                    # ... (füge hier alle anderen Daten für das Payload ein) ...
                }
                response = insert_questionnaire_data(data_payload)
                if response:
                    st.success("Danke! Du wirst jetzt zur App weitergeleitet.")
                    st.balloons()
                    st.session_state.user_profile = data_payload 
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Fehler beim Speichern des Fragebogens.")

def render_new_plan_tab(user_profile, history_summary):
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
                if len(st.session_state.messages) == 2: 
                    full_initial_prompt = f"Nutzerprofil: {user_profile}\n\nAnfrage: {prompt}"
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
                new_rows = parse_ai_plan_to_rows(st.session_state.latest_plan_text, user_profile)
                if not new_rows:
                    st.error("Der Plan konnte nicht verarbeitet werden. Das Format der KI-Antwort war unerwartet. Bitte versuche, den Plan neu zu generieren.")
                else:
                    response = replace_user_workouts(user_profile['uuid'], new_rows)
                    if response:
                        st.success("Dein neuer Plan ist jetzt aktiv!")
                        st.balloons()
                        del st.session_state.messages
                        del st.session_state.latest_plan_text
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Es gab ein Problem beim Speichern des neuen Plans.")

def display_training_tab(user_profile_uuid: str):
    st.header("Dein aktueller Plan")
    workouts_data = load_user_workouts(user_profile_uuid)
    if not workouts_data:
        st.info("Du hast noch keinen aktiven Trainingsplan. Erstelle einen neuen Plan im 'Neuer Plan'-Tab!")
        return
    
    df = pd.DataFrame(workouts_data)
    for workout_name, workout_group in df.groupby('workout'):
        with st.expander(f"**{workout_name}**", expanded=True):
            for exercise_name, exercise_group in workout_group.groupby('exercise'):
                st.markdown(f"##### {exercise_name}")
                sorted_sets = exercise_group.sort_values(by='set')
                for _, row in sorted_sets.iterrows():
                    cols = st.columns([1, 2, 2, 1, 2])
                    with cols[0]:
                        st.write(f"Satz {row['set']}")
                    with cols[1]:
                        new_weight = st.number_input("Gewicht (kg)", value=float(row['weight']), key=f"w_{row['id']}", min_value=0.0, step=0.5, label_visibility="collapsed")
                    with cols[2]:
                        # Use the target reps as default for the number input
                        default_reps = int(re.search(r'\d+', str(row['reps'])).group()) if re.search(r'\d+', str(row['reps'])) else 0
                        new_reps = st.number_input("Wdh", value=default_reps, key=f"r_{row['id']}", min_value=0, step=1, label_visibility="collapsed")
                    with cols[3]:
                        new_rir = st.number_input("RIR", value=int(row.get('rirDone', 0) or 0), key=f"rir_{row['id']}", min_value=0, max_value=10, step=1, label_visibility="collapsed")
                    with cols[4]:
                        if row['completed']:
                            st.button("Erledigt ✅", key=f"done_{row['id']}", disabled=True, use_container_width=True)
                        else:
                            if st.button("Abschließen", key=f"save_{row['id']}", type="primary", use_container_width=True):
                                updates = {
                                    "weight": new_weight, "reps": str(new_reps), "rirDone": new_rir,
                                    "completed": True, "time": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }
                                if update_workout_set(row['id'], updates):
                                    st.rerun()
                                else:
                                    st.error("Fehler beim Speichern.")
                st.divider()

def display_main_app_page(user_profile):
    st.title(f"Willkommen, {user_profile.get('forename', 'Athlet')}!")
    
    # REVISED TABS for better User Experience
    tab1, tab2, tab3, tab4 = st.tabs(["💪 Training", "🤖 Neuer Plan", "📈 Stats", "👤 Profil"])

    with tab1:
        display_training_tab(user_profile['uuid'])

    with tab2:
        history_summary = "Keine Trainingshistorie vorhanden." # Placeholder
        render_new_plan_tab(user_profile, history_summary)

    with tab3:
        st.header("Deine Fortschritte")
        st.info("Dieser Bereich wird bald deine Trainingsstatistiken anzeigen.")
    
    with tab4:
        st.header("Dein Profil")
        st.write(f"**Name:** {user_profile.get('forename', '')} {user_profile.get('surename', '')}")
        st.write(f"**E-Mail:** {user_profile.get('email', '')}")
        if st.button("Logout"):
            for key in st.session_state.keys():
                del st.session_state[key]
            supabase_auth_client.auth.sign_out()
            st.rerun()
