import streamlit as st

st.write("Verfügbare Secrets:")
st.write(list(st.secrets.keys()))

import datetime
import requests
import pandas as pd
import re
from openai import OpenAI
import io
import json
from supabase import create_client, Client

st.write("Imports funktionieren!")
# ---- Configuration ----
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_service_role_key"]
TABLE_WORKOUT = "workouts"
TABLE_ARCHIVE = "workout_history"
TABLE_QUESTIONNAIRE = "questionaire"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Supabase Client für Auth
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.write("Configuration geladen!")

