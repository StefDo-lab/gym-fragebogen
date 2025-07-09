import streamlit as st
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

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
    geburtsdatum = st.date_input("Geburtsdatum *")
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
    kfa_out = "" if kfa is None else kfa
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

    # 1. OP
    op = st.radio(
        "1. OP in den letzten 12–18 Monaten?", ["Nein", "Ja"], key="op"
    )
    with st.expander("Bitte beschreibe die OP (Art, Zeitpunkt, Folgen):",
                      expanded=(op == "Ja")):
        op_details = st.text_area("OP-Details", key="op_details")

    # 2. Ausstrahlende Schmerzen
    schmerzen = st.radio(
        "2. Ausstrahlende Schmerzen?", ["Nein", "Ja"], key="schmerzen"
    )
    with st.expander("Wo und wie äußern sich die Schmerzen?",
                      expanded=(schmerzen == "Ja")):
        schmerzen_details = st.text_area("Schmerz-Details", key="schmerzen_details")

    # 3. Bandscheibenvorfall
    bandscheibe = st.radio(
        "3. Bandscheibenvorfall in den letzten 6–12 Monaten?", ["Nein", "Ja"], key="bandscheibe"
    )
    with st.expander("Bitte beschreibe den Bandscheibenvorfall:",
                      expanded=(bandscheibe == "Ja")):
        bandscheibe_details = st.text_area("Bandscheiben-Details", key="bandscheibe_details")

    # 4. Osteoporose
    osteoporose = st.radio("4. Osteoporose?", ["Nein", "Ja"], key="osteoporose")
    with st.expander("Bitte beschreibe die Osteoporose:",
                      expanded=(osteoporose == "Ja")):
        osteoporose_details = st.text_area("Osteoporose-Details", key="osteoporose_details")

    # 5. Bluthochdruck
    bluthochdruck = st.radio("5. Bluthochdruck?", ["Nein", "Ja"], key="bluthochdruck")
    with st.expander("Bitte beschreibe den Bluthochdruck:",
                      expanded=(bluthochdruck == "Ja")):
        bluthochdruck_details = st.text_area("Blutdruck-Details", key="bluthochdruck_details")

    # 6. Innere Brüche
    brueche = st.radio("6. Innere Brüche?", ["Nein", "Ja"], key="brueche")
    with st.expander("Bitte beschreibe die Brüche:", expanded=(brueche == "Ja")):
        brueche_details = st.text_area("Brüche-Details", key="brueche_details")

    # 7. Herzprobleme
    herz = st.radio("7. Herzprobleme?", ["Nein", "Ja"], key="herz")
    with st.expander("Bitte beschreibe die Herzprobleme:",
                      expanded=(herz == "Ja")):
        herz_details = st.text_area("Herz-Details", key="herz_details")

    # 8. Schlaganfall, Epilepsie o.Ä.
    schlaganfall = st.radio(
        "8. Schlaganfall, Epilepsie, o. Ä.?", ["Nein", "Ja"], key="schlaganfall"
    )
    with st.expander("Bitte beschreibe die Erkrankung:",
                      expanded=(schlaganfall == "Ja")):
        schlaganfall_details = st.text_area("Erkrankungs-Details", key="schlaganfall_details")

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
        sheet.append_row(new_row)
        st.success("Danke für das Ausfüllen des Fragebogens!")
