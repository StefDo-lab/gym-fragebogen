# app.py
# This is the main file that runs the Streamlit app.

import streamlit as st
# --- KORREKTUR: Unnötigen und falschen Import entfernt ---
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
    page_icon="🤖", # You can use an emoji or a URL to your favicon
    layout="wide",
    initial_sidebar_state="collapsed"
)
inject_mobile_styles()

# --- Session State Initialization ---
if "user" not in st.session_state:
    st.session_state.user = None
if "questionnaire_complete" not in st.session_state:
    st.session_state.questionnaire_complete = False
if "user_profile" not in st.session_state:
    st.session_state.user_profile = None


# --- Main App Logic ---
def main():
    """
    This is the main function that controls the app's flow.
    It decides which page to show based on the user's login status
    and whether they have completed the questionnaire.
    """
    # Check if user is logged in
    if not st.session_state.user:
        display_login_page()
    else:
        # If user is logged in, check if they have a profile.
        # We cache the profile in session_state to avoid repeated database calls.
        if st.session_state.user_profile is None:
            profile_exists, profile_data = check_user_profile_exists(st.session_state.user.id)
            if profile_exists:
                st.session_state.questionnaire_complete = True
                st.session_state.user_profile = profile_data
            else:
                # If no profile, show the questionnaire
                display_questionnaire_page()
                return # Stop further execution until form is submitted
        
        # If profile exists, show the main app
        if st.session_state.questionnaire_complete:
            display_main_app_page(st.session_state.user_profile)

if __name__ == "__main__":
    main()
