import streamlit as st
from supabase import create_client, Client

url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

if "user" not in st.session_state:
    st.session_state.user = None
if "mode" not in st.session_state:
    st.session_state.mode = "login"

def register():
    st.subheader("Registrierung")
    email = st.text_input("E-Mail", key="reg_email")
    password = st.text_input("Passwort", type="password", key="reg_pw")
    if st.button("Jetzt registrieren", key="reg_button"):
        try:
            res = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            if res.user:
                st.success("Registrierung erfolgreich! Bitte E-Mail bestätigen.")
                st.session_state.mode = "login"
        except Exception as e:
            st.error(f"Registrierung fehlgeschlagen: {e}")

def login():
    st.subheader("Login")
    email = st.text_input("E-Mail", key="login_email")
    password = st.text_input("Passwort", type="password", key="login_pw")
    if st.button("Jetzt einloggen", key="login_button"):
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            if res.user:
                st.session_state.user = res.user
                st.success(f"Willkommen, {res.user.email} 👋")
        except Exception as e:
            st.error(f"Login fehlgeschlagen: {e}")

def logout():
    st.session_state.user = None
    st.success("Du wurdest ausgeloggt.")

st.title("MyGymBuddy - Login & Registrierung")

if st.session_state.user:
    st.success(f"Eingeloggt als {st.session_state.user.email}")
    st.write(f"Deine User-ID: {st.session_state.user.id}")
    if st.button("Logout", key="logout_button"):
        logout()
else:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login auswählen", key="switch_login"):
            st.session_state.mode = "login"
    with col2:
        if st.button("Registrierung auswählen", key="switch_register"):
            st.session_state.mode = "register"

    if st.session_state.mode == "login":
        login()
    else:
        register()
