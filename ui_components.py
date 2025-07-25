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
    load_user_workouts, update_workout_set, add_set, delete_set,
    delete_exercise, add_exercise, delete_workout
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
        .small-header { font-weight: bold; color: #555; margin-bottom: -10px; }
    </style>
    """, unsafe_allow_html=True)

def display_milo_logo():
    logo_url = "https://github.com/StefDo-lab/gym-fragebogen/blob/feature/coach-milo-makeover/logo-dark.png?raw=true" 
    try:
        st.image(logo_url, width=120)
    except Exception as e:
        st.warning(f"Logo konnte nicht geladen werden. Bitte URL prüfen. Fehler: {e}")

# --- Page Rendering Functions ---
def display_login_page():
    display_milo_logo()
    st.title("Willkommen bei Coach Milo")
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
    """
    Displays the new, structured questionnaire for new users.
    """
    st.header("Hallo! Willkommen bei Coach Milo.")
    st.info("Damit ich den perfekten Plan für dich erstellen kann, brauche ich ein paar Informationen. Das dauert nur 2-3 Minuten.")

    with st.form("new_questionnaire_form"):
        tab1, tab2, tab3 = st.tabs(["Schritt 1: Stammdaten", "Schritt 2: Ziele & Training", "Schritt 3: Gesundheits-Check"])

        with tab1:
            st.subheader("Deine Kontaktdaten")
            forename = st.text_input("Vorname *")
            surename = st.text_input("Nachname *")
            email = st.text_input("E-Mail-Adresse *", value=st.session_state.user.email, disabled=True)
            today = datetime.date.today()
            birthday = st.date_input("Geburtsdatum *", min_value=today.replace(year=today.year - 100), max_value=today.replace(year=today.year - 16), value=today.replace(year=today.year - 25))

        with tab2:
            st.subheader("Deine Ziele & dein Training")
            primary_goal = st.selectbox("Was ist dein Hauptziel?", ["Muskelaufbau", "Gewichtsreduktion", "Kraft steigern", "Fitness & Gesundheit", "Rücken stärken"])
            experience_level = st.select_slider("Deine Trainingserfahrung", options=["Anfänger (0-1 Jahre)", "Fortgeschritten (1-3 Jahre)", "Erfahren (3+ Jahre)"])
            
            st.divider()
            
            training_days_per_week = st.slider("Wie viele Tage pro Woche möchtest du trainieren?", 1, 7, 3)
            time_per_session_minutes = st.slider("Wie viel Zeit hast du pro Einheit (in Minuten)?", 30, 120, 60, step=15)
            training_location = st.selectbox("Wo trainierst du hauptsächlich?", ["Voll ausgestattetes Fitnessstudio", "Home-Gym (Basisausstattung)", "Nur mit Körpergewicht"])
            
            st.divider()

            other_activities_per_week = st.number_input("Wie viele weitere anstrengende Sporteinheiten hast du pro Woche (Fußball, Laufen etc.)?", 0, 10, 0)
            other_activities_description = st.text_input("Welche Sportarten sind das?", placeholder="z.B. Fußball, Laufen, Tennis")

            st.subheader("Deine Vorlieben")
            liked_equipment = st.text_input("Gibt es Ausrüstung, die du besonders gerne nutzt?", placeholder="z.B. Kettlebells, Langhantel")
            disliked_exercises = st.text_input("Gibt es Übungen, die du gar nicht magst?", placeholder="z.B. Kniebeugen, Burpees")

        with tab3:
            st.subheader("Dein Gesundheits-Check")
            
            medical_topics = st.multiselect(
                "Welche der folgenden gesundheitlichen Themen treffen auf dich zu? (Mehrfachauswahl möglich)",
                ["Kürzliche Operation (letzte 18 Monate)", "Ausstrahlende Schmerzen", "Bandscheibenvorfall", "Bluthochdruck", "Herzprobleme", "Andere wichtige Themen"]
            )
            
            medical_notes = {}
            if "Kürzliche Operation (letzte 18 Monate)" in medical_topics:
                medical_notes['surgery'] = st.text_area("Bitte beschreibe die OP:", key="surgery_details")
            if "Ausstrahlende Schmerzen" in medical_topics:
                medical_notes['pain_details'] = st.text_area("Bitte beschreibe die Schmerzen:", key="pain_details")
            # ... (weitere Textfelder für andere medizinische Themen) ...

            st.divider()
            
            sleep_quality_rating = st.slider("Wie bewertest du deine Schlafqualität (1=schlecht, 10=hervorragend)?", 1, 10, 7)
            stress_level_rating = st.slider("Wie ist dein aktuelles Stresslevel (1=entspannt, 10=sehr hoch)?", 1, 10, 5)

        submitted = st.form_submit_button("Meine Antworten an Milo senden", type="primary")

        if submitted:
            if not forename or not surename:
                st.error("Bitte fülle mindestens Vorname und Nachname aus.")
            else:
                db_payload = {
                    "auth_user_id": st.session_state.user.id,
                    "uuid": str(uuid.uuid4()),
                    "forename": forename,
                    "surename": surename,
                    "email": email,
                    "birthday": str(birthday),
                    "training_days_per_week": training_days_per_week,
                    "time_per_session_minutes": time_per_session_minutes,
                    "training_location": training_location,
                    "experience_level": experience_level,
                    "primary_goal": primary_goal,
                    "other_activities_per_week": other_activities_per_week,
                    "has_restrictions": len(medical_topics) > 0,
                }

                context_payload = {
                    "other_activities_description": other_activities_description,
                    "liked_equipment": liked_equipment,
                    "disliked_exercises": disliked_exercises,
                    "sleep_quality_rating": sleep_quality_rating,
                    "stress_level_rating": stress_level_rating,
                    "medical_notes": medical_notes
                }
                db_payload["context_and_preferences"] = context_payload
                
                response = insert_questionnaire_data(db_payload)
                if response:
                    st.success("Super, danke! Ich habe alle Informationen. Lass uns jetzt deinen ersten Plan erstellen.")
                    st.balloons()
                    st.session_state.user_profile = db_payload
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Es gab einen Fehler beim Speichern deiner Antworten.")

def render_chat_tab(user_profile):
    st.header("Planung mit Milo")
    logo_url = "https://github.com/StefDo-lab/gym-fragebogen/blob/feature/coach-milo-makeover/logo-dark.png?raw=true"

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hallo! Ich bin Milo. Wollen wir einen neuen Trainingsplan erstellen?"}]
    
    for message in st.session_state.messages:
        avatar_icon = logo_url if message["role"] == "assistant" else "🧑"
        with st.chat_message(message["role"], avatar=avatar_icon):
            cleaned_content = message["content"].replace("<analyse>", "").replace("</analyse>", "").replace("<plan>", "").replace("</plan>", "")
            st.markdown(cleaned_content)

    if prompt := st.chat_input("Was möchtest du trainieren?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=logo_url):
            with st.spinner("Milo denkt nach..."):
                history_analysis = "Keine Trainingshistorie zur Analyse vorhanden."
                additional_info = {"text": "Keine besonderen Wünsche"}
                
                response = get_chat_response(st.session_state.messages, user_profile, history_analysis, additional_info)
                
                display_response = response.replace("<analyse>", "").replace("</analyse>", "").replace("<plan>", "\n\n").replace("</plan>", "")
                
                st.markdown(display_response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.latest_plan_text = response
    
    if 'latest_plan_text' in st.session_state:
        st.divider()
        if st.button("Diesen Plan aktivieren", type="primary", use_container_width=True):
            with st.spinner("Plan wird aktiviert..."):
                new_rows = parse_ai_plan_to_rows(st.session_state.latest_plan_text, user_profile)
                if not new_rows:
                    st.error("Der Plan konnte nicht verarbeitet werden.")
                else:
                    try:
                        old_workouts = load_user_workouts(user_profile['uuid'])
                        for item in old_workouts:
                            supabase_auth_client.table("workouts").delete().eq("id", item['id']).execute()
                        for row in new_rows:
                            supabase_auth_client.table("workouts").insert(row).execute()
                        st.success("Dein neuer Plan ist jetzt aktiv!")
                        st.balloons()
                        del st.session_state.messages
                        del st.session_state.latest_plan_text
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ein Fehler ist beim Aktivieren des Plans aufgetreten: {e}")

def display_training_tab(user_profile: dict):
    st.header("Dein aktueller Plan")
    user_profile_uuid = user_profile['uuid']
    user_name = f"{user_profile.get('forename', '')} {user_profile.get('surename', '')}".strip()
    workouts_data = load_user_workouts(user_profile_uuid)

    if not workouts_data:
        st.info("Du hast noch keinen aktiven Trainingsplan.")
    else:
        df = pd.DataFrame(workouts_data)
        workout_order = df.groupby('workout').first().sort_values('id').index
        
        for workout_name in workout_order:
            with st.expander(f"**{workout_name}**", expanded=True):
                workout_group = df[df['workout'] == workout_name]
                exercise_order = workout_group.groupby('exercise').first().sort_values('id').index
                
                for exercise_name in exercise_order:
                    st.markdown(f"##### {exercise_name}")
                    exercise_group = workout_group[workout_group['exercise'] == exercise_name].sort_values('set')
                    coach_msg = exercise_group.iloc[0]['messageFromCoach']
                    if coach_msg and coach_msg.strip():
                        st.info(f"💡 Tipp von Milo: {coach_msg}")
                    header_cols = st.columns([1, 2, 2, 1, 2])
                    with header_cols[1]: st.markdown("<p class='small-header'>Gewicht (kg)</p>", unsafe_allow_html=True)
                    with header_cols[2]: st.markdown("<p class='small-header'>Wdh.</p>", unsafe_allow_html=True)
                    with header_cols[3]: st.markdown("<p class='small-header'>RIR</p>", unsafe_allow_html=True)

                    for _, row in exercise_group.iterrows():
                        cols = st.columns([1, 2, 2, 1, 2])
                        with cols[0]: st.write(f"Satz {row['set']}")
                        with cols[1]: new_weight = st.number_input("Gewicht (kg)", value=float(row['weight']), key=f"w_{row['id']}", min_value=0.0, step=0.5, label_visibility="collapsed")
                        with cols[2]:
                            default_reps = int(row['reps'])
                            new_reps = st.number_input("Wdh", value=default_reps, key=f"r_{row['id']}", min_value=0, step=1, label_visibility="collapsed")
                        with cols[3]: new_rir = st.number_input("RIR", value=int(row.get('rirDone', 0) or 0), key=f"rir_{row['id']}", min_value=0, max_value=10, step=1, label_visibility="collapsed")
                        with cols[4]:
                            if row['completed']:
                                st.button("Erledigt ✅", key=f"done_{row['id']}", disabled=True, use_container_width=True)
                            else:
                                if st.button("Abschließen", key=f"save_{row['id']}", type="primary", use_container_width=True):
                                    updates = {"weight": new_weight, "reps": new_reps, "rirDone": new_rir, "completed": True, "time": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                                    if update_workout_set(row['id'], updates): st.rerun()
                    
                    btn_cols = st.columns(3)
                    with btn_cols[0]:
                        if st.button("➕ Satz hinzufügen", key=f"add_set_{row['id']}"):
                            last_set_data = exercise_group.iloc[-1].to_dict()
                            new_set_number = int(last_set_data['set']) + 1
                            last_set_data['set'] = new_set_number
                            last_set_data['completed'] = False
                            del last_set_data['id']
                            if add_set(last_set_data): st.rerun()
                    with btn_cols[1]:
                        if len(exercise_group) > 1 and st.button("➖ Letzten Satz löschen", key=f"del_set_{row['id']}"):
                            last_set_id = exercise_group.iloc[-1]['id']
                            if delete_set(last_set_id): st.rerun()
                    with btn_cols[2]:
                        if st.button("🗑️ Übung löschen", key=f"del_ex_{row['id']}"):
                            if delete_exercise(exercise_group['id'].tolist()): st.rerun()

                    with st.expander("💬 Nachricht an Milo"):
                        message_to_coach = st.text_area("Dein Feedback zur Übung", value=row.get('messageToCoach', ''), key=f"msg_area_{row['id']}")
                        if st.button("Nachricht senden", key=f"send_msg_btn_{row['id']}"):
                            for set_id in exercise_group['id']:
                                update_workout_set(set_id, {"messageToCoach": message_to_coach})
                            st.success("Nachricht gesendet!")

                    st.divider()

                with st.expander("➕ Neue Übung zu diesem Workout hinzufügen"):
                    with st.form(key=f"add_ex_form_{workout_name}"):
                        ex_name = st.text_input("Übungsname")
                        ex_cols = st.columns(3)
                        ex_sets = ex_cols[0].number_input("Sätze", 1, 10, 3)
                        ex_reps_str = ex_cols[1].text_input("Wdh.", "8-12")
                        ex_weight = ex_cols[2].number_input("Gewicht (kg)", 0.0, 500.0, 0.0, 0.5)
                        if st.form_submit_button("Hinzufügen"):
                            new_ex_rows = []
                            reps_for_db = int(ex_reps_str.split('-')[0])
                            for i in range(1, ex_sets + 1):
                                new_ex_rows.append({'uuid': user_profile_uuid, 'date': datetime.date.today().isoformat(), 'name': user_name, 'workout': workout_name, 'exercise': ex_name, 'set': i, 'weight': ex_weight, 'reps': reps_for_db, 'completed': False, 'messageFromCoach': f"Ziel: {ex_reps_str} Wdh."})
                            if add_exercise(new_ex_rows): st.rerun()
                
                if st.button("🗑️ Gesamtes Workout löschen", key=f"del_wo_{workout_name}"):
                    if delete_workout(workout_group['id'].tolist()): st.rerun()

    with st.expander("➕ Neues Workout erstellen"):
        with st.form(key="add_workout_form"):
            wo_name = st.text_input("Name des neuen Workouts")
            if st.form_submit_button("Erstellen"):
                dummy_exercise = [{'uuid': user_profile_uuid, 'date': datetime.date.today().isoformat(), 'name': user_name, 'workout': wo_name, 'exercise': "Neue Übung", 'set': 1, 'weight': 0, 'reps': 10, 'completed': False}]
                if add_exercise(dummy_exercise): st.rerun()


def display_main_app_page(user_profile):
    st.title(f"Willkommen, {user_profile.get('forename', 'Athlet')}!")
    tab1, tab2, tab3, tab4 = st.tabs(["Training", "Chat mit Milo", "Stats", "Profil"])
    with tab1:
        if 'uuid' in user_profile:
            display_training_tab(user_profile)
        else:
            st.error("Fehler: Keine UUID im Nutzerprofil gefunden.")
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
            for key in list(st.session_state.keys()): del st.session_state[key]
            supabase_auth_client.auth.sign_out()
            st.rerun()
