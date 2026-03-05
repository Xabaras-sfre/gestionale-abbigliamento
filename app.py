import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime
from io import BytesIO

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestionale Rete Vendita", layout="wide", page_icon="👔")

# --- 2. CONNESSIONE INTELLIGENTE (LOCALE + CLOUD) ---
@st.cache_resource
def get_connect():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Prova a leggere dai Secrets di Streamlit (Online)
    if "gspread" in st.secrets:
        creds_dict = dict(st.secrets["gspread"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    # Altrimenti cerca il file locale (PC)
    else:
        cartella = os.path.dirname(os.path.abspath(__file__))
        path_file = os.path.join(cartella, 'credenziali.json')
        if os.path.exists(path_file):
            creds = ServiceAccountCredentials.from_json_keyfile_name(path_file, scope)
        else:
            st.error("❌ Credenziali non trovate! Inseriscile nei Secrets (Cloud) o nel file 'credenziali.json' (Locale).")
            return None
            
    client = gspread.authorize(creds)
    # Sostituisci con il nome esatto del tuo file Google Sheets
    return client.open("Gestionale_Rete_Vendita_Abbigliamento")

sh = get_connect()

if not sh:
    st.stop()

# --- 3. INIZIALIZZAZIONE FOGLI E LOG ---
def init_sheets():
    try:
        l_s = sh.worksheet("Log_Consegne")
    except:
        l_s = sh.add_worksheet(title="Log_Consegne", rows="1000", cols=3)
        l_s.append_row(["ID_Ordine", "Data_Consegna", "Valore_Consegnato"])
    
    return l_s, sh.worksheet("Ordini"), sh.worksheet("Brand"), sh.worksheet("Agenti")

log_sheet, ordini_sheet, brand_sheet, agenti_sheet = init_sheets()

# --- 4. UTILITY ---
def clean_pct(val):
    """Converte '15%', '15' o 0.15 in float (0.15)"""
    try:
        return float(str(val).replace('%', '').replace(',', '.')) / 100
    except:
        return 0.0

# --- 5. SIDEBAR ---
st.sidebar.title("👔 Controllo Rete")
menu = st.sidebar.radio("Vai a:", [
    "📊 Dashboard Finanziaria", 
    "📝 Inserimento Ordine", 
    "🚚 Gestione Consegne", 
    "📄 Distinta Provvigioni",
    "🏷️ Anagrafica Brand"
])

# --- 6. SEZIONE: DASHBOARD FINANZIARIA ---
if menu == "📊 Dashboard Finanziaria":
    st.title("📊 Analisi Vendite e Maturato")
    
    df_o = pd.DataFrame(ordini_sheet.get_all_records())
    df_b = pd.DataFrame(brand_sheet.get_all_records())
    
    if not df_o.empty and not df_b.empty:
        # Unione dati per calcolo provvigioni
        df_m = pd.merge(df_o, df_b, left_on='Brand', right_on='Nome_Brand')
        
        # Calcoli Finanziari
        df_m['%_Totale'] = df_m['Provvigione_Totale_%'].apply(clean_pct)
        df_m['Provv_Tot_Potenziale'] = df_m['Ordinato_€'] * df_m['%_Totale']
        df_m['Provv_Maturata'] = df_m['Consegnato_€'] * df_m['%_Totale']
        
        # KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("Fatturato Ordinato", f"{df_m['Ordinato_€'].sum():,.2f} €")
        c2.metric("Fatturato Consegnato", f"{df_m['Consegnato_€'].sum():,.2f} €")
        c3.metric("Provvigioni Maturate", f"{df_m['Provv_Maturata'].sum():,.2f} €")

        # Filtri
        st.divider()
        stati = df_m['Stato_Incasso'].unique().tolist()
        f_stato = st.multiselect("Filtra per stato ordine", stati, default=stati)
        
        st.dataframe(df_m[df_m['Stato_Incasso'].isin(f_stato)], use_container_width=True)
    else:
        st.info("Inizia inserendo i Brand e il tuo primo Ordine.")

# --- 7. SEZIONE: NUOVO ORDINE ---
elif menu == "📝 Inserimento Ordine":
    st.title("📝 Registra Nuovo Ordine")
    b_df = pd.DataFrame(brand_sheet.get_all_records())
    a_df = pd.DataFrame(agenti_sheet.get_all_records())

    with st.form("new_order", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            id_o = st.text_input("Codice Ordine")
            stagione = st.selectbox("Stagione", ["PE 2026", "AI 2026", "PE 2027"])
            agente = st.selectbox("Agente", a_df['Nome'].tolist())
        with col2:
            brand = st.selectbox("Brand", b_df['Nome_Brand'].tolist())
            negozio = st.text_input("Ragione Sociale Negozio")
            valore = st.number_input("Valore Lordo Ordinato (€)", min_value=0.0)
        
        if st.form_submit_button("Salva nel Database"):
            ordini_sheet.append_row([id_o, stagione, agente, negozio, brand, valore, 0, "In Attesa"])
            st.success("Ordine registrato correttamente su Google Sheets!")
            st.balloons()

# --- 8. SEZIONE: GESTIONE CONSEGNE ---
elif menu == "🚚 Gestione Consegne":
    st.title("🚚 Scarico Merce e Consegne Parziali")
    df_o = pd.DataFrame(ordini_sheet.get_all_records())
    pendenti = df_o[df_o['Stato_Incasso'] != "Consegnato"]
    
    if not pendenti.empty:
        scelta = st.selectbox("Scegli l'ordine da aggiornare", pendenti['ID_Ordine'].tolist())
        dati_sel = pendenti[pendenti['ID_Ordine'] == scelta].iloc[0]
        
        ordinato = float(dati_sel['Ordinato_€'])
        gia_cons = float(dati_sel['Consegnato_€'])
        rimanente = round(ordinato - gia_cons, 2)
        
        st.metric("Valore ancora da consegnare", f"{rimanente} €")

        with st.form("consegna_form"):
            val_scarico = st.number_input("Valore fatturato oggi", min_value=0.0, max_value=rimanente, step=1.0)
            data_scarico = st.date_input("Data della bolla/fattura", datetime.now())
            
            if st.form_submit_button("Conferma Scarico"):
                # 1. Log Storico
                log_sheet.append_row([scelta, str(data_scarico), val_scarico])
                # 2. Aggiornamento Testata
                nuovo_tot = gia_cons + val_scarico
                nuovo_stato = "Consegnato" if nuovo_tot >= ordinato else "Parziale"
                cella = ordini_sheet.find(scelta)
                ordini_sheet.update_cell(cella.row, 7, nuovo_tot)
                ordini_sheet.update_cell(cella.row, 8, nuovo_stato)
                st.success(f"Scarico effettuato. Stato: {nuovo_stato}")
                st.rerun()
                
        # Dettaglio storico consegne dell'ordine scelto
        df_log = pd.DataFrame(log_sheet.get_all_records())
        if not df_log.empty:
            storico = df_log[df_log['ID_Ordine'] == scelta]
            if not storico.empty:
                st.subheader("Storico spedizioni per questo ordine")
                st.table(storico)

# --- 9. SEZIONE: DISTINTA PROVVIGIONI ---
elif menu == "📄 Distinta Provvigioni":
    st.title("📄 Calcolo Distinta Agente")
    df_o = pd.DataFrame(ordini_sheet.get_all_records())
    df_b = pd.DataFrame(brand_sheet.get_all_records())
    df_a = pd.DataFrame(agenti_sheet.get_all_records())

    if not df_o.empty:
        agente_sel = st.selectbox("Seleziona Agente", df_a['Nome'].tolist())
        stagione_sel = st.selectbox("Seleziona Stagione", df_o['Stagione'].unique().tolist())
        
        df_f = df_o[(df_o['ID_Agente'] == agente_sel) & (df_o['Stagione'] == stagione_sel)].copy()
        df_rep = pd.merge(df_f, df_b, left_on='Brand', right_on='Nome_Brand')
        
        df_rep['%_Ag'] = df_rep['Quota_Agente_%'].apply(clean_pct)
        df_rep['Provvigione_Maturata_€'] = df_rep['Consegnato_€'] * df_rep['%_Ag']
        
        vista = df_rep[['ID_Ordine', 'ID_Negozio', 'Brand', 'Consegnato_€', 'Quota_Agente_%', 'Provvigione_Maturata_€']]
        st.dataframe(vista, use_container_width=True)
        st.metric("TOTALE MATURATO DA PAGARE", f"{vista['Provvigione_Maturata_€'].sum():,.2f} €")
        
        # Download Excel
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            vista.to_excel(writer, index=False, sheet_name='Distinta')
        st.download_button("📥 Scarica Distinta Excel", buf.getvalue(), f"Distinta_{agente_sel}_{stagione_sel}.xlsx")

# --- 10. SEZIONE: ANAGRAFICA BRAND ---
elif menu == "🏷️ Anagrafica Brand":
    st.title("🏷️ Gestione Marchi e Provvigioni")
    
    with st.expander("Aggiungi nuovo Brand"):
        with st.form("add_brand"):
            n = st.text_input("Nome Marchio")
            t = st.number_input("Provvigione Totale (%)", step=0.1)
            c = st.number_input("Quota Capoarea (%)", step=0.1)
            a = st.number_input("Quota Agente (%)", step=0.1)
            if st.form_submit_button("Salva"):
                brand_sheet.append_row([f"B{len(brand_sheet.get_all_records())+1}", n, f"{t}%", f"{c}%", f"{a}%"])
                st.success("Brand aggiunto!")
                st.rerun()
                
    st.dataframe(pd.DataFrame(brand_sheet.get_all_records()), use_container_width=True)
