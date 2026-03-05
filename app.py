import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
from io import BytesIO

# --- CONFIGURAZIONE E CONNESSIONE (Invariata) ---
cartella_corrente = os.path.dirname(os.path.abspath(__file__))
path_credenziali = next((os.path.join(cartella_corrente, f) for f in ['credenziali.json', 'credenziali'] if os.path.exists(os.path.join(cartella_corrente, f))), None)

@st.cache_resource
def get_connect():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(path_credenziali, scope)
    client = gspread.authorize(creds)
    return client.open("Gestionale_Rete_Vendita_Abbigliamento")

sh = get_connect()
ordini_sheet = sh.worksheet("Ordini")
brand_sheet = sh.worksheet("Brand")
agenti_sheet = sh.worksheet("Agenti")

def clean_pct(val):
    try: return float(str(val).replace('%', '').replace(',', '.')) / 100
    except: return 0.0

# --- SIDEBAR ---
st.sidebar.title("👔 Menu Gestionale")
menu = st.sidebar.radio("Navigazione", [
    "📊 Dashboard Finanziaria", 
    "📝 Nuovo Ordine", 
    "🚚 Gestione Consegne", 
    "📄 Distinta Provvigioni", # <-- Nuova Voce
    "🏷️ Anagrafica Brand"
])

# ... [Le altre sezioni Dashboard, Nuovo Ordine, Consegne rimangono come prima] ...

# --- SEZIONE: DISTINTA PROVVIGIONI (NEW) ---
if menu == "📄 Distinta Provvigioni":
    st.title("📄 Generazione Distinta Maturato")
    st.write("Seleziona l'agente e la stagione per generare il riepilogo dei compensi basato sul consegnato.")

    df_o = pd.DataFrame(ordini_sheet.get_all_records())
    df_b = pd.DataFrame(brand_sheet.get_all_records())
    df_a = pd.DataFrame(agenti_sheet.get_all_records())

    if not df_o.empty:
        col_a, col_s = st.columns(2)
        with col_a:
            agente_sel = st.selectbox("Seleziona Agente", df_a['Nome'].tolist())
        with col_s:
            stagione_sel = st.selectbox("Seleziona Stagione", df_o['Stagione'].unique().tolist())

        # Elaborazione Dati
        # 1. Filtriamo per Agente e Stagione
        df_f = df_o[(df_o['ID_Agente'] == agente_sel) & (df_o['Stagione'] == stagione_sel)].copy()
        
        # 2. Colleghiamo le percentuali dei Brand
        df_report = pd.merge(df_f, df_b, left_on='Brand', right_on='Nome_Brand')
        
        # 3. Calcolo finanziario specifico per l'AGENTE
        df_report['%_Agente'] = df_report['Quota_Agente_%'].apply(clean_pct)
        df_report['Maturato_Agente_€'] = df_report['Consegnato_€'] * df_report['%_Agente']
        
        # Tabella pulita per la visualizzazione
        distinta_view = df_report[['ID_Ordine', 'ID_Negozio', 'Brand', 'Ordinato_€', 'Consegnato_€', 'Quota_Agente_%', 'Maturato_Agente_€']]
        
        st.subheader(f"Riepilogo per {agente_sel} - {stagione_sel}")
        st.dataframe(distinta_view, use_container_width=True)
        
        tot_maturato = distinta_view['Maturato_Agente_€'].sum()
        st.metric("TOTALE DA PAGARE (Saldato su Consegnato)", f"{tot_maturato:,.2f} €")

        # --- EXPORT EXCEL ---
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            distinta_view.to_excel(writer, index=False, sheet_name='Distinta')
        
        st.download_button(
            label="📥 Scarica Distinta Excel",
            data=buffer.getvalue(),
            file_name=f"Distinta_{agente_sel.replace(' ', '_')}_{stagione_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Nessun ordine presente per generare distinte.")

# ... [Aggiungi qui le altre sezioni elif già esistenti] ...