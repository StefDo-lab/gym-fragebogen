# supabase_utils.py
# This file handles all communication with the Supabase database.

import streamlit as st
from supabase import create_client, Client
from postgrest import APIResponse
import pandas as pd

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

# ... (alle bisherigen Funktionen wie check_user_profile_exists, load_user_workouts etc. bleiben unverändert) ...

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

def load_workout_history(user_uuid: str) -> list:
    """Loads all workout history for a user from the 'workouts_history' table."""
    try:
        response = supabase_auth_client.table("workouts_history") \
            .select("*") \
            .eq("uuid", user_uuid) \
            .order("time", desc=True) \
            .execute()
        return response.data if response.data else []
    except Exception as e:
        st.error(f"Fehler beim Laden der Trainingshistorie: {e}")
        return []

def update_workout_set(set_id: int, updates: dict) -> bool:
    """Updates a single completed set in the database."""
    try:
        supabase_auth_client.table("workouts").update(updates).eq("id", set_id).execute()
        return True
    except Exception as e:
        st.error(f"Fehler beim Aktualisieren des Satzes: {e}")
        return False

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

def archive_workout_and_analyze(user_uuid: str, workout_name: str):
    """
    Archives all completed sets of a specific workout, resets them in the active plan,
    and analyzes for new personal records (PRs).
    """
    try:
        completed_sets_response = supabase_auth_client.table("workouts") \
            .select("*") \
            .eq("uuid", user_uuid) \
            .eq("workout", workout_name) \
            .eq("completed", True) \
            .execute()

        if not completed_sets_response.data:
            st.warning("Keine abgeschlossenen Sätze zum Archivieren in diesem Workout gefunden.")
            return False, "Keine abgeschlossenen Sätze gefunden."

        sets_to_archive = completed_sets_response.data
        set_ids_to_reset = [s['id'] for s in sets_to_archive]
        
        pr_summary = []
        df_archived = pd.DataFrame(sets_to_archive)
        
        for exercise in df_archived['exercise'].unique():
            best_set = df_archived[df_archived['exercise'] == exercise].sort_values('weight', ascending=False).iloc[0]
            current_weight = best_set['weight']
            current_reps = best_set['reps']

            history_response = supabase_auth_client.table("workouts_history") \
                .select("weight, reps") \
                .eq("uuid", user_uuid) \
                .eq("exercise", exercise) \
                .order("weight", desc=True) \
                .limit(1) \
                .execute()

            if not history_response.data:
                pr_summary.append(f"Erster Eintrag für {exercise}: {current_weight}kg für {current_reps} Wdh.")
            else:
                previous_best_weight = history_response.data[0]['weight']
                if current_weight > previous_best_weight:
                    pr_summary.append(f"Neuer Rekord bei {exercise}: {current_weight}kg für {current_reps} Wdh. (vorher {previous_best_weight}kg)!")

        analysis_string = " ".join(pr_summary) if pr_summary else "Starke Leistung, alle Sätze abgeschlossen!"

        sets_for_history = [s.copy() for s in sets_to_archive]
        for s in sets_for_history:
            if 'id' in s:
                del s['id']
        
        supabase_auth_client.table("workouts_history").insert(sets_for_history).execute()

        update_payload = {"completed": False, "messagetocoach": "", "rirdone": 0}
        
        supabase_auth_client.table("workouts") \
            .update(update_payload) \
            .in_("id", set_ids_to_reset) \
            .execute()

        return True, analysis_string

    except Exception as e:
        st.error(f"Fehler beim Archivieren des Workouts: {e}")
        return False, f"Fehler: {e}"

# --- NEUE FUNKTION FÜR DIE ÜBUNGSDATENBANK ---
def load_filtered_exercises(user_profile: dict) -> list:
    """
    Loads exercises from the database, filtered by the user's profile.
    This is the scalable server-side filtering approach.
    """
    try:
        query = supabase_auth_client.table("exercises").select("*")

        # 1. Filter by Difficulty based on Experience
        experience = user_profile.get("experience_level", "Anfänger (0-1 Jahre)")
        if "Anfänger" in experience:
            # Anfänger bekommen Anfänger- und Fortgeschrittenen-Übungen
            query = query.in_("difficulty", ["Anfänger", "Fortgeschritten"])
        elif "Fortgeschritten" in experience:
            # Fortgeschrittene bekommen alle Schwierigkeitsgrade
            query = query.in_("difficulty", ["Anfänger", "Fortgeschritten", "Experte"])
        elif "Erfahren" in experience:
            # Erfahrene bekommen Fortgeschrittenen- und Experten-Übungen
            query = query.in_("difficulty", ["Fortgeschritten", "Experte"])

        # 2. Filter by available Equipment
        location = user_profile.get("training_location", "Voll ausgestattetes Fitnessstudio")
        if location == "Nur mit Körpergewicht":
            query = query.eq("equipment", "Körpergewicht")
        elif location == "Home-Gym (Basisausstattung)":
            # Hier nehmen wir an, dass ein Home-Gym keine großen Maschinen hat
            query = query.not_.ilike("equipment", "%Maschine%")

        # 3. Filter out disliked exercises
        disliked_raw = user_profile.get("context_and_preferences", {}).get("disliked_exercises", "")
        if disliked_raw:
            disliked_list = [ex.strip() for ex in disliked_raw.split(',') if ex.strip()]
            if disliked_list:
                for ex in disliked_list:
                    # 'ilike' für eine case-insensitive Suche
                    query = query.not_.ilike("name", f"%{ex}%")

        response = query.execute()
        return response.data if response.data else []

    except Exception as e:
        st.error(f"Fehler beim Laden der gefilterten Übungen: {e}")
        return []
