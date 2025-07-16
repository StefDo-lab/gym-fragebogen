import streamlit as st
import requests
import datetime
import uuid

# ---- Supabase Setup ----
SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_service_role_key"]
SUPABASE_TABLE = "Fragebogen"

def insert_into_supabase(data):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        headers=headers,
        json=data
    )
    return response

# ---- Streamlit App ----
st.title("Fitness- und Gesundheitsfragebogen (Supabase)")

with st.form("fitness_fragebogen"):
    st.header("Persönliche Daten")
    vorname = st.text_input("Vorname *")
    nachname = st.text_input("Nachname *")
    geburtsdatum = st.date_input("Geburtsdatum *", value=datetime.date(2000, 1, 1))
    email = st.text_input("E-Mail-Adresse *")
    telefon = st.text_input("Telefonnummer *")
    geschlecht = st.selectbox("Geschlecht", ["Bitte wählen...", "männlich", "weiblich", "divers"])
    erfassungsdatum = st.date_input("Datum der Erfassung", value=datetime.date.today())
    studio = st.selectbox("Studio *", ["Bitte wählen...", "Studio 1", "Studio 2"])

    st.subheader("Körperdaten (optional)")
    groesse = st.number_input("Größe (cm)", min_value=0, step=1)
    gewicht = st.number_input("Gewicht (kg)", min_value=0.0, step=0.1)
    kfa = st.number_input("Körperfettanteil (%)", min_value=0.0, step=0.1)

    st.subheader("Gesundheit und Ziele")
    krafttraining = st.radio("Hast du bereits Erfahrung mit Krafttraining?", ["Ja", "Nein"])
    ergaenzung = st.text_area("Was möchtest du ergänzen?")
    ziele = st.multiselect("Deine Trainingsziele", [
        "Rücken stärken", "Gelenke stabilisieren", "Osteoporoseprävention",
        "Stoffwechsel verbessern", "Haltung verbessern", "Gewebe straffen",
        "Gewicht reduzieren", "Muskelmasse aufbauen", "Vorbereitung auf Sport",
        "Verletzungsprophylaxe", "Leistungssteigerung", "Dysbalancen ausgleichen"
    ])
    weitere_ziele = st.text_area("Weitere Anmerkungen zu deinen Trainingszielen")

    # Kurzversion der medizinischen Fragen (vereinfachtes Beispiel)
    op = st.radio("OP in den letzten 12–18 Monaten?", ["Nein", "Ja"])
    op_details = st.text_area("OP-Details", value="")

    gesundheit = st.text_area("Sonstige Gesundheitsprobleme oder Medikamente?")
    konkrete_ziele = st.text_area("Was sind deine konkreten Ziele beim Training?")
    gesundheitszustand = st.text_area("Wie ist dein aktueller Gesundheitszustand?")
    einschraenkungen = st.text_area("Gibt es Einschränkungen bei Bewegung oder Sport?")
    stresslevel = st.slider("Stresslevel (1 = kein Stress, 10 = extrem gestresst):", 1, 10, 1)
    schlaf = st.number_input("Durchschnittliche Schlafdauer (in Stunden):", min_value=0.0, step=0.5)
    ernaehrung = st.text_area("Wie ernährst du dich aktuell?")
    motivation = st.slider("Motivationslevel (1 = null, 10 = hoch):", 1, 10, 5)
    training_haeufigkeit = st.number_input("Wie oft möchtest du pro Woche trainieren?", min_value=0, step=1)

    einwilligung = st.checkbox("Ich stimme der DSGVO-Einwilligung zu")

    abgeschickt = st.form_submit_button("Fragebogen absenden")

if abgeschickt:
    if not (vorname and nachname and email and telefon and studio != "Bitte wählen..." and einwilligung):
        st.error("Bitte fülle alle Pflichtfelder aus und stimme der Datenschutzerklärung zu.")
    else:
        user_id = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{vorname[:3].upper()}"

        supabase_data = {
            "ID": str(uuid.uuid4()),
            "UserID": user_id,
            "Vorname": vorname,
            "Nachname": nachname,
            "Geburtsdatum": str(geburtsdatum),
            "E-Mail-Adresse": email,
            "Telefonnummer": telefon,
            "Geschlecht": geschlecht,
            "Datum der Erfassung": str(erfassungsdatum),
            "Studio": studio,
            "Größe (cm)": groesse,
            "Gewicht (kg)": gewicht,
            "Körperfettanteil (%)": kfa,
            "Krafttraining-Erfahrung": krafttraining,
            "Ergänzungen": ergaenzung,
            "Trainingsziele": "; ".join(ziele),
            "Ziel-Details": weitere_ziele,
            "OP letzte 12-18 Monate": op,
            "OP-Details": op_details,
            "Sonstige Gesundheitsprobleme": gesundheit,
            "Konkrete Ziele": konkrete_ziele,
            "Gesundheitszustand": gesundheitszustand,
            "Einschränkungen": einschraenkungen,
            "Stresslevel": stresslevel,
            "Schlafdauer (h)": schlaf,
            "Ernährung": ernaehrung,
            "Motivationslevel": motivation,
            "Trainingshäufigkeit (pro Woche)": training_haeufigkeit,
            "DSGVO-Einwilligung": "Ja" if einwilligung else "Nein"
        }

        response = insert_into_supabase(supabase_data)

        if response.status_code in [200, 201]:
            st.success("✅ Daten erfolgreich in Supabase gespeichert!")
            st.balloons()
        else:
            st.error(f"❌ Fehler beim Supabase-Speichern: {response.status_code} - {response.text}")

        st.info(f"📱 **Deine Benutzer-ID:** `{user_id}`\nBitte speichern oder Screenshot machen!")
