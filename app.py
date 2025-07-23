# app.py
# This is the main file that runs the Streamlit app.

import streamlit as st
from supabase_utils import check_user_profile_exists
from ui_components import (
    inject_mobile_styles, 
    display_login_page, 
    display_questionnaire_page, 
    display_main_app_page
)

# --- Page Config and Styling ---
st.set_page_config(
    page_title="Coach Milo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)
inject_mobile_styles()

# --- Main App Logic ---
def main():
    """
    Controls the app's flow based on user's login status and
    questionnaire completion.
    """
    # Initialize session state if keys don't exist
    if "user" not in st.session_state:
        st.session_state.user = None
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = None

    # --- FLOW CONTROL ---

    # 1. If user is not logged in, show login page.
    if not st.session_state.user:
        display_login_page()
        return

    # 2. If user is logged in, but we haven't checked for a profile yet.
    if st.session_state.user and st.session_state.user_profile is None:
        with st.spinner("Lade dein Profil..."):
            profile_exists, profile_data = check_user_profile_exists(st.session_state.user.id)
            if profile_exists:
                # Profile found, store it in session state and rerun to show main app.
                st.session_state.user_profile = profile_data
                st.rerun()
            else:
                # No profile found, mark it as such so we show the questionnaire.
                # We use a specific value to prevent re-checking the DB.
                st.session_state.user_profile = "NO_PROFILE_FOUND"
                st.rerun()
    
    # 3. If we've checked and found a profile, show the main app.
    if isinstance(st.session_state.user_profile, dict):
        display_main_app_page(st.session_state.user_profile)
    
    # 4. If we've checked and found no profile, show the questionnaire.
    elif st.session_state.user_profile == "NO_PROFILE_FOUND":
        display_questionnaire_page()


if __name__ == "__main__":
    main()
