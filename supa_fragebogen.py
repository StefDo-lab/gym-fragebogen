import streamlit as st
import requests
import datetime
import uuid
from supabase import create_client, Client

# ---- Supabase Setup ----
url = st.secrets["supabase_url"]
key = st.secrets["supabase_key"]
supabase: Client = create_client(url, key)

SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_service_role_key"]
SUPABASE_TABLE = "questionaire"

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

def send_to_make_webhook(payload):
    WEBHOOK_URL = "https://hook.eu2.make.com/4kt4g15jfxcn7t78coox6accz79ui47f"
    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=30)
        return response
    except Exception as e:
        return e

if "user" not in st.session_state:
    st.session_state.user = None
if "mode" not in st.session_state:
    st.session_state.mode = "login"

def login():
    st.subheader("Login")
    email = st.text_input("E-Mail", key="login_email")
    password = st.text_input("Passwort", type="password", key="login_pw")
    if st.button("Jetzt einloggen", key="login_button"):
        try:
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            if res.user:
                st.session_state.user = res.user
                st.success(f"Willkommen, {res.user.email}")
        except Exception as e:
            st.error(f"Login fehlgeschlagen: {e}")
    if st.button("Passwort vergessen?"):
        if email:
            try:
                supabase.auth.reset_password_email(email)
                st.success("Passwort-Reset-E-Mail wurde versendet.")
            except Exception as e:
                st.error(f"Fehler beim Senden der Reset-E-Mail: {e}")
        else:
            st.warning("Bitte gib deine E-Mail-Adresse ein.")

def register():
    st.subheader("Registrieren")
    email = st.text_input("E-Mail", key="reg_email")
    password = st.text_input("Passwort", type="password", key="reg_pw")
    if st.button("Jetzt registrieren", key="reg_button"):
        try:
            res = supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            if res.user:
                st.success("Registrierung erfolgreich! Bitte E-Mail bestätigen und anschließend einloggen.")
                st.session_state.mode = "login"
        except Exception as e:
            st.error(f"Registrierung fehlgeschlagen: {e}")

def logout():
    st.session_state.user = None
    st.success("Du wurdest ausgeloggt.")

def auth_flow():
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Zum Login", key="switch_login"):
            st.session_state.mode = "login"
    with col2:
        if st.button("Zur Registrierung", key="switch_register"):
            st.session_state.mode = "register"

    if st.session_state.mode == "login":
        login()
    else:
        register()

def fragebogen():
    st.success(f"Eingeloggt als {st.session_state.user.email}")
    if st.button("Logout", key="logout_button"):
        logout()
        return

    st.markdown("**Deine Benutzer-ID:** `{}`".format(st.session_state.user.id))

    with st.form("fitness_fragebogen"):
        st.header("Persönliche Daten")
        forename = st.text_input("Vorname *")
        surename = st.text_input("Nachname *")
        birthday = st.date_input("Geburtsdatum *", value=datetime.date(2000, 1, 1))
        email = st.text_input("E-Mail-Adresse *")
        phone = st.text_input("Telefonnummer *")
        gender = st.selectbox("Geschlecht", ["Bitte wählen...", "männlich", "weiblich", "divers"])
        date = st.date_input("Datum der Erfassung", value=datetime.date.today())
        studio = st.selectbox("Studio *", ["Bitte wählen...", "Studio 1", "Studio 2"])

        st.subheader("Körperdaten (optional)")
        height = st.number_input("Größe (cm)", min_value=0, step=1)
        weight = st.number_input("Gewicht (kg)", min_value=0.0, step=0.1)
        bodyfat = st.number_input("Körperfettanteil (%)", min_value=0.0, step=0.1)

        st.subheader("Gesundheit und Ziele")
        experience = st.radio("Hast du bereits Erfahrung mit Krafttraining?", ["Ja", "Nein"])
        additional = st.text_area("Was möchtest du ergänzen?")
        goals = st.multiselect("Deine Trainingsziele", [
            "Rücken stärken", "Gelenke stabilisieren", "Osteoporoseprävention",
            "Stoffwechsel verbessern", "Haltung verbessern", "Gewebe straffen",
            "Gewicht reduzieren", "Muskelmasse aufbauen", "Vorbereitung auf Sport",
            "Verletzungsprophylaxe", "Leistungssteigerung", "Dysbalancen ausgleichen"
        ])
        goalDetail = st.text_area("Weitere Anmerkungen zu deinen Trainingszielen")

        st.subheader("Medizinische Fragen")
        surgery = st.radio("1. OP in den letzten 12–18 Monaten?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe die OP (Art, Zeitpunkt, Folgen):", expanded=(surgery == "Ja")):
            surgeryDetails = st.text_area("OP-Details", value="")

        radiatingPain = st.radio("2. Ausstrahlende Schmerzen?", ["Nein", "Ja"])
        with st.expander("Wo und wie äußern sich die Schmerzen?", expanded=(radiatingPain == "Ja")):
            painDetails = st.text_area("Schmerz-Details", value="")

        discHerniated = st.radio("3. Bandscheibenvorfall in den letzten 6–12 Monaten?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe den Bandscheibenvorfall:", expanded=(discHerniated == "Ja")):
            discDetails = st.text_area("Bandscheiben-Details", value="")

        osteoporose = st.radio("4. Osteoporose?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe die Osteoporose:", expanded=(osteoporose == "Ja")):
            osteporoseDetails = st.text_area("Osteoporose-Details", value="")

        hypertension = st.radio("5. Bluthochdruck?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe den Bluthochdruck:", expanded=(hypertension == "Ja")):
            hypertensionDetails = st.text_area("Bluthochdruck-Details", value="")

        hernia = st.radio("6. Innere Brüche?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe die Brüche:", expanded=(hernia == "Ja")):
            herniaDetails = st.text_area("Bruch-Details", value="")

        cardic = st.radio("7. Herzprobleme?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe die Herzprobleme:", expanded=(cardic == "Ja")):
            cardicDetails = st.text_area("Herz-Details", value="")

        stroke = st.radio("8. Schlaganfall, Epilepsie o. Ä.?", ["Nein", "Ja"])
        with st.expander("Bitte beschreibe die Erkrankung:", expanded=(stroke == "Ja")):
            strokeDetails = st.text_area("Schlaganfall-Details", value="")

        healthOther = st.text_area("Sonstige Gesundheitsprobleme oder Medikamente?")
        goalsDetailExtra = st.text_area("Was sind deine konkreten Ziele beim Training?")
        healthCondition = st.text_area("Wie ist dein aktueller Gesundheitszustand?")
        restrictions = st.text_area("Gibt es Einschränkungen bei Bewegung oder Sport?")
        pains = st.text_area("Wo spürst du Schmerzen oder Beschwerden?")
        stresslevel = st.slider("Stresslevel (1 = kein Stress, 10 = extrem gestresst):", 1, 10, 1)
        sleepDuration = st.number_input("Durchschnittliche Schlafdauer (in Stunden):", min_value=0.0, step=0.5)
        diet = st.text_area("Wie ernährst du dich aktuell?")
        motivation = st.slider("Motivationslevel (1 = null, 10 = hoch):", 1, 10, 5)
        trainFrequency = st.number_input("Wie oft möchtest du pro Woche trainieren?", min_value=0, step=1)

        dsgvo = st.checkbox("Ich stimme der DSGVO-Einwilligung zu")
        abgeschickt = st.form_submit_button("Fragebogen absenden")

    if abgeschickt:
        if not (forename and surename and email and phone and studio != "Bitte wählen..." and dsgvo):
            st.error("Bitte fülle alle Pflichtfelder aus und stimme der Datenschutzerklärung zu.")
        else:
            data_payload = {
                "user_id": st.session_state.user.id,
                "uuid": str(uuid.uuid4()),
                "forename": forename,
                "surename": surename,
                "birthday": str(birthday),
                "email": email,
                "phone": phone,
                "gender": gender,
                "date": str(date),
                "studio": studio,
                "height": height,
                "weight": weight,
                "bodyfat": bodyfat,
                "experience": experience,
                "additional": additional,
                "goals": "; ".join(goals),
                "goalDetail": goalDetail,
                "surgery": surgery,
                "surgeryDetails": surgeryDetails,
                "radiatingPain": radiatingPain,
                "painDetails": painDetails,
                "discHerniated": discHerniated,
                "discDetails": discDetails,
                "osteoporose": osteoporose,
                "osteporoseDetails": osteporoseDetails,
                "hypertension": hypertension,
                "hypertensionDetails": hypertensionDetails,
                "hernia": hernia,
                "herniaDetails": herniaDetails,
                "cardic": cardic,
                "cardicDetails": cardicDetails,
                "stroke": stroke,
                "strokeDetails": strokeDetails,
                "healthOther": healthOther,
                "goalsDetail": goalsDetailExtra,
                "healthCondition": healthCondition,
                "restrictions": restrictions,
                "pains": pains,
                "stresslevel": stresslevel,
                "sleepDuration": sleepDuration,
                "diet": diet,
                "motivation": motivation,
                "trainFrequency": trainFrequency,
                "dsgvo": True if dsgvo else False,
                "time": str(datetime.datetime.now())
            }
            response_db = insert_into_supabase(data_payload)
            if response_db.status_code in [200, 201]:
                st.success("✅ Daten erfolgreich in Supabase gespeichert!")
                response_hook = send_to_make_webhook(data_payload)
                if isinstance(response_hook, requests.Response) and response_hook.status_code in [200, 202]:
                    st.success("✅ Webhook erfolgreich an Make.com gesendet!")
                else:
                    st.warning("⚠️ Webhook konnte nicht gesendet werden.")
            else:
                st.error(f"❌ Fehler beim Supabase-Speichern: {response_db.status_code} - {response_db.text}")

st.title("Fitness- und Gesundheitsfragebogen (mit Login & Registrierung)")

if st.session_state.user:
    fragebogen()
else:
    auth_flow()
