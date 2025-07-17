import streamlit as st
from supabase import create_client, Client

# ---- Supabase Setup ----
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-public-anon-key"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Session State ----
if "user" not in st.session_state:
    st.session_state.user = None
if "mode" not in st.session_state:
    st.session_state.mode = "login"

# ---- Registration ----
def register():
    st.subheader("Registrierung")
    email = st.text_input("E-Mail", key="reg_email")
    password = st.text_input("Passwort", type="password", key="reg_pw")
    if st.button("Registrieren"):
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

# ---- Login ----
def login():
    st.subheader("Login")
    email = st.text_input("E-Mail", key="login_email")
    password = st.text_input("Passwort", type="password", key="login_pw")
    if st.button("Einloggen"):
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

# ---- Logout ----
def logout():
    st.session_state.user = None
    st.success("Du wurdest ausgeloggt.")

# ---- Main ----
st.title("MyGymBuddy - Login & Registrierung")

if st.session_state.user:
    st.success(f"Eingeloggt als {st.session_state.user.email}")
    st.write(f"Deine User-ID: {st.session_state.user.id}")
    if st.button("Logout"):
        logout()
else:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            st.session_state.mode = "login"
    with col2:
        if st.button("Registrieren"):
            st.session_state.mode = "register"

    if st.session_state.mode == "login":
        login()
    else:
        register()
