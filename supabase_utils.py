# supabase_utils.py
# This file handles all communication with the Supabase database.

import streamlit as st
from supabase import create_client, Client
from postgrest import APIResponse

# --- Supabase Client Initialization ---
@st.cache_resource
def init_supabase_client() -> Client:
    """Initializes and returns the Supabase client."""
    url = st.secrets.get("supabase_url")
    anon_key = st.secrets.get("supabase_key")

    if not url or not anon_key:
        st.error("Supabase URL oder Anon Key sind nicht in den Secrets konfiguriert.")
        st.stop()
        
    return create_client(url, anon_key)

supabase_auth_client = init_supabase_client()

# --- App-specific Database Functions ---

def check_user_profile_exists(auth_user_id: str):
    """
    Checks if a questionnaire profile exists for a given auth user ID.
    Returns a tuple: (exists: bool, profile_data: dict | None)
    """
    try:
        response = supabase_auth_client.table("questionaire") \
            .select("*") \
            .eq("auth_user_id", auth_user_id) \
            .limit(1) \
            .execute()
        
        if response.data:
            return True, response.data[0]
        else:
            return False, None
    except Exception as e:
        st.error(f"Fehler bei der Profilprüfung: {e}")
        return False, None

def insert_questionnaire_data(data: dict) -> APIResponse:
    """Inserts the questionnaire data for a new user."""
    try:
        return supabase_auth_client.table("questionaire").insert(data).execute()
    except Exception as e:
        st.error(f"Fehler beim Speichern des Fragebogens: {e}")
        return None

def load_user_workouts(user_profile_uuid: str) -> list:
    """Loads all current workout sets for a user, using the profile UUID."""
    try:
        response = supabase_auth_client.table("workouts") \
            .select("*") \
            .eq("uuid", user_profile_uuid) \
            .order("id", desc=False) \
            .execute()
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Fehler beim Laden der Workouts: {e}")
        return []

def replace_user_workouts(user_profile_uuid: str, new_workouts: list) -> bool:
    """Atomically replaces all workouts for a user."""
    try:
        supabase_auth_client.table("workouts").delete().eq("uuid", user_profile_uuid).execute()
        if new_workouts:
            response = supabase_auth_client.table("workouts").insert(new_workouts).execute()
            if not response.data: return False
        return True
    except Exception as e:
        st.error(f"Fehler beim Ersetzen der Workouts: {e}")
        return False

def update_workout_set(set_id: int, updates: dict) -> bool:
    """Updates a single completed set in the database."""
    try:
        supabase_auth_client.table("workouts").update(updates).eq("id", set_id).execute()
        return True
    except Exception as e:
        st.error(f"Fehler beim Aktualisieren des Satzes: {e}")
        return False

# --- NEW FUNCTIONS FOR EDITING WORKOUTS ---

def delete_set(set_id: int) -> bool:
    """Deletes a single set by its ID."""
    try:
        supabase_auth_client.table("workouts").delete().eq("id", set_id).execute()
        return True
    except Exception as e:
        st.error(f"Fehler beim Löschen des Satzes: {e}")
        return False

def add_set(new_set_data: dict) -> bool:
    """Inserts a single new set."""
    try:
        response = supabase_auth_client.table("workouts").insert(new_set_data).execute()
        return bool(response.data)
    except Exception as e:
        st.error(f"Fehler beim Hinzufügen des Satzes: {e}")
        return False

def delete_exercise(exercise_ids: list) -> bool:
    """Deletes all sets for an exercise given a list of their IDs."""
    try:
        supabase_auth_client.table("workouts").delete().in_("id", exercise_ids).execute()
        return True
    except Exception as e:
        st.error(f"Fehler beim Löschen der Übung: {e}")
        return False

def add_exercise(new_exercise_sets: list) -> bool:
    """Inserts all sets for a new exercise."""
    try:
        response = supabase_auth_client.table("workouts").insert(new_exercise_sets).execute()
        return bool(response.data)
    except Exception as e:
        st.error(f"Fehler beim Hinzufügen der Übung: {e}")
        return False

def delete_workout(workout_ids: list) -> bool:
    """Deletes all sets for a workout given a list of their IDs."""
    try:
        supabase_auth_client.table("workouts").delete().in_("id", workout_ids).execute()
        return True
    except Exception as e:
        st.error(f"Fehler beim Löschen des Workouts: {e}")
        return False
