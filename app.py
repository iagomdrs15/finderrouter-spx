import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit.components.v1 as components
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")

# O Streamlit busca automaticamente supabase_url e supabase_key nos Secrets
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- 2. FUNÇÕES AUXILIARES OTIMIZADAS ---
def style_sla(row):
    color = 'white'
    text_color = 'black'
    try:
        tempo = row['tempo_hub']
        if pd.notna(tempo) and tempo != "":
            partes = list(map(int, tempo.split(':')))
            total_segundos = (partes[0] * 3600 + partes[1] * 60 + partes[2]) if len(partes) == 3 else (partes[0] * 60 + partes[1])
            minutos = total_segundos / 60
            if minutos >= 15: color, text_color = '#ff4b4b', 'white'
            elif minutos >= 11: color, text_color = '#f9d71c', 'black'
            else: color, text_color = '#28a745', 'white'
    except: pass
    return [f'background-color: {color}; color: {text_color}' if name == 'tempo_hub' else '' for name in row.index]

def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if any(pd.isna([lat1, lon1, lat2, lon2])): return 9999
        r = 6371 
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
        a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

# --- 3. CARREGAMENTO DE DADOS (SQL) ---
@st.cache_data(ttl=600)
def carregar_bases_sql():
    # Carrega as tabelas que o senhor subiu para o Supabase
    spx = conn.table("Base SPX").select("*").execute()
    cluster = conn.table("Base Cluster").select("*").execute()
    fleet = conn.table("Base Fleet").select("*").execute()
    return pd.DataFrame(spx.data), pd.DataFrame(cluster.data), pd.DataFrame(fleet.data)

# --- 4. INTERFACE PRINCIPAL ---
df_spx, df_cluster, df_fleet_base = carregar_bases_sql()

tab_aloc, tab_fleet = st.tabs(["🎯 Alocador de Pacotes", "🚚 Gestão de Fleet (SQL)"])

# --- ABA ALOCADOR ---
with tab_aloc:
    col_id, col_obs = st.columns(2)
    id_busca = col_id.text_input("🔎 Order ID / Cluster:").strip()
    obs = col_obs.text_input("📝 Obs Etiqueta:")

    if id_busca:
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca] if not df_spx.empty else pd.DataFrame()
        ref_lat = pacote['latitude'].iloc[0] if not pacote.empty else HUB_LAT
        ref_lon = pacote['longitude'].iloc[0] if not pacote.empty else HUB_LON

        df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(ref_lat, ref_lon, x['latitude'], x['longitude']), axis=1)
        sugestoes = df_cluster.sort_values('dist_km').drop_duplicates('corridor_cage').head(3)

        c1, c2 = st.columns([1, 1.2])
        with c1:
            for i, row in sugestoes.iterrows():
                with st.expander(f"📍 {row['corridor_cage']} ({row['dist_km']:.2f}km)"):
                    st.button("🖨️ Imprimir", key=f"btn_{i}")
        with c2:
            st.map(pd.DataFrame({'lat': [ref_lat], 'lon': [ref_lon]}), zoom=14)

# --- ABA FLEET (SQL) ---
with tab_fleet:
    @st.fragment
    def sessao_fleet():
        col_in, col_list = st.columns([1, 2])
        with col_in:
            d_id = st.text_input("🆔 Bipar Driver ID:", key="scan_sql").strip()
            if d_id:
                # Busca motorista no SQL
                match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
                if not match.empty:
                    nome, placa = match['driver_name'].values[0], str(match['license_plate'].values[0])
                    # Verifica registro aberto no banco
                    res = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
                    
                    if res.data: # Saída
                        row_id = res.data[0]['id']
                        entrada_dt = datetime.fromisoformat(res.data[0]['entrada'].replace('Z', '+00:00'))
                        delta = datetime.now().astimezone() - entrada_dt
                        tempo = str(delta).split('.')[0]
                        conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": tempo}).eq("id", row_id).execute()
                        st.toast(f"Saída: {nome}", icon="🏁")
                    else: # Entrada
                        conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                        st.toast(f"Entrada: {nome}", icon="📥")
        
        with col_list:
            logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
            if logs.data:
                st.dataframe(pd.DataFrame(logs.data)[['nome', 'placa', 'entrada', 'tempo_hub']].style.apply(style_sla, axis=1), use_container_width=True)

    sessao_fleet()
