import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro", layout="wide", page_icon="🚀")

# Conexão direta via Secrets
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- 2. FUNÇÕES ESSENCIAIS ---
def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if any(pd.isna([lat1, lon1, lat2, lon2])): return 9999
        r = 6371 
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
        a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

def style_sla(row):
    color = 'white'
    try:
        tempo = row['tempo_hub']
        if pd.notna(tempo) and ":" in str(tempo):
            partes = list(map(int, str(tempo).split(':')))
            minutos = (partes[0] * 60 + partes[1]) if len(partes) >= 2 else 0
            if minutos >= 15: color = '#ff4b4b'
            elif minutos >= 11: color = '#f9d71c'
            else: color = '#28a745'
    except: pass
    return [f'background-color: {color}' if name == 'tempo_hub' else '' for name in row.index]

# --- 3. CARREGAMENTO DE DADOS (SEM COMPLEXIDADE) ---
@st.cache_data(ttl=60) # Cache curto de 1 minuto para facilitar testes
def carregar_tudo():
    # Buscando dados das tabelas
    spx = conn.table("base_spx").select("*").execute()
    cluster = conn.table("base_cluster").select("*").execute()
    fleet = conn.table("base_fleet").select("*").execute()
    return pd.DataFrame(spx.data), pd.DataFrame(cluster.data), pd.DataFrame(fleet.data)

df_spx, df_cluster, df_fleet_base = carregar_tudo()

# --- 4. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador de Pacotes", "🚚 Gestão de Fleet"])

with tab1:
    id_busca = st.text_input("🔎 Digite o Order ID:").strip()
    if id_busca:
        # Busca o pacote na base SPX
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca] if not df_spx.empty else pd.DataFrame()
        
        if not pacote.empty:
            ref_lat, ref_lon = pacote['latitude'].iloc[0], pacote['longitude'].iloc[0]
            st.success(f"✅ Pacote encontrado! Destino: {ref_lat}, {ref_lon}")
            
            # Calcula sugestões na base_cluster
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(ref_lat, ref_lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').head(3)
            
            cols = st.columns(3)
            for idx, row in enumerate(sugestoes.itertuples()):
                cols[idx].metric(f"📍 {row.corridor_cage}", f"{row.dist_km:.2f} km")
        else:
            st.warning("⚠️ Pacote não encontrado na base_spx.")

with tab2:
    st.subheader("Bip de Entrada/Saída")
    d_id = st.text_input("🆔 Scan Driver ID:").strip()
    
    if d_id and not df_fleet_base.empty:
        # Localiza o motorista na base_fleet
        motorista = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
        
        if not motorista.empty:
            nome = motorista['driver_name'].values[0]
            placa = motorista['license_plate'].values[0]
            
            # Verifica se já está no HUB (sem hora de saída)
            aberto = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
            
            if aberto.data: # Registrar Saída
                row_id = aberto.data[0]['id']
                entrada_dt = datetime.fromisoformat(aberto.data[0]['entrada'].replace('Z', '+00:00'))
                delta = datetime.now().astimezone() - entrada_dt
                tempo = str(delta).split('.')[0]
                conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": tempo}).eq("id", row_id).execute()
                st.toast(f"🚩 Saída: {nome}")
            else: # Registrar Entrada
                conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                st.toast(f"📥 Entrada: {nome}")
        else:
            st.error("❌ Motorista não cadastrado na base_fleet.")

    # Exibe os logs do dia
    st.divider()
    logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
    if logs.data:
        st.dataframe(pd.DataFrame(logs.data)[['nome', 'placa', 'entrada', 'tempo_hub']].style.apply(style_sla, axis=1), use_container_width=True)
