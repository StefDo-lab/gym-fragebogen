import streamlit as st
import requests
import pandas as pd
import uuid

# ---- Supabase REST API Setup ----
SUPABASE_URL = st.secrets["supabase_url"]  # z.B. https://xyzcompany.supabase.co
SUPABASE_KEY = st.secrets["supabase_key"]
TABLE = "Aktuell"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ---- Alle Daten abrufen ----
def get_data():
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?select=*"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Fehler beim Abrufen der Daten: {response.status_code} - {response.text}")
        return []

# ---- Einen neuen Datensatz speichern ----
def insert_data(data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    response = requests.post(url, headers=headers, json=[data])
    if response.status_code in (200, 201):
        return True
    else:
        st.error(f"Fehler beim Speichern: {response.status_code} - {response.text}")
        return False

# ---- Streamlit UI ----
st.title("📋 Supabase REST API Test")

if st.button("Alle Daten laden"):
    data = get_data()
    if data:
        st.dataframe(pd.DataFrame(data))

if st.button("Neuen Dummy-Datensatz speichern"):
    dummy = {
    #    "ID": str(uuid.uuid4()),
        "UserID": "TestUser123",
        "Datum": "2025-07-15",
        "Name": "Test via REST",
        "Workout Name": "REST Test Workout",
        "Übung": "REST-Test",
        "Satz-Nr.": 1,
        "Gewicht": 60,
        "Wdh": 12,
        "Einheit": "kg",
        "Typ": "REST",
        "Erledigt": False
    }
    if insert_data(dummy):
        st.success("Dummy-Datensatz gespeichert ✅")
