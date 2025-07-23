# ui_components.py
# This file contains functions that render parts of the Streamlit UI.

import streamlit as st
import datetime
import uuid
import time
import pandas as pd
import re
from supabase_utils import (
    supabase_auth_client, insert_questionnaire_data, 
    load_user_workouts, update_workout_set
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
        /* Style for the headers */
        .small-header {
            font-weight: bold;
            color: #555;
            margin-bottom: -10px;
        }
    </style>
    """, unsafe_allow_html=True)

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
                        st.success("Registrierung erfolgreich! Bitte fülle nun den Fragebogen aus und logge dich danach ein.")
                except Exception:
                    st.error("Registrierung fehlgeschlagen. Ist die E-Mail schon vergeben?")

def display_questionnaire_page():
    # Hier den Code für den Fragebogen einfügen, falls benötigt
    st.header("Fragebogen")
    st.info("Dieser Bereich ist für den Fragebogen für neue Nutzer vorgesehen.")
    st.warning("Bitte beachte: Die Logik für den Fragebogen muss noch hinzugefügt werden.")
    # Beispiel-Button, um den Flow zu simulieren
    if st.button("Fragebogen (simuliert) abschicken"):
        # Hier würde die Logik zum Speichern des Fragebogens stehen
        # und st.session_state.user_profile würde mit den echten Daten gefüllt
        st.session_state.user_profile = {"uuid": "simulated-uuid", "forename": "Test", "surename": "User", "email": "test@test.com"}
        st.success("Fragebogen gespeichert!")
        time.sleep(1)
        st.rerun()


def render_chat_tab(user_profile):
    st.header("Planung mit Milo")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hallo! Ich bin Milo. Wollen wir einen neuen Trainingsplan erstellen?"}]
    
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Was möchtest du trainieren?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Milo denkt nach..."):
                full_prompt = f"Nutzerprofil: {user_profile}\n\nAnfrage: {prompt}"
                temp_history = [{"role": "user", "content": full_prompt}]
                response = get_chat_response(temp_history)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.latest_plan_text = response

    if 'latest_plan_text' in st.session_state:
        st.divider()
        if st.button("Diesen Plan aktivieren", type="primary", use_container_width=True):
            with st.spinner("Plan wird aktiviert..."):
                new_rows = parse_ai_plan_to_rows(st.session_state.latest_plan_text, user_profile)

                if not new_rows:
                    st.error("Der Plan konnte nicht verarbeitet werden. Das KI-Format war unerwartet. Bitte versuche es erneut.")
                else:
                    # --- KORRIGIERTE LOGIK: Manuelles Löschen und Einfügen ---
                    try:
                        # 1. Alte Workouts laden
                        old_workouts = load_user_workouts(user_profile['uuid'])
                        
                        # 2. Alte Workouts einzeln löschen
                        for item in old_workouts:
                            supabase_auth_client.table("workouts").delete().eq("id", item['id']).execute()
                        
                        # 3. Neue Workouts einzeln einfügen
                        for row in new_rows:
                            supabase_auth_client.table("workouts").insert(row).execute()
                        
                        # Wenn alles geklappt hat:
                        st.success("Dein neuer Plan ist jetzt aktiv!")
                        st.balloons()
                        del st.session_state.messages
                        del st.session_state.latest_plan_text
                        time.sleep(1)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Ein Fehler ist beim Aktivieren des Plans aufgetreten: {e}")


def display_training_tab(user_profile_uuid: str):
    st.header("Dein aktueller Plan")
    workouts_data = load_user_workouts(user_profile_uuid)

    if not workouts_data:
        st.info("Du hast noch keinen aktiven Trainingsplan. Erstelle einen neuen Plan im 'Chat mit Milo'-Tab!")
        return
    
    df = pd.DataFrame(workouts_data)
    
    workout_order = df.groupby('workout').first().sort_values('id').index
    
    for workout_name in workout_order:
        with st.expander(f"**{workout_name}**", expanded=True):
            workout_group = df[df['workout'] == workout_name]
            exercise_order = workout_group.groupby('exercise').first().sort_values('id').index
            
            for exercise_name in exercise_order:
                st.markdown(f"##### {exercise_name}")
                exercise_group = workout_group[workout_group['exercise'] == exercise_name].sort_values('set')
                
                # --- HINZUGEFÜGT: Tipp von Milo ---
                coach_msg = exercise_group.iloc[0]['messageFromCoach']
                if coach_msg and coach_msg.strip():
                    st.info(f"💡 Tipp von Milo: {coach_msg}")

                # --- HINZUGEFÜGT: Spaltenüberschriften ---
                header_cols = st.columns([1, 2, 2, 1, 2])
                with header_cols[1]:
                    st.markdown("<p class='small-header'>Gewicht (kg)</p>", unsafe_allow_html=True)
                with header_cols[2]:
                    st.markdown("<p class='small-header'>Wdh.</p>", unsafe_allow_html=True)
                with header_cols[3]:
                    st.markdown("<p class='small-header'>RIR</p>", unsafe_allow_html=True)

                for _, row in exercise_group.iterrows():
                    cols = st.columns([1, 2, 2, 1, 2])
                    with cols[0]:
                        st.write(f"Satz {row['set']}")
                    with cols[1]:
                        new_weight = st.number_input("Gewicht (kg)", value=float(row['weight']), key=f"w_{row['id']}", min_value=0.0, step=0.5, label_visibility="collapsed")
                    with cols[2]:
                        reps_str = str(row['reps']).split('-')[0]
                        default_reps = int(re.search(r'\d+', reps_str).group()) if re.search(r'\d+', reps_str) else 10
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
                
                # --- HINZUGEFÜGT: Nachricht an Milo ---
                with st.expander("💬 Nachricht an Milo"):
                    current_message = exercise_group.iloc[0].get('messageToCoach', '')
                    # Eindeutiger Key für die Text Area
                    text_area_key = f"msg_area_{exercise_group.iloc[0]['id']}"
                    
                    message_to_coach = st.text_area(
                        "Dein Feedback zur Übung",
                        value=current_message,
                        key=text_area_key,
                        placeholder="z.B. Gewicht war zu leicht, Technik-Fragen, etc."
                    )
                    
                    # Eindeutiger Key für den Button
                    button_key = f"send_msg_btn_{exercise_group.iloc[0]['id']}"
                    
                    if st.button("Nachricht senden", key=button_key):
                        success_count = 0
                        # Update die Nachricht für alle Sätze dieser Übung
                        for set_id in exercise_group['id']:
                            if update_workout_set(set_id, {"messageToCoach": message_to_coach}):
                                success_count += 1
                        
                        if success_count == len(exercise_group):
                            st.success("Nachricht gesendet!")
                            # Kein st.rerun() hier, damit die Nachricht sichtbar bleibt
                        else:
                            st.error("Fehler beim Senden der Nachricht.")

                st.divider()

def display_main_app_page(user_profile):
    st.title(f"Willkommen, {user_profile.get('forename', 'Athlet')}!")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Training", "Chat mit Milo", "Stats", "Profil"])

    with tab1:
        if 'uuid' in user_profile:
            display_training_tab(user_profile['uuid'])
        else:
            st.error("Fehler: Keine UUID im Nutzerprofil gefunden. Login-Prozess bitte überprüfen.")

    with tab2:
        render_chat_tab(user_profile)

    with tab3:
        st.header("Deine Fortschritte")
        st.info("Dieser Bereich wird bald deine Trainingsstatistiken anzeigen.")
    
    with tab4:
        st.header("Dein Profil")
        st.write(f"**Name:** {user_profile.get('forename', '')} {user_profile.get('surename', '')}")
        st.write(f"**E-Mail:** {user_profile.get('email', '')}")
        st.write(f"**Profil-UUID:** `{user_profile.get('uuid')}`")
        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            supabase_auth_client.auth.sign_out()
            st.rerun()
