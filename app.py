import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import random
import time

# --- KONFIGURATION & VERBINDUNG ---
def get_gspread_client():
    """
    Lädt die Anmeldedaten aus den Streamlit Secrets, repariert Zeilenumbrüche
    und verbindet sich mit den korrekten Berechtigungen mit Google Sheets.
    """
    # 1. Scopes für Google Sheets UND Google Drive definieren
    # (Drive wird von gspread zwingend benötigt, um Tabellen per Namen zu suchen)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # 2. Secrets in ein anpassbares Dictionary laden
    credentials_dict = dict(st.secrets["gcp_service_account"])
    
    # 3. Bulletproof-Trick: \n im private_key in echte Zeilenumbrüche umwandeln
    credentials_dict["private_key"] = credentials_dict["private_key"].replace("\\n", "\n")
    
    # 4. Credentials-Objekt mit den reparierten Daten und neuen Scopes erstellen
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    
    # 5. Client autorisieren und zurückgeben
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    # Ersetze "Dein_Sheet_Name" durch den echten Namen deiner Datei
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1tvzRVjyVlsRj_hkyJcRzwSVdQqInFDiTyPOfuxtSNvQ/edit?gid=1963155081#gid=1963155081").sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data), sheet

# --- APP SETUP ---
# Muss immer der erste Streamlit-Befehl sein!
st.set_page_config(page_title="Vokabel-Pro", layout="centered")

if "df" not in st.session_state:
    df, sheet = load_data()
    st.session_state.df = df
    st.session_state.sheet = sheet
    st.session_state.counter = 0
    st.session_state.reverse = False # False: DE->ES, True: ES->DE

# --- LOGIK ---
def get_next_vokabel():
    df = st.session_state.df
    col_weight = "Gewicht_ES_DE" if st.session_state.reverse else "Gewicht_DE_ES"
    
    # Gewichtete Zufallsauswahl: 1/Gewichtung sorgt dafür, dass kleine Werte öfter kommen
    weights = 1.0 / df[col_weight].astype(float)
    return df.sample(n=1, weights=weights).iloc[0]

if "current_vok" not in st.session_state:
    st.session_state.current_vok = get_next_vokabel()

# --- UI OBEN ---
col_header, col_toggle = st.columns([3, 1])
with col_toggle:
    if st.button("🔄 Drehen"):
        st.session_state.reverse = not st.session_state.reverse
        st.session_state.current_vok = get_next_vokabel()
        st.rerun()

# --- HAUPTTEIL ---
vok = st.session_state.current_vok
frage = vok["Spanisch"] if st.session_state.reverse else vok["Deutsch"]
antwort_korrekt = vok["Deutsch"] if st.session_state.reverse else vok["Spanisch"]

st.markdown(f"### Wie sagt man auf {'Deutsch' if st.session_state.reverse else 'Spanisch'}?")
st.info(f"## {frage}")

with st.form(key="answer_form", clear_on_submit=True):
    user_input = st.text_input("Deine Antwort:")
    submit = st.form_submit_button("Prüfen")

if submit:
    # 1. Sicherheitscheck: Wurde überhaupt etwas eingegeben?
    if user_input.strip() == "":
        st.warning("Bitte gib zuerst ein Wort ein! ✍️")
    else:
        # 2. Antwort bereinigen und prüfen
        clean_user = user_input.strip().lower()
        clean_correct = str(antwort_korrekt).strip().lower()
        
        col_weight = "Gewicht_ES_DE" if st.session_state.reverse else "Gewicht_DE_ES"
        idx = st.session_state.df[st.session_state.df.index == vok.name].index[0]
        
        if clean_user == clean_correct:
            st.success("Richtig! 🎉")
            # Gewichtung erhöhen (erscheint seltener)
            st.session_state.df.at[idx, col_weight] += 0.2
        else:
            st.error(f"Leider falsch. Richtig wäre: {antwort_korrekt}")
            # Gewichtung senken (erscheint häufiger), minimal 0.1
            new_val = st.session_state.df.at[idx, col_weight] - 0.5
            st.session_state.df.at[idx, col_weight] = max(0.1, new_val)

        # 3. Fortschrittszähler für Google Sheets
        st.session_state.counter += 1
        if st.session_state.counter >= 5:
            st.session_state.sheet.update([st.session_state.df.columns.values.tolist()] + st.session_state.df.values.tolist())
            st.session_state.counter = 0
            st.toast("Fortschritt in Google Sheets gespeichert! 💾")

        # 4. Nächste Vokabel laden
        st.session_state.current_vok = get_next_vokabel()
        
        # 5. Magie: Kurz warten, damit man die Lösung lesen kann, dann flüssig neu laden
        time.sleep(2.5)
        st.rerun()
