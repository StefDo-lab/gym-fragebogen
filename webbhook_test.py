import streamlit as st
import requests
import datetime

st.title("Webhook Test")

WEBHOOK_URL = "https://hook.eu2.make.com/i8vbdd2xgdif28ym98mhk174wsecx10t"

# Einfacher Test-Button
if st.button("🚀 Webhook Test senden"):
    # Ganz einfache Test-Daten
    test_data = {
        "nachricht": "Hallo von Streamlit!",
        "zeit": str(datetime.datetime.now()),
        "test": True
    }
    
    try:
        # Sende Request
        response = requests.post(WEBHOOK_URL, json=test_data)
        
        # Zeige Ergebnis
        st.write(f"Status Code: {response.status_code}")
        st.write(f"Response: {response.text}")
        
        if response.status_code in [200, 202, 204]:
            st.success("✅ Webhook erfolgreich gesendet!")
            st.balloons()
        else:
            st.error("❌ Etwas ist schiefgelaufen")
            
    except Exception as e:
        st.error(f"Fehler: {str(e)}")

# Zeige die Webhook URL zur Sicherheit
st.info(f"Webhook URL: {WEBHOOK_URL}")
