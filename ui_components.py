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
    delete_exercise, add_exercise, delete_workout, archive_workout_and_analyze,
    load_workout_history
)
from ai_utils import (
    get_initial_plan_response, get_chat_response, 
    parse_ai_plan_to_rows, get_workout_feedback,
    analyze_workout_history
)

# --- General UI Components ---
def inject_mobile_styles():
    """Injects CSS for mobile-friendly styling and to hide Streamlit's default header/footer."""
    st.markdown("""
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden !important;}
        .block-container { padding-top: 1rem; }
        .small-header { font-weight: bold; color: #555; margin-bottom: -10px; }
        .stButton>button {
            width: 100%;
        }
    </style>
    """, unsafe_allow_html=True)

def display_milo_logo():
    """Displays the Coach Milo logo."""
    logo_url = "https://github.com/StefDo-lab/gym-fragebogen/blob/feature/coach-milo-makeover/logo-dark.png?raw=true"
    st.image(logo_url, width=120)

# --- Page Rendering Functions ---
def display_login_page():
    """Renders the login and registration forms."""
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
                        login_res = supabase_auth_client.auth.sign_in_with_password({"email": email, "password": password})
                        if login_res.user:
                            st.session_state.user = login_res.user
                            time.sleep(2)
                            st.rerun()
                except Exception:
                    st.error("Registrierung fehlgeschlagen. Ist die E-Mail schon vergeben?")


# --- QUESTIONNAIRE (UPDATED) ---

def _render_questionnaire_step1():
    st.subheader("Schritt 1: Wer bist du?")
    with st.form("step1_form"):
        q_data = st.session_state.questionnaire_data
        st.write("##### Deine Kontaktdaten")
        forename = st.text_input("Vorname *", value=q_data.get("forename", ""))
        surename = st.text_input("Nachname *", value=q_data.get("surename", ""))
        
        # NEU: Abfrage des Geschlechts
        gender = st.selectbox(
            "Geschlecht *", 
            ["Weiblich", "Männlich", "Divers"], 
            index=["Weiblich", "Männlich", "Divers"].index(q_data.get("gender", "Weiblich"))
        )

        today = datetime.date.today()
        default_bday = q_data.get("birthday", today.replace(year=today.year - 25))
        birthday = st.date_input("Geburtsdatum *", min_value=today.replace(year=today.year - 100), max_value=today.replace(year=today.year - 16), value=default_bday)
        
        st.divider()
        st.write("##### Deine Körpermaße")
        height = st.number_input("Deine Körpergröße (in cm) *", min_value=120, max_value=250, value=q_data.get("height_cm", 175))
        weight = st.number_input("Dein aktuelles Körpergewicht (in kg) *", min_value=40.0, max_value=250.0, value=q_data.get("weight_kg", 75.0), step=0.5)
        bodyfat = st.number_input("Dein Körperfettanteil in % (optional, wenn bekannt)", min_value=3.0, max_value=50.0, value=q_data.get("bodyfat_percentage", 15.0), step=0.25, help="Wenn du diesen Wert nicht kennst, einfach so lassen.")
        
        submitted = st.form_submit_button("Weiter zu Schritt 2", type="primary")
        if submitted:
            if not all([forename, surename, height, weight, gender]):
                st.error("Bitte fülle alle Pflichtfelder (*) aus.")
                return
            # NEU: Geschlecht wird gespeichert
            q_data.update({"forename": forename, "surename": surename, "gender": gender, "birthday": birthday, "height_cm": height, "weight_kg": weight, "bodyfat_percentage": bodyfat})
            st.session_state.questionnaire_step = 2
            st.rerun()

def _render_questionnaire_step2():
    # Diese Funktion bleibt unverändert
    st.subheader("Schritt 2: Deine Ziele & dein Alltag")
    with st.form("step2_form"):
        q_data = st.session_state.questionnaire_data
        st.write("##### Deine Ziele")
        primary_goal = st.selectbox("Was ist dein Hauptziel?", ["Muskelaufbau", "Gewichtsreduktion", "Kraft steigern", "Fitness & Gesundheit", "Rücken stärken"], index=["Muskelaufbau", "Gewichtsreduktion", "Kraft steigern", "Fitness & Gesundheit", "Rücken stärken"].index(q_data.get("primary_goal", "Muskelaufbau")))
        secondary_goals = st.multiselect("Hast du weitere Ziele?", ["Muskelaufbau", "Gewichtsreduktion", "Kraft steigern", "Fitness & Gesundheit", "Rücken stärken"], default=q_data.get("secondary_goals", []))
        specific_goal_text = st.text_input("Was ist dein konkretes, messbares Ziel? (optional)", placeholder="z.B. 100kg Bankdrücken, 10kg abnehmen", value=q_data.get("specific_goal_text", ""))
        st.divider()
        st.write("##### Dein Training")
        experience_level = st.select_slider("Deine Trainingserfahrung", options=["Anfänger (0-1 Jahre)", "Fortgeschritten (1-3 Jahre)", "Erfahren (3+ Jahre)"], value=q_data.get("experience_level", "Anfänger (0-1 Jahre)"))
        training_days_per_week = st.slider("Wie viele Tage pro Woche möchtest du trainieren?", 1, 7, q_data.get("training_days_per_week", 3))
        time_per_session_minutes = st.slider("Wie viel Zeit hast du pro Einheit (in Minuten)?", 30, 120, q_data.get("time_per_session_minutes", 60), step=15)
        use_rir = st.checkbox("Soll 'Reps in Reserve' (RIR) zur Steuerung der Intensität genutzt werden?", value=q_data.get("use_rir", False), help="RIR gibt an, wie viele Wiederholungen du am Ende eines Satzes noch geschafft hättest. RIR 2 bedeutet z.B., dass du noch 2 weitere Wiederholungen mit sauberer Technik geschafft hättest.")
        training_location = st.selectbox("Wo trainierst du hauptsächlich?", ["Voll ausgestattetes Fitnessstudio", "Home-Gym (Basisausstattung)", "Nur mit Körpergewicht"], index=["Voll ausgestattetes Fitnessstudio", "Home-Gym (Basisausstattung)", "Nur mit Körpergewicht"].index(q_data.get("training_location", "Voll ausgestattetes Fitnessstudio")))
        liked_equipment = st.text_input("Gibt es Ausrüstung, die du besonders gerne nutzt?", placeholder="z.B. Kettlebells, Langhantel", value=q_data.get("liked_equipment", ""))
        disliked_exercises = st.text_input("Gibt es Übungen, die du gar nicht magst?", placeholder="z.B. Kniebeugen, Burpees", value=q_data.get("disliked_exercises", ""))
        st.divider()
        st.write("##### Dein Alltag & Lifestyle")
        job_activity_level = st.selectbox("Wie körperlich aktiv ist dein Beruf?", ["Hauptsächlich sitzend", "Meistens stehend/gehend", "Körperlich anstrengend"], index=["Hauptsächlich sitzend", "Meistens stehend/gehend", "Körperlich anstrengend"].index(q_data.get("job_activity_level", "Hauptsächlich sitzend")))
        sleep_hours_avg = st.slider("Wie viele Stunden schläfst du durchschnittlich pro Nacht?", 4.0, 12.0, q_data.get("sleep_hours_avg", 7.5), step=0.5)
        nutrition_style = st.selectbox("Welcher Ernährungsstil beschreibt dich am besten?", ["Ich achte nicht besonders darauf", "Ausgewogen & gesund", "Proteinreich", "Vegetarisch", "Vegan"], index=["Ich achte nicht besonders darauf", "Ausgewogen & gesund", "Proteinreich", "Vegetarisch", "Vegan"].index(q_data.get("nutrition_style", "Ich achte nicht besonders darauf")))
        col1, col2 = st.columns(2)
        with col1:
            back_clicked = st.form_submit_button("Zurück zu Schritt 1")
        with col2:
            next_clicked = st.form_submit_button("Weiter zu Schritt 3", type="primary")
        if next_clicked:
            q_data.update({"primary_goal": primary_goal, "secondary_goals": secondary_goals, "specific_goal_text": specific_goal_text, "experience_level": experience_level, "training_days_per_week": training_days_per_week, "time_per_session_minutes": time_per_session_minutes, "use_rir": use_rir, "training_location": training_location, "liked_equipment": liked_equipment, "disliked_exercises": disliked_exercises, "job_activity_level": job_activity_level, "sleep_hours_avg": sleep_hours_avg, "nutrition_style": nutrition_style})
            st.session_state.questionnaire_step = 3
            st.rerun()
        if back_clicked:
            st.session_state.questionnaire_step = 1
            st.rerun()

def _render_questionnaire_step3():
    st.subheader("Schritt 3: Dein Gesundheits-Check & Mindset")
    with st.form("step3_form"):
        q_data = st.session_state.questionnaire_data
        st.write("##### Gesundheitliche Angaben")
        medical_topics = st.multiselect("Welche der folgenden gesundheitlichen Themen treffen auf dich zu? (optional)", ["Kürzliche Operation", "Ausstrahlende Schmerzen", "Bandscheibenvorfall", "Bluthochdruck", "Herzprobleme"], default=q_data.get("medical_topics", []))
        st.text_area("Falls du oben eine oder mehrere Optionen ausgewählt hast, beschreibe sie hier bitte im Detail.", placeholder="z.B. Bandscheibenvorfall HWS vor 5 Jahren, komplett verheilt.", key="medical_topics_details", value=q_data.get("medical_topics_details", ""))
        st.text_area("Gibt es aktuelle Schmerzen oder Verletzungen, die dein Training beeinflussen könnten?", key="pain_and_injury_notes", value=q_data.get("pain_and_injury_notes", ""))
        st.text_area("Weitere Anmerkungen zu deiner Gesundheit (optional)", key="other_health_notes", value=q_data.get("other_health_notes", ""))
        st.divider()
        st.write("##### Mindset & Erholung")
        sleep_quality_rating = st.slider("Wie bewertest du deine Schlafqualität (1=schlecht, 10=hervorragend)?", 1, 10, q_data.get("sleep_quality_rating", 7))
        stress_level_rating = st.slider("Wie ist dein aktuelles Stresslevel (1=entspannt, 10=sehr hoch)?", 1, 10, q_data.get("stress_level_rating", 5))
        motivation_level = st.slider("Wie motiviert bist du gerade auf einer Skala von 1-10?", 1, 10, q_data.get("motivation_level", 8), help="1 = 'Ich muss mich zwingen', 10 = 'Ich könnte Bäume ausreißen!'")
        col1, col2 = st.columns(2)
        with col1:
            back_clicked = st.form_submit_button("Zurück zu Schritt 2")
        with col2:
            submitted = st.form_submit_button("Meine Antworten an Milo senden", type="primary")
        if submitted:
            q_data.update({"medical_topics": medical_topics, "medical_topics_details": st.session_state.medical_topics_details, "pain_and_injury_notes": st.session_state.pain_and_injury_notes, "other_health_notes": st.session_state.other_health_notes, "sleep_quality_rating": sleep_quality_rating, "stress_level_rating": stress_level_rating, "motivation_level": motivation_level})
            with st.spinner("Speichere deine Antworten..."):
                # NEU: Geschlecht wird in die Datenbank geschrieben
                db_payload = {
                    "auth_user_id": st.session_state.user.id, "uuid": str(uuid.uuid4()), 
                    "forename": q_data.get("forename"), "surename": q_data.get("surename"),
                    "email": st.session_state.user.email, "birthday": str(q_data.get("birthday")),
                    "gender": q_data.get("gender"), "height_cm": q_data.get("height_cm"), 
                    "weight_kg": q_data.get("weight_kg"), "bodyfat_percentage": q_data.get("bodyfat_percentage"),
                    "job_activity_level": q_data.get("job_activity_level"), "sleep_hours_avg": q_data.get("sleep_hours_avg"),
                    "nutrition_style": q_data.get("nutrition_style"), "training_days_per_week": q_data.get("training_days_per_week"),
                    "time_per_session_minutes": q_data.get("time_per_session_minutes"), "training_location": q_data.get("training_location"),
                    "experience_level": q_data.get("experience_level"), "primary_goal": q_data.get("primary_goal"),
                    "use_rir": q_data.get("use_rir"), 
                    "has_restrictions": len(q_data.get("medical_topics", [])) > 0 or bool(q_data.get("pain_and_injury_notes", "").strip()),
                }
                context_payload = {"secondary_goals": q_data.get("secondary_goals"), "specific_goal_text": q_data.get("specific_goal_text"), "liked_equipment": q_data.get("liked_equipment"), "disliked_exercises": q_data.get("disliked_exercises"), "sleep_quality_rating": q_data.get("sleep_quality_rating"), "stress_level_rating": q_data.get("stress_level_rating"), "motivation_level": q_data.get("motivation_level"), "medical_topics_details": q_data.get("medical_topics_details"), "pain_and_injury_notes": q_data.get("pain_and_injury_notes"), "other_health_notes": q_data.get("other_health_notes"),}
                db_payload["context_and_preferences"] = context_payload
                response = insert_questionnaire_data(db_payload)
                if response:
                    st.success("Super, danke! Dein Profil ist gespeichert.")
                    st.session_state.user_profile = db_payload
                    del st.session_state.questionnaire_step
                    del st.session_state.questionnaire_data
                    st.session_state.run_initial_plan_generation = True
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Es gab einen Fehler beim Speichern deiner Antworten.")
        if back_clicked:
            st.session_state.questionnaire_step = 2
            st.rerun()

def display_questionnaire_page():
    st.header("Hallo! Willkommen bei Coach Milo.")
    st.info("Damit ich den perfekten Plan für dich erstellen kann, brauche ich ein paar Informationen. Das dauert nur 2-3 Minuten.")
    if "questionnaire_step" not in st.session_state:
        st.session_state.questionnaire_step = 1
    if "questionnaire_data" not in st.session_state:
        st.session_state.questionnaire_data = {}
    progress_value = (st.session_state.questionnaire_step - 1) / 3
    st.progress(progress_value, text=f"Schritt {st.session_state.questionnaire_step} von 3")
    if st.session_state.questionnaire_step == 1:
        _render_questionnaire_step1()
    elif st.session_state.questionnaire_step == 2:
        _render_questionnaire_step2()
    elif st.session_state.questionnaire_step == 3:
        _render_questionnaire_step3()


# --- Main App Display (UPDATED) ---

def render_chat_tab(user_profile):
    """Renders the main chat interface, including the plan 'canvas' and new controls."""
    st.header("Planung mit Milo")
    logo_url = "https://github.com/StefDo-lab/gym-fragebogen/blob/feature/coach-milo-makeover/logo-dark.png?raw=true"

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "latest_plan_text" not in st.session_state:
        st.session_state.latest_plan_text = ""

    # NEU: Steuerungselemente für die Planerstellung
    with st.expander("Neuen Plan anfordern oder anpassen"):
        plan_params = {}
        plan_params['days'] = st.slider("Trainingstage pro Woche", 1, 7, user_profile.get("training_days_per_week", 3))
        plan_params['split'] = st.selectbox(
            "Split-Typ", 
            ["Ganzkörper", "Oberkörper/Unterkörper", "Push/Pull/Beine", "Individuell"],
            index=["Ganzkörper", "Oberkörper/Unterkörper", "Push/Pull/Beine", "Individuell"].index(user_profile.get("split_type", "Ganzkörper"))
        )
        plan_params['focus'] = st.selectbox(
            "Fokus",
            ["Muskelaufbau", "Kraftsteigerung", "Fettreduktion", "Allgemeine Fitness"],
            index=["Muskelaufbau", "Kraftsteigerung", "Fettreduktion", "Allgemeine Fitness"].index(user_profile.get("primary_goal", "Muskelaufbau"))
        )
        
        # NEU: Der explizite Button zum Anfordern eines Plans
        if st.button("Neuen Plan mit diesen Einstellungen anfordern", type="primary", use_container_width=True):
            with st.spinner("Milo erstellt deinen neuen Plan basierend auf den Einstellungen..."):
                # Wir übergeben die neuen Parameter direkt an die KI-Funktion
                response_text = get_chat_response(
                    st.session_state.messages, 
                    user_profile, 
                    plan_request_params=plan_params
                )
                st.session_state.latest_plan_text = response_text
                
                # Begrüßungstext für den Chat extrahieren
                if "TEIL 2 - DER TRAININGSPLAN" in response_text:
                    conversational_part = response_text.split("TEIL 2 - DER TRAININGSPLAN")[0]
                else:
                    conversational_part = response_text
                
                st.session_state.messages.append({"role": "assistant", "content": conversational_part})
                st.rerun()

    # Initial Plan Generation (läuft nur einmal nach dem Fragebogen)
    if st.session_state.get("run_initial_plan_generation", False):
        st.session_state.run_initial_plan_generation = False
        with st.spinner("Milo analysiert dein Profil und erstellt einen ersten Plan-Vorschlag..."):
            initial_plan = get_initial_plan_response(user_profile)
            st.session_state.latest_plan_text = initial_plan
            if "TEIL 2 - DER TRAININGSPLAN" in initial_plan:
                conversational_part = initial_plan.split("TEIL 2 - DER TRAININGSPLAN")[0]
            else:
                conversational_part = initial_plan
            st.session_state.messages.append({"role": "assistant", "content": conversational_part})
            st.rerun()

    # Display the latest plan in an expander
    if st.session_state.latest_plan_text:
        with st.expander("Dein aktueller Plan-Vorschlag", expanded=True):
            st.markdown(st.session_state.latest_plan_text)
            if st.button("Diesen Plan aktivieren", use_container_width=True, key="activate_plan_expander"):
                with st.spinner("Plan wird aktiviert..."):
                    new_rows = parse_ai_plan_to_rows(st.session_state.latest_plan_text, user_profile)
                    if not new_rows:
                        st.error("Der Plan konnte nicht verarbeitet werden.")
                    else:
                        try:
                            supabase_auth_client.table("workouts").delete().eq("uuid", user_profile['uuid']).execute()
                            supabase_auth_client.table("workouts").insert(new_rows).execute()
                            st.success("Dein neuer Plan ist jetzt aktiv!")
                            st.balloons()
                            st.session_state.messages = []
                            st.session_state.latest_plan_text = ""
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ein Fehler ist beim Aktivieren des Plans aufgetreten: {e}")
        st.divider()

    # Display chat history
    for message in st.session_state.messages:
        avatar_icon = logo_url if message["role"] == "assistant" else "🧑"
        with st.chat_message(message["role"], avatar=avatar_icon):
            st.markdown(message["content"])

    # Handle user input for general chat
    if prompt := st.chat_input("Stelle Fragen oder gib Änderungswünsche ein"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=logo_url):
            with st.spinner("Milo denkt nach..."):
                # Hier wird kein plan_request_params übergeben -> normaler Chat
                full_response = get_chat_response(st.session_state.messages, user_profile)
                
                plan_update_match = re.search(r'<PLAN_UPDATE>(.*)</PLAN_UPDATE>', full_response, re.DOTALL)
                
                if plan_update_match:
                    new_plan_text = plan_update_match.group(1).strip()
                    st.session_state.latest_plan_text = new_plan_text
                    conversational_part = re.sub(r'<PLAN_UPDATE>.*</PLAN_UPDATE>', '', full_response, flags=re.DOTALL).strip()
                elif "TEIL 2 - DER TRAININGSPLAN" in full_response:
                    new_plan_text = full_response
                    st.session_state.latest_plan_text = new_plan_text
                    conversational_part = full_response.split("TEIL 2 - DER TRAININGSPLAN")[0].strip()
                else:
                    conversational_part = full_response

                st.session_state.messages.append({"role": "assistant", "content": conversational_part})
                st.rerun()

def display_training_tab(user_profile: dict):
    """Renders the currently active training plan with editing capabilities."""
    st.header("Dein aktueller Plan")
    user_profile_uuid = user_profile.get('uuid')
    user_name = f"{user_profile.get('forename', '')} {user_profile.get('surename', '')}".strip()
    
    if not user_profile_uuid:
        st.error("Profil-UUID nicht gefunden. Kann Plan nicht laden.")
        return

    workouts_data = load_user_workouts(user_profile_uuid)

    if not workouts_data:
        st.info("Du hast noch keinen aktiven Trainingsplan. Wechsle zum 'Chat mit Milo'-Tab, um einen zu erstellen!")
        return

    df = pd.DataFrame(workouts_data)
    workout_order = df.groupby('workout')['id'].min().sort_values().index.tolist()
    
    for workout_name in workout_order:
        with st.expander(f"**{workout_name}**", expanded=True):
            workout_group = df[df['workout'] == workout_name].copy()
            
            all_sets_completed = all(workout_group['completed'])
            if st.button("Workout abschließen & Feedback erhalten", key=f"finish_wo_{workout_name}", disabled=not all_sets_completed, use_container_width=True, type="primary"):
                with st.spinner("Milo schaut sich deine Leistung an..."):
                    success, analysis = archive_workout_and_analyze(user_profile_uuid, workout_name)
                    if success:
                        feedback = get_workout_feedback(analysis)
                        st.success(feedback)
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(analysis)

            exercise_order = workout_group.groupby('exercise')['id'].min().sort_values().index.tolist()
            
            for exercise_name in exercise_order:
                st.markdown(f"##### {exercise_name}")
                exercise_group_sorted = workout_group[workout_group['exercise'] == exercise_name].sort_values('set')
                
                coach_msg = exercise_group_sorted.iloc[0].get('messagefromcoach')
                if coach_msg and str(coach_msg).strip():
                    st.info(f"💡 Tipp von Milo: {coach_msg}")

                header_cols = st.columns([1, 2, 2, 1, 2])
                header_cols[0].markdown("<p class='small-header'>Satz</p>", unsafe_allow_html=True)
                header_cols[1].markdown("<p class='small-header'>Gewicht (kg)</p>", unsafe_allow_html=True)
                header_cols[2].markdown("<p class='small-header'>Wdh.</p>", unsafe_allow_html=True)
                header_cols[3].markdown("<p class='small-header'>RIR</p>", unsafe_allow_html=True)

                for _, row in exercise_group_sorted.iterrows():
                    cols = st.columns([1, 2, 2, 1, 2])
                    cols[0].write(f"**{row['set']}**")
                    new_weight = cols[1].number_input("Gewicht", value=float(row['weight']), key=f"w_{row['id']}", min_value=0.0, step=0.5, label_visibility="collapsed")
                    new_reps = cols[2].number_input("Wdh", value=int(row['reps']), key=f"r_{row['id']}", min_value=0, step=1, label_visibility="collapsed")
                    new_rir = cols[3].number_input("RIR", value=int(row.get('rirdone', 0) or 0), key=f"rir_{row['id']}", min_value=0, max_value=10, step=1, label_visibility="collapsed")
                    
                    if row['completed']:
                        cols[4].button("Erledigt ✅", key=f"done_{row['id']}", disabled=True, use_container_width=True)
                    else:
                        if cols[4].button("Abschließen", key=f"save_{row['id']}", type="primary", use_container_width=True):
                            updates = {"weight": new_weight, "reps": new_reps, "rirdone": new_rir, "completed": True, "time": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                            if update_workout_set(row['id'], updates): st.rerun()
                
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    if st.button("➕ Satz", key=f"add_set_{exercise_name}_{workout_name}"):
                        last_set_data = exercise_group_sorted.iloc[-1].to_dict()
                        new_set_number = int(last_set_data['set']) + 1
                        last_set_data['set'] = new_set_number
                        last_set_data['completed'] = False
                        del last_set_data['id']
                        if add_set(last_set_data): st.rerun()
                with btn_cols[1]:
                    if len(exercise_group_sorted) > 1 and st.button("➖ Satz", key=f"del_set_{exercise_name}_{workout_name}"):
                        last_set_id = exercise_group_sorted.iloc[-1]['id']
                        if delete_set(last_set_id): st.rerun()
                with btn_cols[2]:
                    if st.button("🗑️ Übung", key=f"del_ex_{exercise_name}_{workout_name}"):
                        if delete_exercise(exercise_group_sorted['id'].tolist()): st.rerun()

                with st.expander("💬 Nachricht an Milo"):
                    message_to_coach = st.text_area("Dein Feedback zur Übung", value=row.get('messagetocoach', ''), key=f"msg_area_{exercise_name}_{workout_name}")
                    if st.button("Nachricht senden", key=f"send_msg_btn_{exercise_name}_{workout_name}"):
                        for set_id in exercise_group_sorted['id']:
                            update_workout_set(set_id, {"messagetocoach": message_to_coach})
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
                        reps_for_db_match = re.search(r'\d+', ex_reps_str)
                        reps_for_db = int(reps_for_db_match.group(0)) if reps_for_db_match else 10
                        new_ex_rows = []
                        for i in range(1, ex_sets + 1):
                            new_ex_rows.append({'uuid': user_profile_uuid, 'date': datetime.date.today().isoformat(), 'name': user_name, 'workout': workout_name, 'exercise': ex_name, 'set': i, 'weight': ex_weight, 'reps': reps_for_db, 'completed': False, 'messagefromcoach': f"Ziel: {ex_reps_str} Wdh."})
                        if add_exercise(new_ex_rows): st.rerun()
            
            if st.button("🗑️ Gesamtes Workout löschen", key=f"del_wo_{workout_name}"):
                if delete_workout(workout_group['id'].tolist()): st.rerun()

    with st.expander("➕ Neues Workout erstellen"):
        with st.form(key="add_workout_form"):
            wo_name = st.text_input("Name des neuen Workouts")
            if st.form_submit_button("Erstellen"):
                dummy_exercise = [{'uuid': user_profile_uuid, 'date': datetime.date.today().isoformat(), 'name': user_name, 'workout': wo_name, 'exercise': "Neue Übung", 'set': 1, 'weight': 0, 'reps': 10, 'completed': False}]
                if add_exercise(dummy_exercise): st.rerun()

def display_statistics_tab(user_profile: dict):
    """Renders the statistics and history page."""
    st.header("Deine Fortschritte")
    user_uuid = user_profile.get('uuid')

    if not user_uuid:
        st.error("Profil-UUID nicht gefunden. Kann Statistiken nicht laden.")
        return

    history_data = load_workout_history(user_uuid)

    if not history_data:
        st.info("Noch keine abgeschlossenen Workouts vorhanden. Schließe ein Training ab, um hier deine Statistiken zu sehen!")
        return
    
    analysis_text, df_history = analyze_workout_history(history_data)

    st.subheader("Leistungsentwicklung")

    exercise_list = sorted(df_history['exercise'].unique())
    selected_exercise = st.selectbox("Wähle eine Übung zur Analyse:", exercise_list)

    if selected_exercise:
        ex_df = df_history[df_history['exercise'] == selected_exercise].copy()
        ex_df['date'] = pd.to_datetime(ex_df['date'])
        
        daily_max_weight = ex_df.groupby('date')['weight'].max()
        ex_df['volume'] = ex_df['weight'] * ex_df['reps']
        daily_volume = ex_df.groupby('date')['volume'].sum()

        st.markdown(f"**Gewichtsentwicklung für {selected_exercise}**")
        if not daily_max_weight.empty:
            st.line_chart(daily_max_weight)
        else:
            st.write("Keine Gewichtsdaten für diese Übung vorhanden.")

        st.markdown(f"**Volumenentwicklung für {selected_exercise} (Gewicht * Wdh.)**")
        if not daily_volume.empty:
            st.line_chart(daily_volume)
        else:
            st.write("Keine Volumendaten für diese Übung vorhanden.")

    st.divider()

    st.subheader("Milos Analyse deiner Trainingshistorie")
    st.text(analysis_text)


def display_main_app_page(user_profile):
    """Controls the main app layout with tabs."""
    st.title(f"Willkommen, {user_profile.get('forename', 'Athlet')}!")
    
    tabs = ["🗓️ Training", "💬 Chat mit Milo", "📊 Statistiken", "👤 Profil"]
    
    if st.session_state.get("run_initial_plan_generation", False):
        st.info("🤖 Milo erstellt deinen ersten Plan-Vorschlag im 'Chat mit Milo'-Tab. Bitte wechsle dorthin, um ihn zu sehen.")

    tab1, tab2, tab3, tab4 = st.tabs(tabs)
    
    with tab1:
        display_training_tab(user_profile)
    
    with tab2:
        render_chat_tab(user_profile)

    with tab3:
        display_statistics_tab(user_profile)
        
    with tab4:
        st.header("Dein Profil")
        st.write(f"**Name:** {user_profile.get('forename', '')} {user_profile.get('surename', '')}")
        st.write(f"**E-Mail:** {user_profile.get('email', '')}")
        
        # NEU: Zeigt die angereicherten Daten im Profil an
        st.write(f"**Alter:** {user_profile.get('age', 'N/A')}")
        st.write(f"**Geschlecht:** {user_profile.get('gender', 'N/A')}")
        st.write(f"**BMI:** {user_profile.get('bmi', 'N/A')}")
        st.write(f"**Fettfreie Masse:** {user_profile.get('lean_body_mass_kg', 'N/A')} kg")

        st.divider()
        st.write(f"**Hauptziel:** {user_profile.get('primary_goal')}")
        st.write(f"**Erfahrung:** {user_profile.get('experience_level')}")
        
        st.divider()
        
        if st.button("Logout", use_container_width=True):
            supabase_auth_client.auth.sign_out()
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
