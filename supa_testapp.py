import streamlit as st
from supabase import create_client, Client

# ---- Supabase Setup ----
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-anon-key"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Session State Setup ----
if "user" not in st.session_state:
    st.session_state.user = None

# ---- Login Form ----
def login():
    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Passwort", type="password")
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
st.title("MyGymBuddy - Login Test")

if st.session_state.user:
    st.success(f"Eingeloggt als {st.session_state.user.email}")
    st.write(f"Deine User-ID: {st.session_state.user.id}")
    if st.button("Logout"):
        logout()
else:
    login()
