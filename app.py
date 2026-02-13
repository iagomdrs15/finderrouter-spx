import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit.components.v1 as components
import os

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Alocador SPX Pro", layout="wide", page_icon="🚀")

# --- COORDENADAS DO HUB ---
HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135

# --- INICIALIZAÇÃO E PERSISTÊNCIA LOCAL ---
ARQUIVO_LOG = "log_fleet_hub.csv"

if 'fleet_logs' not in st.session_state:
    if os.path.exists(ARQUIVO_LOG):
        st.session_state['fleet_logs'] = pd.read_csv(ARQUIVO_LOG)
    else:
        st.session_state['fleet_logs'] = pd.DataFrame(columns=['Driver ID', 'Nome', 'Placa', 'Entrada', 'Saída', 'Tempo no HUB', 'Data'])

hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- FUNÇÕES AUXILIARES ---
def salvar_localmente():
    st.session_state.fleet_logs.to_csv(ARQUIVO_LOG, index=False)

def style_sla(row):
    """Aplica cores baseadas no rigoroso critério de 10/12.5/15 min"""
    color = 'white'
    text_color = 'black'
    try:
        tempo = row['Tempo no HUB']
        if pd.notna(tempo) and tempo != "":
            # Converte formato HH:MM:SS ou MM:SS para segundos totais
            partes = list(map(int, tempo.split(':')))
            if len(partes) == 3: # HH:MM:SS
                total_segundos = partes[0] * 3600 + partes[1] * 60 + partes[2]
            else: # MM:SS
                total_segundos = partes[0] * 60 + partes[1]
            
            minutos_decimais = total_segundos / 60
            
            if minutos_decimais >= 15:
                color = '#ff4b4b' # Vermelho (Alerta)
                text_color = 'white'
            elif minutos_decimais >= 11: # Início da zona de atenção (incluindo o ponto de 12:30)
                color = '#f9d71c' # Amarelo (Atenção)
            else:
                color = '#28a745' # Verde (OK)
                text_color = 'white'
    except: pass
    return [f'background-color: {color}; color: {text_color}' if name == 'Tempo no HUB' else '' for name in row.index]

def tratar_pontos_coordenada(valor, tipo='lat'):
    try:
        if pd.isna(valor) or str(valor).strip() == "": return np.nan
        s = str(valor).replace(".", "").replace(",", "").strip()
        sinal = "-" if s.startswith("-") else ""
        apenas_numeros = s.replace("-", "")
        corrigido = sinal + (apenas_numeros[:1] if tipo == 'lat' else apenas_numeros[:2]) + "." + (apenas_numeros[1:] if tipo == 'lat' else apenas_numeros[2:])
        return float(corrigido)
    except: return np.nan

def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2): return 9999
        r = 6371 
        phi1, phi2 = np.radians(lat1), np.radians(lat2)
        dphi, dlambda = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
        a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

@st.cache_data(ttl=3600, show_spinner=False)
def carregar_dados_google(url, aba):
    try:
        file_id = url.split("/d/")[1].split("/")[0]
        url_csv = f"https://docs.google.com/spreadsheets/d/{file_id}/gviz/tq?tqx=out:csv&sheet={aba.replace(' ', '%20')}"
        df = pd.read_csv(url_csv)
        df.columns = df.columns.str.strip()
        return df
    except: return pd.DataFrame()

# --- INTERFACE ---
with st.sidebar:
    st.header("⚙️ Painel de Controle")
    if st.button("🔄 Sincronizar Agora", width='stretch'):
        st.cache_data.clear()
        st.rerun()

tab_alocador, tab_fleet = st.tabs(["🎯 Alocador de Pacotes", "🚚 Gestão de Fleet"])
url_planilha = st.text_input("🔗 Link da Planilha Google Sheets:", key="url_main")

if url_planilha:
    df_spx = carregar_dados_google(url_planilha, "Base SPX")
    df_cluster = carregar_dados_google(url_planilha, "Base Cluster")
    df_fleet_base = carregar_dados_google(url_planilha, "Base Fleet")

    # --- ABA 1: ALOCADOR ---
    with tab_alocador:
        col_s, col_o = st.columns([1, 1])
        with col_s: id_busca = st.text_input("🔎 Bipar Order ID / Cluster:", key="aloc_in").strip()
        with col_o: obs_label = st.text_input("📝 Obs Etiqueta:", placeholder="Opcional...")

        if id_busca:
            pacote = df_spx[df_spx['Order ID'].astype(str) == id_busca] if not df_spx.empty else pd.DataFrame()
            mask_cluster = df_cluster.astype(str).apply(lambda x: x.str.contains(id_busca, case=False)).any(axis=1) if not df_cluster.empty else pd.Series()
            item_cluster = df_cluster[mask_cluster]

            lat_p, lon_p = (tratar_pontos_coordenada(pacote['Latitude'].iloc[0], 'lat'), tratar_pontos_coordenada(pacote['Longitude'].iloc[0], 'lon')) if not pacote.empty else (np.nan, np.nan)
            if (pd.isna(lat_p)) and not item_cluster.empty:
                lat_p, lon_p = tratar_pontos_coordenada(item_cluster['Latitude'].iloc[0], 'lat'), tratar_pontos_coordenada(item_cluster['Longitude'].iloc[0], 'lon')
            
            ref_lat, ref_lon = (lat_p if not pd.isna(lat_p) else HUB_LAT), (lon_p if not pd.isna(lon_p) else HUB_LON)
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(ref_lat, ref_lon, tratar_pontos_coordenada(x['Latitude'], 'lat'), tratar_pontos_coordenada(x['Longitude'], 'lon')), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').drop_duplicates('Corridor Cage').head(3)

            c1, c2 = st.columns([1, 1.2])
            with c1:
                st.success(f"📍 Referência: {'Pacote' if not pacote.empty else 'HUB'}")
                for i, row in sugestoes.iterrows():
                    with st.expander(f"📍 {row['Corridor Cage']} ({row['dist_km']:.2f}km)"):
                        b1, b2 = st.columns(2)
                        with b1: st.link_button("🔗 Alocar", f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={str(row['Planned AT']).strip()}", width='stretch')
                        with b2:
                            if st.button("🖨️ Imprimir", key=f"prt_{i}", width='stretch'):
                                p = str(row['Corridor Cage']).split('-')
                                d = {'c': p[0], 'g': p[1] if len(p)>1 else "0", 'id': id_busca, 'b': row['Cluster'], 'o': obs_label, 'dt': datetime.now().strftime("%d/%m/%Y %H:%M")}
                                html = f"""<style>@media print {{ @page {{ size: 70mm 50mm; margin: 0; }} body {{ margin: 0; }} }} .box {{ width: 68mm; height: 48mm; border: 3px solid #000; font-family: Arial; }} .header {{ background: #000; color: #fff; text-align: center; padding: 2px; font-weight: bold; font-size: 9pt; }} .split {{ display: flex; border-bottom: 2px solid #000; height: 21mm; }} .side {{ flex: 1; text-align: center; border-right: 2px solid #000; display: flex; flex-direction: column; justify-content: center; }} .big {{ font-size: 42pt; font-weight: bold; line-height: 0.9; }} .bairro {{ background: #eee; text-align: center; padding: 4px; font-weight: bold; text-transform: uppercase; border-bottom: 1.5pt dashed black; font-size: 10pt; }}</style><div class="box"><div class="header">SPX - PORTO VELHO HUB</div><div class="split"><div class="side"><div>CORREDOR</div><div class="big">{d['c']}</div></div><div class="side" style="border:none;"><div>GAIOLA</div><div class="big">{d['g']}</div></div></div><div class="bairro">{d['b']}</div><div style="text-align:center; padding:1px; font-size: 8pt;"><b>{d['o']}</b><br>ID: {d['id']} | {d['dt']}</div></div><script>window.onload = function() {{ window.print(); }};</script>"""
                                components.html(html, height=250)
            with c2:
                st.map(pd.DataFrame({'lat': [ref_lat], 'lon': [ref_lon]}), zoom=13)

    # --- ABA 2: GESTÃO DE FLEET ---
    with tab_fleet:
        st.header(f"⏱️ Controle de Carregamento - {hoje_str}")
        col_f1, col_f2 = st.columns([1, 2])
        
        with col_f1:
            def registrar_fleet():
                d_id = st.session_state.f_scan.strip()
                if d_id and not df_fleet_base.empty:
                    match = df_fleet_base[df_fleet_base['Driver ID'].astype(str) == d_id]
                    if not match.empty:
                        nome, placa = match['Driver Name'].values[0], str(match['License Plate'].values[0])
                        agora = datetime.now()
                        logs = st.session_state.fleet_logs
                        aberto = logs[(logs['Driver ID'] == d_id) & (logs['Saída'].isna())]
                        
                        if not aberto.empty:
                            idx = aberto.index[-1]
                            saida_s = agora.strftime("%H:%M:%S")
                            logs.at[idx, 'Saída'] = saida_s
                            entrada_dt = datetime.strptime(logs.at[idx, 'Entrada'], "%H:%M:%S")
                            delta = agora - datetime.combine(datetime.today(), entrada_dt.time())
                            # Salva a diferença no formato H:M:S
                            logs.at[idx, 'Tempo no HUB'] = str(delta).split('.')[0]
                            st.toast(f"Saída: {nome}", icon="🏁")
                        else:
                            new_row = {'Driver ID': d_id, 'Nome': nome, 'Placa': placa, 'Entrada': agora.strftime("%H:%M:%S"), 'Saída': np.nan, 'Tempo no HUB': "", 'Data': hoje_str}
                            st.session_state.fleet_logs = pd.concat([logs, pd.DataFrame([new_row])], ignore_index=True)
                            st.toast(f"Entrada: {nome}", icon="📥")
                        
                        salvar_localmente()
                st.session_state.f_scan = ""

            st.text_input("🆔 Bipar Driver ID:", key="f_scan", on_change=registrar_fleet)

            if not st.session_state.fleet_logs.empty:
                last = st.session_state.fleet_logs.iloc[-1]
                p_html = f"""<div style="background:#FFF;border:3px solid #000;border-radius:6px;width:200px;height:70px;margin:10px auto;display:flex;flex-direction:column;align-items:center;justify-content:space-between;font-family:sans-serif;border-top:12px solid #003399;"><div style="color:white;font-size:7px;font-weight:bold;margin-top:-11px;">BRASIL</div><div style="font-size:28px;font-weight:900;letter-spacing:1px;color:#000;padding-bottom:5px;">{str(last['Placa']).upper()}</div></div>"""
                components.html(p_html, height=90)

        with col_f2:
            st.subheader("📋 Tabela de SLA - Fleet")
            # Aplica o estilo na tabela
            st.dataframe(st.session_state.fleet_logs.style.apply(style_sla, axis=1), width='stretch')
            
            if not st.session_state.fleet_logs.empty:
                st.download_button("📥 Extrair Log Completo (CSV)", st.session_state.fleet_logs.to_csv(index=False).encode('utf-8'), f"Backup_Fleet_{hoje_str.replace('/','-')}.csv", width='stretch')