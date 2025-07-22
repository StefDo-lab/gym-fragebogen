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
        # We check the session state first to avoid repeated database calls.
        if not st.session_state.questionnaire_complete:
            # Check the database once per session
            profile_exists, _ = check_user_profile_exists(st.session_state.user.id)
            if profile_exists:
                st.session_state.questionnaire_complete = True
            else:
                # If no profile, show the questionnaire
                display_questionnaire_page()
                return # Stop further execution until form is submitted
        
        # If profile exists, show the main app
        if st.session_state.questionnaire_complete:
            display_main_app_page()

if __name__ == "__main__":
    main()