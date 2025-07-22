# ui_components.py
# This file contains functions that render parts of the Streamlit UI.

import streamlit as st
import datetime
import uuid
import time
import pandas as pd
from supabase_utils import supabase_auth_client, insert_data, get_user_profile_by_data_uuid, load_user_workouts
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
        /* Add the rest of your custom CSS from the original file here */
    </style>
    """, unsafe_allow_html=True)

def display_milo_logo():
    """Displays the Coach Milo logo."""
    # IMPORTANT: Upload your logo to your GitHub repository and get the raw URL.
    # Replace the placeholder URL below with your actual logo URL.
    logo_url = "https://raw.githubusercontent.com/dein-github-user/dein-repo/feature/coach-milo-makeover/logo.png" #<-- ANPASSEN
    try:
        st.image(logo_url, width=120)
    except Exception:
        st.warning("Logo konnte nicht geladen werden. Bitte URL in ui_components.py anpassen.")

# --- Page Rendering Functions ---

def display_login_page():
    """Displays the login and registration forms with Milo branding."""
    display_milo_logo()
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
                        st.rerun()
                except Exception as e:
                    st.error(f"Login fehlgeschlagen. Bitte prüfe deine Eingaben.")
    
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
                    st.error(f"Registrierung fehlgeschlagen: {e}")

def display_questionnaire_page():
    """Displays the questionnaire form for new users."""
    display_milo_logo()
    st.header("Lerne deinen Coach Milo kennen")
    st.info("Hallo! Ich bin Milo, dein persönlicher KI-Coach. Um den perfekten Plan für dich zu erstellen, muss ich dich erst ein wenig kennenlernen. Das dauert nur 2 Minuten.")

    with st.form("fitness_fragebogen"):
        # This is the full form from your questionnaire app.
        st.header("Persönliche Daten")
        forename = st.text_input("Vorname *")
        surename = st.text_input("Nachname *")
        
        today = datetime.date.today()
        min_date = today.replace(year=today.year - 100)
        max_date = today.replace(year=today.year - 16)
        birthday = st.date_input("Geburtsdatum *", min_value=min_date, max_value=max_date, value=max_date)
        
        # ... (PASTE ALL OTHER FORM FIELDS FROM YOUR QUESTIONNAIRE HERE) ...
        
        abgeschickt = st.form_submit_button("Meine Antworten an Milo senden")

        if abgeschickt:
            if not forename or not surename:
                st.error("Bitte fülle mindestens Vor- und Nachname aus.")
            else:
                data_payload = {
                    "auth_user_id": st.session_state.user.id,
                    "uuid": str(uuid.uuid4()),
                    "forename": forename,
                    "surename": surename,
                    "birthday": str(birthday),
                    "email": st.session_state.user.email,
                    # ... (PASTE ALL OTHER PAYLOAD FIELDS HERE) ...
                }
                response = insert_data("questionaire", data_payload)
                if response.status_code in [200, 201]:
                    st.success("Danke! Milo hat deine Daten erhalten. Du wirst jetzt zur App weitergeleitet.")
                    st.balloons()
                    st.session_state.questionnaire_complete = True
                    time.sleep(2) # Give user time to read the message
                    st.rerun()
                else:
                    st.error(f"Fehler beim Speichern: {response.text}")

def render_chat_tab(user_profile, history_summary):
    """Renders the interactive chat UI for plan generation."""
    st.header("Planung mit Milo")

    # Initialize chat history in session state if it doesn't exist
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hallo! Ich bin Milo. Wollen wir einen neuen Trainingsplan erstellen? Sag mir einfach, was du dir vorstellst."}]

    # Display existing messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Get user input
    if prompt := st.chat_input("Was möchtest du trainieren?"):
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Milo denkt nach..."):
                # For the very first user message, we inject the profile and history
                if len(st.session_state.messages) == 2: # Assistant welcome + first user prompt
                    full_initial_prompt = f"""
Hier sind die Hintergrundinformationen über den Nutzer. Erstelle basierend darauf und seiner Anfrage den ersten Plan.

---
BENUTZERPROFIL:
{user_profile}
---
TRAININGSHISTORIE:
{history_summary}
---
AKTUELLE ANFRAGE DES NUTZERS:
{prompt}
"""
                    # Create a temporary history for the first call
                    temp_history = [{"role": "user", "content": full_initial_prompt}]
                    response = get_chat_response(temp_history)
                else:
                    # For all subsequent messages, just send the conversation history
                    response = get_chat_response(st.session_state.messages)
                
                st.markdown(response)
                # Add assistant response to history
                st.session_state.messages.append({"role": "assistant", "content": response})

                # Store the latest plan for activation
                st.session_state.latest_plan_text = response


    # "Activate Plan" button should be visible if a plan has been generated
    if 'latest_plan_text' in st.session_state and st.session_state.latest_plan_text:
        st.divider()
        if st.button("Diesen Plan aktivieren", type="primary", use_container_width=True):
            # Here you would call the parsing and database insertion logic
            st.success("Plan wird aktiviert... (Logik hier einfügen)")
            # Reset chat for the next planning session
            del st.session_state.messages
            del st.session_state.latest_plan_text
            st.rerun()


def display_main_app_page(user_profile):
    """Displays the main workout tracker UI with tabs."""
    st.title(f"Coach Milo")
    
    # We need the user's data UUID for most operations
    user_data_uuid = user_profile.get("uuid")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Training", "Chat mit Milo", "Stats", "Profil"])

    with tab1:
        st.header("Dein Training heute")
        workouts = load_user_workouts(user_data_uuid)
        if not workouts:
            st.info("Du hast noch keine aktiven Workouts. Erstelle einen neuen Plan im 'Chat mit Milo'-Tab!")
        else:
            df = pd.DataFrame(workouts)
            # ... (Logic from your workout tracker's tab1 to display workouts goes here) ...
            st.dataframe(df) # Placeholder

    with tab2:
        # We need the history summary for the chat context
        # Note: This is a simplified call. In a real app, you'd build the summary properly.
        history_summary = "Keine Trainingshistorie vorhanden." # Placeholder
        render_chat_tab(user_profile, history_summary)

    with tab3:
        st.header("Deine Fortschritte")
        # ... (Logic from your workout tracker's tab3 goes here) ...
    
    with tab4:
        st.header("Dein Profil")
        # ... (The questionnaire form will be moved here for editing) ...
        if st.button("Logout"):
            supabase_auth_client.auth.sign_out()
            st.session_state.user = None
            st.rerun()
