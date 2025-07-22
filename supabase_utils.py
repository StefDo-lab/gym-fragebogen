# supabase_utils.py
# This file handles all communication with the Supabase database.

import streamlit as st
import requests
from supabase import create_client

# --- Supabase Client Initialization ---
# Use a function to initialize to avoid running it on every import and cache the resource.
@st.cache_resource
def init_supabase_client():
    """Initializes and returns the Supabase client for authentication."""
    url = st.secrets["supabase_url"]
    # The 'anon' key is used for user authentication (Login/Register)
    anon_key = st.secrets["supabase_key"]
    return create_client(url, anon_key)

# This is the client for handling user login, registration, etc.
supabase_auth_client = init_supabase_client()

# --- Generic Database Functions using the Service Role Key for elevated privileges ---
def _get_service_headers():
    """Returns the authorization headers required for admin-level access."""
    return {
        "apikey": st.secrets["supabase_service_role_key"],
        "Authorization": f'Bearer {st.secrets["supabase_service_role_key"]}',
        "Content-Type": "application/json"
    }

def get_data(table, filters=None):
    """Fetches data from a specified table."""
    url = f'{st.secrets["supabase_url"]}/rest/v1/{table}'
    if filters:
        url += f"?{filters}"
    
    response = requests.get(url, headers=_get_service_headers())
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching data from {table}: {response.text}")
        return []

def insert_data(table, data):
    """Inserts data into a specified table."""
    url = f'{st.secrets["supabase_url"]}/rest/v1/{table}'
    response = requests.post(url, headers=_get_service_headers(), json=data)
    return response

def update_data(table, updates, filter_column, filter_value):
    """Updates data in a specified table based on a filter."""
    url = f'{st.secrets["supabase_url"]}/rest/v1/{table}?{filter_column}=eq.{filter_value}'
    response = requests.patch(url, headers=_get_service_headers(), json=updates)
    return response.status_code in [200, 204]

def delete_data(table, filter_column, filter_value):
    """Deletes data from a specified table based on a filter."""
    url = f'{st.secrets["supabase_url"]}/rest/v1/{table}?{filter_column}=eq.{filter_value}'
    response = requests.delete(url, headers=_get_service_headers())
    return response.status_code in [200, 204]

# --- App-specific Database Functions ---

def check_user_profile_exists(auth_user_id):
    """Checks if a questionnaire profile exists for a given auth user ID."""
    data = get_data("questionaire", f"auth_user_id=eq.{auth_user_id}")
    return len(data) > 0, data[0] if len(data) > 0 else None

def get_user_profile_by_data_uuid(uuid):
    """Gets the user's full profile from the questionnaire table using the data UUID."""
    data = get_data("questionaire", f"uuid=eq.{uuid}")
    return data[0] if data else {}

def load_user_workouts(user_data_uuid):
    """Loads all current workout sets for a user."""
    return get_data("workouts", f"uuid=eq.{user_data_uuid}")

def load_workout_history(user_data_uuid):
    """Loads the archived workout history for a user."""
    return get_data("workout_history", f"uuid=eq.{user_data_uuid}")