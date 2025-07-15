import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.title("🔗 Supabase Test")

# ---- Setup ----
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---- Test: Alle Einträge laden ----
st.subheader("📋 Alle Daten laden")
try:
    response = supabase.table("Aktuell").select("*").execute()
    df = pd.DataFrame(response.data)
    st.write(df)
except Exception as e:
    st.error(f"Fehler beim Laden der Daten: {e}")

# ---- Test: Dummy-Datensatz hinzufügen ----
st.subheader("➕ Dummy-Datensatz hinzufügen")
if st.button("Neuen Dummy-Datensatz speichern"):
    try:
        insert_data = {
            "UserID": "TestUser123",
            "Datum": "2025-07-15",
            "Name": "Test-Eintrag",
            "Workout Name": "Test-Workout",
            "Übung": "Test-Übung",
            "Satz-Nr.": 1,
            "Gewicht": 50,
            "Wdh": 10,
            "Einheit": "kg",
            "Typ": "Test",
            "Erledigt": False
        }
        supabase.table("Aktuell").insert(insert_data).execute()
        st.success("Dummy-Datensatz wurde gespeichert!")
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")