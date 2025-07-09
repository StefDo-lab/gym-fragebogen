import streamlit as st
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheets Setup
SHEET_NAME = "Workout Tabelle"
WORKSHEET_NAME = "fragebogen"

def get_gsheet_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scopes)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)

sheet = get_gsheet_worksheet()

st.title("Fitness- und Gesundheitsfragebogen")

with st.form("fitness_fragebogen"):
    st.header("Persönliche Daten")
    vorname = st.text_input("Vorname *")
    nachname = st.text_input("Nachname *")
    geburtsdatum = st.date_input("Geburtsdatum *")
    email = st.text_input("E-Mail-Adresse *")
    telefon = st.text_input("Telefonnummer *")
    geschlecht = st.selectbox("Geschlecht", ["Bitte wählen...", "männlich", "weiblich", "divers"])
    erfassungsdatum = st.date_input("Datum der Erfassung", value=datetime.date.today())
    studio = st.selectbox("Studio *", ["Bitte wählen...", "Studio 1", "Studio 2"])

    st.subheader("Körperdaten (optional)")
    groesse = st.number_input("Größe (cm)", min_value=0, step=1, format="%d", placeholder="optional")
    gewicht = st.number_input("Gewicht (kg)", min_value=0.0, step=0.1, format="%.1f", placeholder="optional")
    kfa = st.number_input("Körperfettanteil (%)", min_value=0.0, step=0.1, format="%.1f", value=None, placeholder="optional")
    if kfa is None:
        kfa_out = ""
    else:
        kfa_out = kfa
    st.caption("Hinweis: Diese Angaben sind freiwillig und helfen uns bei der individuellen Trainingsplanung. Falls du diese Werte nicht kennst, können wir sie gerne bei deinem ersten Termin gemeinsam ermitteln.")

    st.subheader("Sonstiges")
    krafttraining = st.radio("Hast du bereits Erfahrung mit Krafttraining?", ["Ja", "Nein"])
    ergaenzung = st.text_area("Was möchtest du ergänzen (Trainingsform, Wünsche, Unsicherheiten)?")
    ziele = st.multiselect("Deine Trainingsziele (Mehrfachauswahl möglich)", [
        "Rücken stärken", "Gelenke stabilisieren", "Osteoporoseprävention", "Stoffwechsel verbessern",
        "Haltung verbessern", "Gewebe straffen", "Gewicht reduzieren", "Muskelmasse aufbauen",
        "Vorbereitung auf Sport", "Verletzungsprophylaxe", "Leistungssteigerung", "Dysbalancen ausgleichen"
    ])

    # Dynamische Zusatzfelder für Ziele
    ziel_details = {}
    for ziel in ziele:
        if ziel in [
            "Haltung verbessern", "Rücken stärken", "Gelenke stabilisieren", "Dysbalancen ausgleichen"
        ]:
            ziel_details[ziel] = st.text_area(f"Bitte beschreibe dein Ziel '{ziel}' genauer:")

    st.subheader("Medizinische Fragen")

    op = st.radio("1. OP in den letzten 12–18 Monaten?", ["Nein", "Ja"])
    op_details = ""
    if op == "Ja":
        op_details = st.text_area("Bitte beschreibe die OP (Art, Zeitpunkt, Folgen):")

    schmerzen = st.radio("2. Ausstrahlende Schmerzen?", ["Nein", "Ja"])
    schmerzen_details = ""
    if schmerzen == "Ja":
        schmerzen_details = st.text_area("Wo und wie äußern sich die Schmerzen?")

    bandscheibe = st.radio("3. Bandscheibenvorfall in den letzten 6–12 Monaten?", ["Nein", "Ja"])
    bandscheibe_details = ""
    if bandscheibe == "Ja":
        bandscheibe_details = st.text_area("Bitte beschreibe den Bandscheibenvorfall:")

    osteoporose = st.radio("4. Osteoporose?", ["Nein", "Ja"])
    osteoporose_details = ""
    if osteoporose == "Ja":
        osteoporose_details = st.text_area("Bitte beschreibe die Osteoporose:")

    bluthochdruck = st.radio("5. Bluthochdruck?", ["Nein", "Ja"])
    bluthochdruck_details = ""
    if bluthochdruck == "Ja":
        bluthochdruck_details = st.text_area("Bitte beschreibe den Bluthochdruck:")

    brueche = st.radio("6. Innere Brüche?", ["Nein", "Ja"])
    brueche_details = ""
    if brueche == "Ja":
        brueche_details = st.text_area("Bitte beschreibe die Brüche:")

    herz = st.radio("7. Herzprobleme?", ["Nein", "Ja"])
    herz_details = ""
    if herz == "Ja":
        herz_details = st.text_area("Bitte beschreibe die Herzprobleme:")

    schlaganfall = st.radio("8. Schlaganfall, Epilepsie, o. Ä.?", ["Nein", "Ja"])
    schlaganfall_details = ""
    if schlaganfall == "Ja":
        schlaganfall_details = st.text_area("Bitte beschreibe die Erkrankung:")

    gesundheit = st.text_area("Sonstige Gesundheitsprobleme oder Medikamente?")

    st.subheader("Offene Fragen")
    konkrete_ziele = st.text_area("Was sind deine konkreten Ziele beim Training?")
    gesundheitszustand = st.text_area("Wie ist dein aktueller Gesundheitszustand?")
    einschraenkungen = st.text_area("Gibt es Einschränkungen bei Bewegung oder Sport?")
    schmerzen_beschwerden = st.text_area("Wo spürst du Schmerzen oder Beschwerden?")
    stresslevel = st.slider("Stresslevel (1 = kein Stress, 10 = extrem gestresst):", 1, 10, 1)
    schlaf = st.number_input("Durchschnittliche Schlafdauer (in Stunden):", min_value=0.0, step=0.5, format="%.1f", placeholder="optional")
    ernaehrung = st.text_area("Wie ernährst du dich aktuell?")
    motivation = st.slider("Motivationslevel (1 = null, 10 = hoch):", 1, 10, 5)
    training_haeufigkeit = st.number_input("Wie oft möchtest du pro Woche trainieren?", min_value=0, step=1, format="%d", placeholder="optional")

    st.subheader("DSGVO-Einwilligung")
    st.caption("Mit dem Absenden dieses Fragebogens willigen Sie ein, dass Ihre angegebenen Daten zum Zweck der Trainingsplanung und -betreuung gespeichert und verarbeitet werden. Ihre Daten werden ausschließlich für die Erstellung eines individuellen Trainingsplans und die medizinische Betreuung während des Trainings verwendet. Sie haben jederzeit das Recht auf Auskunft, Berichtigung, Löschung oder Einschränkung der Verarbeitung Ihrer personenbezogenen Daten sowie das Recht auf Datenübertragbarkeit und Widerspruch gegen die Verarbeitung. Diese Einwilligung können Sie jederzeit mit Wirkung für die Zukunft widerrufen.")
    einwilligung = st.checkbox("Ich stimme zu, dass meine Angaben zum Zweck der Trainingsplanung gespeichert und verarbeitet werden. Ich kann diese Einwilligung jederzeit widerrufen. *")

    abgeschickt = st.form_submit_button("Fragebogen absenden")

if abgeschickt:
    # Pflichtfelder prüfen
    if not (vorname and nachname and geburtsdatum and email and telefon and studio != "Bitte wählen..." and einwilligung):
        st.error("Bitte fülle alle Pflichtfelder aus und stimme der Datenschutzerklärung zu.")
    else:
        new_row = [
            vorname, nachname, str(geburtsdatum), email, telefon, geschlecht,
            str(erfassungsdatum), studio, groesse, gewicht, kfa_out, krafttraining,
            ergaenzung, "; ".join(ziele), str(ziel_details), op, op_details,
            schmerzen, schmerzen_details, bandscheibe, bandscheibe_details,
            osteoporose, osteoporose_details, bluthochdruck, bluthochdruck_details,
            brueche, brueche_details, herz, herz_details, schlaganfall, schlaganfall_details,
            gesundheit, konkrete_ziele, gesundheitszustand, einschraenkungen,
            schmerzen_beschwerden, stresslevel, schlaf, ernaehrung, motivation,
            training_haeufigkeit, "Ja" if einwilligung else "Nein"
        ]
        sheet.append_row(new_row)
        st.success("Danke für das Ausfüllen des Fragebogens!")
