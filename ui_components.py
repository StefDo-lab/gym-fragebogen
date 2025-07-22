# ui_components.py
# This file contains functions that render parts of the Streamlit UI.

import streamlit as st
import datetime
import uuid
from supabase_utils import supabase_auth_client, insert_data

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
        /* Add more of your custom CSS from the original file here */
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
    st.info("Hallo! Ich bin Milo. Um den perfekten Plan für dich zu erstellen, muss ich dich erst ein wenig kennenlernen. Das dauert nur 2 Minuten.")

    with st.form("fitness_fragebogen"):
        # This is the full form from your questionnaire app.
        # For brevity, only a few fields are shown here.
        # Copy all your st.text_input, st.selectbox etc. here.
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

def display_main_app_page():
    """Displays the main workout tracker UI with tabs."""
    st.title(f"Coach Milo")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Training", "Chat mit Milo", "Stats", "Profil"])

    with tab1:
        st.header("Dein Training heute")
        # ... (Logic from your workout tracker's tab1 goes here) ...

    with tab2:
        st.header("Planung mit Milo")
        st.info("Hier entsteht bald der interaktive Chat mit Milo.")
        # ... (This will become the interactive chat) ...

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