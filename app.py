import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import random
import time
import re
import unicodedata

# --- HILFSFUNKTIONEN FÜR DIE TEXTPRÜFUNG ---
def normalize_string(s):
    """Entfernt alle Akzente und Sonderzeichen (z.B. ñ -> n, á -> a)."""
    # NFKD teilt Zeichen und Akzente auf, ASCII filtert die Akzente weg
    return unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8')

def get_acceptable_answers(correct_answer):
    """
    Erzeugt eine Liste aller akzeptierten Antworten.
    Aus '(yo) hablo' wird z.B.: ['(yo) hablo', 'yo hablo', 'hablo']
    """
    ans = str(correct_answer).strip().lower()
    acceptable = [ans]
    
    # Wenn Klammern in der Lösung stehen, bauen wir Alternativen
    if '(' in ans and ')' in ans:
        # Variante 1: Alles in Klammern komplett entfernen -> "hablo"
        without_brackets = re.sub(r'\(.*?\)', '', ans).strip()
        # Mehrfache Leerzeichen entfernen, falls welche übrig bleiben
        without_brackets = re.sub(r'\s+', ' ', without_brackets)
        acceptable.append(without_brackets)
        
        # Variante 2: Nur die Klammer-Symbole entfernen, Inhalt behalten -> "yo hablo"
        without_bracket_symbols = ans.replace('(', '').replace(')', '').strip()
        without_bracket_symbols = re.sub(r'\s+', ' ', without_bracket_symbols)
        acceptable.append(without_bracket_symbols)
        
    return acceptable

# --- KONFIGURATION & VERBINDUNG ---
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials_dict = dict(st.secrets["gcp_service_account"])
    credentials_dict["private_key"] = credentials_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return gspread.authorize(creds)

def load_data():
    client = get_gspread_client()
    # Hier ist deine direkte URL
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1tvzRVjyVlsRj_hkyJcRzwSVdQqInFDiTyPOfuxtSNvQ/edit?gid=1963155081#gid=1963155081").sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data), sheet

# --- APP SETUP ---
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
        # 2. Antwort bereinigen und Listen für die Prüfung erstellen
        user_clean = user_input.strip().lower()
        acceptable_answers = get_acceptable_answers(antwort_korrekt)
        
        # Normalisierte Versionen (ohne Akzente) für die Toleranz-Prüfung erstellen
        user_norm = normalize_string(user_clean)
        acceptable_norm = [normalize_string(a) for a in acceptable_answers]
        
        col_weight = "Gewicht_ES_DE" if st.session_state.reverse else "Gewicht_DE_ES"
        idx = st.session_state.df[st.session_state.df.index == vok.name].index[0]
        
        # 3. Die intelligente Prüfung
        if user_clean in acceptable_answers:
            # Fall A: Perfekte Antwort (mit Akzenten / richtiger Klammernutzung)
            st.success("Richtig! 🎉")
            st.session_state.df.at[idx, col_weight] += 0.2
            
        elif user_norm in acceptable_norm:
            # Fall B: Richtig, aber Akzente fehlen oder sind falsch gesetzt
            st.success("Fast perfekt! 🎉")
            st.info(f"**Hinweis:** Achte auf die Akzente! Richtig geschrieben: **{antwort_korrekt}**")
            # Wir werten es trotzdem als richtig
            st.session_state.df.at[idx, col_weight] += 0.2
            
        else:
            # Fall C: Wirklich falsch
            st.error(f"Leider falsch. Richtig wäre: **{antwort_korrekt}**")
            new_val = st.session_state.df.at[idx, col_weight] - 0.5
            st.session_state.df.at[idx, col_weight] = max(0.1, new_val)

        # 4. Fortschrittszähler für Google Sheets
        st.session_state.counter += 1
        if st.session_state.counter >= 5:
            st.session_state.sheet.update([st.session_state.df.columns.values.tolist()] + st.session_state.df.values.tolist())
            st.session_state.counter = 0
            st.toast("Fortschritt in Google Sheets gespeichert! 💾")

        # 5. Nächste Vokabel laden und Pause machen
        st.session_state.current_vok = get_next_vokabel()
        time.sleep(1.5) # Etwas längere Pause, damit man die Hinweise in Ruhe lesen kann
        st.rerun()
