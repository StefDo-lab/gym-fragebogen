import streamlit as st
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# ---- Google Sheets Setup ----
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "fragebogen"

def get_gsheet_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["gcp_service_account"]), scopes
    )
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)

sheet = get_gsheet_worksheet()

# ---- App Titel ----
st.title("Fitness- und Gesundheitsfragebogen")

# ---- Formular ----
with st.form("fitness_fragebogen"):
    # Persönliche Daten
    st.header("Persönliche Daten")
    vorname = st.text_input("Vorname *")
    nachname = st.text_input("Nachname *")
    geburtsdatum = st.date_input(
        "Geburtsdatum *",
        value=datetime.date(2000, 1, 1),
        min_value=datetime.date(1900, 1, 1),
        max_value=datetime.date.today(),
    )
    email = st.text_input("E-Mail-Adresse *")
    telefon = st.text_input("Telefonnummer *")
    geschlecht = st.selectbox(
        "Geschlecht", ["Bitte wählen...", "männlich", "weiblich", "divers"]
    )
    erfassungsdatum = st.date_input(
        "Datum der Erfassung", value=datetime.date.today()
    )
    studio = st.selectbox(
        "Studio *", ["Bitte wählen...", "Studio 1", "Studio 2"]
    )

    # Körperdaten (optional)
    st.subheader("Körperdaten (optional)")
    groesse = st.number_input("Größe (cm)", min_value=0, step=1, format="%d")
    gewicht = st.number_input("Gewicht (kg)", min_value=0.0, step=0.1, format="%.1f")
    kfa = st.number_input(
        "Körperfettanteil (%)", min_value=0.0, step=0.1, format="%.1f"
    )
    kfa_out = "" if kfa == 0 else kfa
    st.caption(
        "Hinweis: Diese Angaben sind freiwillig und helfen uns bei der individuellen Trainingsplanung."
    )

    # Sonstiges
    st.subheader("Sonstiges")
    krafttraining = st.radio(
        "Hast du bereits Erfahrung mit Krafttraining?", ["Ja", "Nein"]
    )
    ergaenzung = st.text_area(
        "Was möchtest du ergänzen (Trainingsform, Wünsche, Unsicherheiten)?"
    )
    ziele = st.multiselect(
        "Deine Trainingsziele (Mehrfachauswahl möglich)",
        [
            "Rücken stärken", "Gelenke stabilisieren", "Osteoporoseprävention",
            "Stoffwechsel verbessern", "Haltung verbessern", "Gewebe straffen",
            "Gewicht reduzieren", "Muskelmasse aufbauen", "Vorbereitung auf Sport",
            "Verletzungsprophylaxe", "Leistungssteigerung",
            "Dysbalancen ausgleichen"
        ]
    )
    weitere_ziele = st.text_area(
        "Weitere Anmerkungen zu deinen Trainingszielen"
    )

    # Medizinische Fragen mit dynamischen Detail-Feldern
    st.subheader("Medizinische Fragen")

    # Detail-Variablen initialisieren
    op_details = ""
    schmerzen_details = ""
    bandscheibe_details = ""
    osteoporose_details = ""
    bluthochdruck_details = ""
    brueche_details = ""
    herz_details = ""
    schlaganfall_details = ""

    # 1. OP
    op = st.radio(
        "1. OP in den letzten 12–18 Monaten?", ["Nein", "Ja"], key="op"
    )
    with st.expander("Bitte beschreibe die OP (Art, Zeitpunkt, Folgen):",
                      expanded=(op == "Ja")):
        op_details = st.text_area("OP-Details", key="op_details", value="")

    # 2. Ausstrahlende Schmerzen
    schmerzen = st.radio(
        "2. Ausstrahlende Schmerzen?", ["Nein", "Ja"], key="schmerzen"
    )
    with st.expander("Wo und wie äußern sich die Schmerzen?",
                      expanded=(schmerzen == "Ja")):
        schmerzen_details = st.text_area("Schmerz-Details", key="schmerzen_details", value="")

    # 3. Bandscheibenvorfall
    bandscheibe = st.radio(
        "3. Bandscheibenvorfall in den letzten 6–12 Monaten?", ["Nein", "Ja"], key="bandscheibe"
    )
    with st.expander("Bitte beschreibe den Bandscheibenvorfall:",
                      expanded=(bandscheibe == "Ja")):
        bandscheibe_details = st.text_area("Bandscheiben-Details", key="bandscheibe_details", value="")

    # 4. Osteoporose
    osteoporose = st.radio("4. Osteoporose?", ["Nein", "Ja"], key="osteoporose")
    with st.expander("Bitte beschreibe die Osteoporose:",
                      expanded=(osteoporose == "Ja")):
        osteoporose_details = st.text_area("Osteoporose-Details", key="osteoporose_details", value="")

    # 5. Bluthochdruck
    bluthochdruck = st.radio("5. Bluthochdruck?", ["Nein", "Ja"], key="bluthochdruck")
    with st.expander("Bitte beschreibe den Bluthochdruck:",
                      expanded=(bluthochdruck == "Ja")):
        bluthochdruck_details = st.text_area("Blutdruck-Details", key="bluthochdruck_details", value="")

    # 6. Innere Brüche
    brueche = st.radio("6. Innere Brüche?", ["Nein", "Ja"], key="brueche")
    with st.expander("Bitte beschreibe die Brüche:", expanded=(brueche == "Ja")):
        brueche_details = st.text_area("Brüche-Details", key="brueche_details", value="")

    # 7. Herzprobleme
    herz = st.radio("7. Herzprobleme?", ["Nein", "Ja"], key="herz")
    with st.expander("Bitte beschreibe die Herzprobleme:",
                      expanded=(herz == "Ja")):
        herz_details = st.text_area("Herz-Details", key="herz_details", value="")

    # 8. Schlaganfall, Epilepsie o.Ä.
    schlaganfall = st.radio(
        "8. Schlaganfall, Epilepsie, o. Ä.?", ["Nein", "Ja"], key="schlaganfall"
    )
    with st.expander("Bitte beschreibe die Erkrankung:",
                      expanded=(schlaganfall == "Ja")):
        schlaganfall_details = st.text_area("Erkrankungs-Details", key="schlaganfall_details", value="")

    # Weitere Gesundheitsfragen
    gesundheit = st.text_area("Sonstige Gesundheitsprobleme oder Medikamente?")
    konkrete_ziele = st.text_area("Was sind deine konkreten Ziele beim Training?")
    gesundheitszustand = st.text_area("Wie ist dein aktueller Gesundheitszustand?")
    einschraenkungen = st.text_area("Gibt es Einschränkungen bei Bewegung oder Sport?")
    schmerzen_beschwerden = st.text_area("Wo spürst du Schmerzen oder Beschwerden?")
    stresslevel = st.slider("Stresslevel (1 = kein Stress, 10 = extrem gestresst):", 1, 10, 1)
    schlaf = st.number_input(
        "Durchschnittliche Schlafdauer (in Stunden):", min_value=0.0, step=0.5, format="%.1f"
    )
    ernaehrung = st.text_area("Wie ernährst du dich aktuell?")
    motivation = st.slider("Motivationslevel (1 = null, 10 = hoch):", 1, 10, 5)
    training_haeufigkeit = st.number_input(
        "Wie oft möchtest du pro Woche trainieren?", min_value=0, step=1, format="%d"
    )

    # DSGVO-Einwilligung
    st.subheader("DSGVO-Einwilligung")
    st.caption(
        "Mit dem Absenden dieses Fragebogens willigen Sie ein, dass Ihre angegebenen Daten ..."
    )
    einwilligung = st.checkbox(
        "Ich stimme zu, dass meine Angaben zum Zweck der Trainingsplanung gespeichert und verarbeitet werden. *"
    )

    abgeschickt = st.form_submit_button("Fragebogen absenden")

# ---- Nach dem Absenden ----
if abgeschickt:
    # Pflichtfelder prüfen
    if not (vorname and nachname and geburtsdatum and email and telefon \
            and studio != "Bitte wählen..." and einwilligung):
        st.error("Bitte fülle alle Pflichtfelder aus und stimme der Datenschutzerklärung zu.")
    else:
        # ===== NEU: ID und temporäres Passwort generieren =====
        user_id = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{vorname[:3].upper()}"
        temp_password = f"{nachname[:3].lower()}{geburtsdatum.day:02d}"
        # Zeile für Google Sheets vorbereiten
        new_row = [
            vorname, nachname, str(geburtsdatum), email, telefon, geschlecht,
            str(erfassungsdatum), studio, groesse, gewicht, kfa_out, krafttraining,
            ergaenzung, "; ".join(ziele), weitere_ziele, op, op_details,
            schmerzen, schmerzen_details, bandscheibe, bandscheibe_details,
            osteoporose, osteoporose_details, bluthochdruck, bluthochdruck_details,
            brueche, brueche_details, herz, herz_details, schlaganfall, schlaganfall_details,
            gesundheit, konkrete_ziele, gesundheitszustand, einschraenkungen,
            schmerzen_beschwerden, stresslevel, schlaf, ernaehrung, motivation,
            training_haeufigkeit, "Ja" if einwilligung else "Nein"
        ]
        
        # Google Sheets speichern
        try:
            sheet.append_row(new_row)
            st.success("✅ Daten in Google Sheets gespeichert!")
        except Exception as e:
            st.error(f"❌ Fehler beim Speichern in Google Sheets: {e}")
        
        # Webhook an Make.com senden
        WEBHOOK_URL = "https://hook.eu2.make.com/i8vbdd2xgdif28ym98mhk174wsecx10t"
        
        payload = {
            "vorname": vorname,
            "user_id": user_id,  # <-- NEU
            "temp_password": temp_password,
            "nachname": nachname,
            "geburtsdatum": str(geburtsdatum),
            "email": email,
            "telefon": telefon,
            "geschlecht": geschlecht if geschlecht != "Bitte wählen..." else "",
            "erfassungsdatum": str(erfassungsdatum),
            "studio": studio,
            "groesse": groesse if groesse > 0 else "",
            "gewicht": gewicht if gewicht > 0 else "",
            "kfa": kfa if kfa > 0 else "",
            "krafttraining": krafttraining,
            "ergaenzung": ergaenzung,
            "ziele": "; ".join(ziele),
            "weitere_ziele": weitere_ziele,
            "op": op,
            "op_details": op_details if op == "Ja" else "",
            "schmerzen": schmerzen,
            "schmerzen_details": schmerzen_details if schmerzen == "Ja" else "",
            "bandscheibe": bandscheibe,
            "bandscheibe_details": bandscheibe_details if bandscheibe == "Ja" else "",
            "osteoporose": osteoporose,
            "osteoporose_details": osteoporose_details if osteoporose == "Ja" else "",
            "bluthochdruck": bluthochdruck,
            "bluthochdruck_details": bluthochdruck_details if bluthochdruck == "Ja" else "",
            "brueche": brueche,
            "brueche_details": brueche_details if brueche == "Ja" else "",
            "herz": herz,
            "herz_details": herz_details if herz == "Ja" else "",
            "schlaganfall": schlaganfall,
            "schlaganfall_details": schlaganfall_details if schlaganfall == "Ja" else "",
            "gesundheit": gesundheit,
            "konkrete_ziele": konkrete_ziele,
            "gesundheitszustand": gesundheitszustand,
            "einschraenkungen": einschraenkungen,
            "schmerzen_beschwerden": schmerzen_beschwerden,
            "stresslevel": stresslevel,
            "schlaf": schlaf,
            "ernaehrung": ernaehrung,
            "motivation": motivation,
            "training_haeufigkeit": training_haeufigkeit,
            "einwilligung": "Ja" if einwilligung else "Nein"
        }
        
        try:
            response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
            if response.status_code in [200, 202, 204]:
                st.success("✅ Daten erfolgreich an Make.com übertragen!")
                st.balloons()
            else:
                st.warning(f"⚠️ Webhook Status: {response.status_code} - {response.text}")
        except Exception as e:
            st.error(f"❌ Webhook Fehler: {e}")
        
        st.success("🎉 Vielen Dank für das Ausfüllen des Fragebogens!")

        # Zugangsdaten in einer schönen Box anzeigen
        st.info(f"""
        📱 **Deine Zugangsdaten für die Trainingsplan-App:**
        
        **Benutzer-ID:** `{user_id}`  
        **Temporäres Passwort:** `{temp_password}`
        
        ⚠️ **Wichtig:** Speichere diese Daten oder mache ein Screenshot!  
        Du erhältst sie auch per E-Mail an {email}.
        """)
        
        # Optional: Daten als Text zum Kopieren
        with st.expander("📋 Zum Kopieren"):
            st.code(f"""
Benutzer-ID: {user_id}
Passwort: {temp_password}
            """)
