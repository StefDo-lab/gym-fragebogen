# ui_components.py
# This file contains functions that render parts of the Streamlit UI.

import streamlit as st
import datetime
import uuid
import time
import pandas as pd
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
        /* Style for navigation buttons */
        .stButton>button {
            width: 100%;
        }
    </style>
    """, unsafe_allow_html=True)

def display_milo_logo():
    logo_url = "https://github.com/StefDo-lab/gym-fragebogen/blob/feature/coach-milo-makeover/logo-dark.png?raw=true" 
    st.image(logo_url, width=120)

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
                        st.success("Registrierung erfolgreich! Du wirst nun zum Fragebogen weitergeleitet.")
                        # After signup, supabase sends a confirmation email. 
                        # For this app, we log the user in directly to proceed.
                        login_res = supabase_auth_client.auth.sign_in_with_password({"email": email, "password": password})
                        if login_res.user:
                            st.session_state.user = login_res.user
                            time.sleep(2)
                            st.rerun()
                except Exception:
                    st.error("Registrierung fehlgeschlagen. Ist die E-Mail schon vergeben?")


# --- NEW MULTI-STEP QUESTIONNAIRE ---

def _render_questionnaire_step1():
    """Renders the UI for Step 1: Stammdaten."""
    st.subheader("Schritt 1: Wer bist du?")
    with st.form("step1_form"):
        forename = st.text_input("Vorname *", value=st.session_state.questionnaire_data.get("forename", ""))
        surename = st.text_input("Nachname *", value=st.session_state.questionnaire_data.get("surename", ""))
        
        today = datetime.date.today()
        default_bday = st.session_state.questionnaire_data.get("birthday", today.replace(year=today.year - 25))
        birthday = st.date_input("Geburtsdatum *", min_value=today.replace(year=today.year - 100), max_value=today.replace(year=today.year - 16), value=default_bday)
        
        submitted = st.form_submit_button("Weiter zu Schritt 2", type="primary")
        if submitted:
            if not forename or not surename:
                st.error("Bitte Vor- und Nachnamen ausfüllen.")
                return

            st.session_state.questionnaire_data['forename'] = forename
            st.session_state.questionnaire_data['surename'] = surename
            st.session_state.questionnaire_data['birthday'] = birthday
            st.session_state.questionnaire_step = 2
            st.rerun()

def _render_questionnaire_step2():
    """Renders the UI for Step 2: Ziele & Training."""
    st.subheader("Schritt 2: Deine Ziele & dein Training")
    with st.form("step2_form"):
        q_data = st.session_state.questionnaire_data
        
        primary_goal = st.selectbox("Was ist dein Hauptziel?", ["Muskelaufbau", "Gewichtsreduktion", "Kraft steigern", "Fitness & Gesundheit", "Rücken stärken"], index=["Muskelaufbau", "Gewichtsreduktion", "Kraft steigern", "Fitness & Gesundheit", "Rücken stärken"].index(q_data.get("primary_goal", "Muskelaufbau")))
        experience_level = st.select_slider("Deine Trainingserfahrung", options=["Anfänger (0-1 Jahre)", "Fortgeschritten (1-3 Jahre)", "Erfahren (3+ Jahre)"], value=q_data.get("experience_level", "Anfänger (0-1 Jahre)"))
        
        st.divider()
        training_days_per_week = st.slider("Wie viele Tage pro Woche möchtest du trainieren?", 1, 7, q_data.get("training_days_per_week", 3))
        time_per_session_minutes = st.slider("Wie viel Zeit hast du pro Einheit (in Minuten)?", 30, 120, q_data.get("time_per_session_minutes", 60), step=15)
        training_location = st.selectbox("Wo trainierst du hauptsächlich?", ["Voll ausgestattetes Fitnessstudio", "Home-Gym (Basisausstattung)", "Nur mit Körpergewicht"], index=["Voll ausgestattetes Fitnessstudio", "Home-Gym (Basisausstattung)", "Nur mit Körpergewicht"].index(q_data.get("training_location", "Voll ausgestattetes Fitnessstudio")))
        
        st.divider()
        other_activities_per_week = st.number_input("Wie viele weitere anstrengende Sporteinheiten hast du pro Woche (Fußball, Laufen etc.)?", 0, 10, q_data.get("other_activities_per_week", 0))
        other_activities_description = st.text_input("Welche Sportarten sind das?", placeholder="z.B. Fußball, Laufen, Tennis", value=q_data.get("other_activities_description", ""))
        
        st.divider()
        liked_equipment = st.text_input("Gibt es Ausrüstung, die du besonders gerne nutzt?", placeholder="z.B. Kettlebells, Langhantel", value=q_data.get("liked_equipment", ""))
        disliked_exercises = st.text_input("Gibt es Übungen, die du gar nicht magst?", placeholder="z.B. Kniebeugen, Burpees", value=q_data.get("disliked_exercises", ""))

        col1, col2 = st.columns(2)
        with col1:
            back_clicked = st.form_submit_button("Zurück zu Schritt 1")
        with col2:
            next_clicked = st.form_submit_button("Weiter zu Schritt 3", type="primary")

        if next_clicked:
            q_data.update({
                "primary_goal": primary_goal, "experience_level": experience_level,
                "training_days_per_week": training_days_per_week, "time_per_session_minutes": time_per_session_minutes,
                "training_location": training_location, "other_activities_per_week": other_activities_per_week,
                "other_activities_description": other_activities_description, "liked_equipment": liked_equipment,
                "disliked_exercises": disliked_exercises
            })
            st.session_state.questionnaire_step = 3
            st.rerun()
        if back_clicked:
            st.session_state.questionnaire_step = 1
            st.rerun()

def _render_questionnaire_step3():
    """Renders the UI for Step 3: Gesundheits-Check and handles final submission."""
    st.subheader("Schritt 3: Dein Gesundheits-Check")
    with st.form("step3_form"):
        q_data = st.session_state.questionnaire_data
        
        medical_topics = st.multiselect(
            "Welche der folgenden gesundheitlichen Themen treffen auf dich zu?",
            ["Kürzliche Operation", "Ausstrahlende Schmerzen", "Bandscheibenvorfall", "Bluthochdruck", "Herzprobleme", "Andere wichtige Themen"],
            default=q_data.get("medical_topics", [])
        )
        
        medical_notes = q_data.get("medical_notes", {})
        if "Kürzliche Operation" in medical_topics:
            medical_notes['surgery'] = st.text_area("Bitte beschreibe die OP:", value=medical_notes.get('surgery', ''))
        if "Ausstrahlende Schmerzen" in medical_topics:
            medical_notes['pain_details'] = st.text_area("Bitte beschreibe die Schmerzen:", value=medical_notes.get('pain_details', ''))
        if "Andere wichtige Themen" in medical_topics:
            medical_notes['other'] = st.text_area("Sonstige Anmerkungen zur Gesundheit:", value=medical_notes.get('other', ''))

        st.divider()
        sleep_quality_rating = st.slider("Wie bewertest du deine Schlafqualität (1=schlecht, 10=hervorragend)?", 1, 10, q_data.get("sleep_quality_rating", 7))
        stress_level_rating = st.slider("Wie ist dein aktuelles Stresslevel (1=entspannt, 10=sehr hoch)?", 1, 10, q_data.get("stress_level_rating", 5))

        col1, col2 = st.columns(2)
        with col1:
            back_clicked = st.form_submit_button("Zurück zu Schritt 2")
        with col2:
            submitted = st.form_submit_button("Meine Antworten an Milo senden", type="primary")

        if submitted:
            # Save final data
            q_data.update({
                "medical_topics": medical_topics, "medical_notes": medical_notes,
                "sleep_quality_rating": sleep_quality_rating, "stress_level_rating": stress_level_rating
            })

            # --- Build Payloads and Submit ---
            with st.spinner("Speichere deine Antworten..."):
                db_payload = {
                    "auth_user_id": st.session_state.user.id,
                    "uuid": str(uuid.uuid4()),
                    "forename": q_data.get("forename"),
                    "surename": q_data.get("surename"),
                    "email": st.session_state.user.email,
                    "birthday": str(q_data.get("birthday")),
                    "training_days_per_week": q_data.get("training_days_per_week"),
                    "time_per_session_minutes": q_data.get("time_per_session_minutes"),
                    "training_location": q_data.get("training_location"),
                    "experience_level": q_data.get("experience_level"),
                    "primary_goal": q_data.get("primary_goal"),
                    "other_activities_per_week": q_data.get("other_activities_per_week"),
                    "has_restrictions": len(q_data.get("medical_topics", [])) > 0,
                }
                context_payload = {
                    "other_activities_description": q_data.get("other_activities_description"),
                    "liked_equipment": q_data.get("liked_equipment"),
                    "disliked_exercises": q_data.get("disliked_exercises"),
                    "sleep_quality_rating": q_data.get("sleep_quality_rating"),
                    "stress_level_rating": q_data.get("stress_level_rating"),
                    "medical_notes": q_data.get("medical_notes")
                }
                db_payload["context_and_preferences"] = context_payload
                
                response = insert_questionnaire_data(db_payload)
                if response:
                    st.success("Super, danke! Ich habe alle Informationen.")
                    st.balloons()
                    st.session_state.user_profile = db_payload
                    # Clean up questionnaire state
                    del st.session_state.questionnaire_step
                    del st.session_state.questionnaire_data
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Es gab einen Fehler beim Speichern deiner Antworten.")
        
        if back_clicked:
            st.session_state.questionnaire_step = 2
            st.rerun()


def display_questionnaire_page():
    """
    Controls the multi-step questionnaire flow.
    """
    st.header("Hallo! Willkommen bei Coach Milo.")
    st.info("Damit ich den perfekten Plan für dich erstellen kann, brauche ich ein paar Informationen. Das dauert nur 2-3 Minuten.")

    # Initialize session state for the questionnaire
    if "questionnaire_step" not in st.session_state:
        st.session_state.questionnaire_step = 1
    if "questionnaire_data" not in st.session_state:
        st.session_state.questionnaire_data = {}

    # Display progress bar
    progress_value = (st.session_state.questionnaire_step - 1) / 3
    st.progress(progress_value, text=f"Schritt {st.session_state.questionnaire_step} von 3")
    
    # Render the current step
    if st.session_state.questionnaire_step == 1:
        _render_questionnaire_step1()
    elif st.session_state.questionnaire_step == 2:
        _render_questionnaire_step2()
    elif st.session_state.questionnaire_step == 3:
        _render_questionnaire_step3()


# --- Main App Display (remains mostly unchanged) ---

def render_chat_tab(user_profile):
    st.header("Planung mit Milo")
    logo_url = "https://github.com/StefDo-lab/gym-fragebogen/blob/feature/coach-milo-makeover/logo-dark.png?raw=true"

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hallo! Ich bin Milo. Wollen wir einen neuen Trainingsplan erstellen?"}]
    
    for message in st.session_state.messages:
        avatar_icon = logo_url if message["role"] == "assistant" else "🧑"
        with st.chat_message(message["role"], avatar=avatar_icon):
            st.markdown(message["content"])

    if prompt := st.chat_input("Was möchtest du trainieren?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=logo_url):
            with st.spinner("Milo denkt nach..."):
                history_analysis = "Keine Trainingshistorie zur Analyse vorhanden."
                
                # Use the chat history as the 'additional_info'
                chat_history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in st.session_state.messages])
                
                response = get_chat_response(
                    messages=st.session_state.messages, 
                    user_profile=user_profile, 
                    history_analysis=history_analysis, 
                    additional_info={"text_from_chat": chat_history_text}
                )
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.session_state.latest_plan_text = response
    
    if 'latest_plan_text' in st.session_state:
        st.divider()
        if st.button("Diesen Plan aktivieren", type="primary", use_container_width=True):
            with st.spinner("Plan wird aktiviert..."):
                new_rows = parse_ai_plan_to_rows(st.session_state.latest_plan_text, user_profile)
                if not new_rows:
                    st.error("Der Plan konnte nicht verarbeitet werden. Überprüfe das Format.")
                else:
                    try:
                        # This logic replaces all old workouts with the new ones.
                        supabase_auth_client.table("workouts").delete().eq("uuid", user_profile['uuid']).execute()
                        supabase_auth_client.table("workouts").insert(new_rows).execute()
                        
                        st.success("Dein neuer Plan ist jetzt aktiv!")
                        st.balloons()
                        # Clean up chat state to start fresh
                        if 'messages' in st.session_state: del st.session_state.messages
                        if 'latest_plan_text' in st.session_state: del st.session_state.latest_plan_text
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
        st.info("Du hast noch keinen aktiven Trainingsplan. Wechsle zum 'Chat mit Milo'-Tab, um einen zu erstellen!")
        return

    df = pd.DataFrame(workouts_data)
    # Sort workouts by their first appearance (minimum ID)
    workout_order = df.groupby('workout')['id'].min().sort_values().index.tolist()
    
    for workout_name in workout_order:
        with st.expander(f"**{workout_name}**", expanded=True):
            workout_group = df[df['workout'] == workout_name].copy()
            # Sort exercises within a workout by their first appearance
            exercise_order = workout_group.groupby('exercise')['id'].min().sort_values().index.tolist()
            
            for exercise_name in exercise_order:
                st.markdown(f"##### {exercise_name}")
                exercise_group = workout_group[workout_group['exercise'] == exercise_name].sort_values('set')
                
                # Display coach message once per exercise
                coach_msg = exercise_group.iloc[0].get('messageFromCoach')
                if coach_msg and str(coach_msg).strip():
                    st.info(f"💡 Tipp von Milo: {coach_msg}")

                # Table Header
                header_cols = st.columns([1, 2, 2, 1, 2])
                header_cols[0].markdown("<p class='small-header'>Satz</p>", unsafe_allow_html=True)
                header_cols[1].markdown("<p class='small-header'>Gewicht (kg)</p>", unsafe_allow_html=True)
                header_cols[2].markdown("<p class='small-header'>Wdh.</p>", unsafe_allow_html=True)
                header_cols[3].markdown("<p class='small-header'>RIR</p>", unsafe_allow_html=True)

                for _, row in exercise_group.iterrows():
                    cols = st.columns([1, 2, 2, 1, 2])
                    cols[0].write(f"**{row['set']}**")
                    new_weight = cols[1].number_input("Gewicht", value=float(row['weight']), key=f"w_{row['id']}", min_value=0.0, step=0.5, label_visibility="collapsed")
                    new_reps = cols[2].number_input("Wdh", value=int(row['reps']), key=f"r_{row['id']}", min_value=0, step=1, label_visibility="collapsed")
                    new_rir = cols[3].number_input("RIR", value=int(row.get('rirDone', 0) or 0), key=f"rir_{row['id']}", min_value=0, max_value=10, step=1, label_visibility="collapsed")
                    
                    if row['completed']:
                        cols[4].button("Erledigt ✅", key=f"done_{row['id']}", disabled=True, use_container_width=True)
                    else:
                        if cols[4].button("Abschließen", key=f"save_{row['id']}", type="primary", use_container_width=True):
                            updates = {"weight": new_weight, "reps": new_reps, "rirDone": new_rir, "completed": True, "time": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                            if update_workout_set(row['id'], updates): st.rerun()
                
                st.divider()

    # --- TODO: Manual Editing section could be refactored into its own functions ---
    st.header("Plan bearbeiten")
    # This section for editing could also be expanded in the future.


def display_main_app_page(user_profile):
    st.title(f"Willkommen, {user_profile.get('forename', 'Athlet')}!")
    
    tab1, tab2, tab3 = st.tabs(["🗓️ Training", "💬 Chat mit Milo", "👤 Profil"])
    
    with tab1:
        if 'uuid' in user_profile:
            display_training_tab(user_profile)
        else:
            st.error("Fehler: Keine UUID im Nutzerprofil gefunden.")
    
    with tab2:
        render_chat_tab(user_profile)
        
    with tab3:
        st.header("Dein Profil")
        st.write(f"**Name:** {user_profile.get('forename', '')} {user_profile.get('surename', '')}")
        st.write(f"**E-Mail:** {user_profile.get('email', '')}")
        st.write(f"**Hauptziel:** {user_profile.get('primary_goal')}")
        st.write(f"**Erfahrung:** {user_profile.get('experience_level')}")
        
        st.divider()
        
        if st.button("Logout", use_container_width=True):
            supabase_auth_client.auth.sign_out()
            # Clear all session state keys on logout
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()