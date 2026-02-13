import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135

# --- 2. O DETERMINANTE (TRADUTOR DE COLUNAS) ---
def normalizar_colunas(df, mapa_sinonimos):
    """
    Traduz os nomes das colunas do banco/CSV para os nomes que o código usa.
    Exemplo: Se no banco estiver 'Pedido', ele vira 'order_id'.
    """
    for nome_correto, sinonimos in mapa_sinonimos.items():
        for s in sinonimos:
            # Busca ignorando maiúsculas/minúsculas e espaços
            col_encontrada = next((c for c in df.columns if c.lower().strip() == s.lower()), None)
            if col_encontrada:
                df = df.rename(columns={col_encontrada: nome_correto})
                break
    return df

# Definição dos sinônimos baseados no que costuma vir nos Sheets/CSVs
SINONIMOS = {
    'order_id': ['order_id', 'pedido', 'id', 'order', 'rastreio'],
    'latitude': ['latitude', 'lat', 'lat_y', 'y'],
    'longitude': ['longitude', 'long', 'lng', 'lon', 'x'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'corredor'],
    'driver_id': ['driver_id', 'id_motorista', 'id', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa', 'veiculo']
}

# --- 3. CARREGAMENTO COM NORMALIZAÇÃO ---
@st.cache_data(ttl=600)
def carregar_bases_sql():
    try:
        # Busca tudo das tabelas para podermos mapear
        spx_raw = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster_raw = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet_raw = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        # Aplica o determinante (tradução)
        df_spx = normalizar_colunas(spx_raw, SINONIMOS)
        df_cluster = normalizar_colunas(cluster_raw, SINONIMOS)
        df_fleet = normalizar_colunas(fleet_raw, SINONIMOS)
        
        return df_spx, df_cluster, df_fleet
    except Exception as e:
        st.error(f"Erro ao carregar/mapear dados: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_spx, df_cluster, df_fleet = carregar_bases_sql()

# --- 4. FUNÇÃO DE DISTÂNCIA ---
def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if any(pd.isna([lat1, lon1, lat2, lon2])): return 9999
        r = 6371 
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
        a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

# --- 5. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador", "🚚 Fleet"])

with tab1:
    id_busca = st.text_input("🔎 Bipar Pedido:").strip()
    if id_busca and not df_spx.empty:
        # Agora o código sempre encontrará 'order_id' graças ao normalizador!
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca]
        
        if not pacote.empty:
            lat, lon = pacote['latitude'].iloc[0], pacote['longitude'].iloc[0]
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(lat, lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').head(3)
            
            cols = st.columns(3)
            for i, row in enumerate(sugestoes.itertuples()):
                cols[i].metric(f"📍 {row.corridor_cage}", f"{row.dist_km:.2f} km")
        else:
            st.warning("Pedido não encontrado na base.")

with tab2:
    d_id = st.text_input("🆔 Bipar Motorista:").strip()
    if d_id and not df_fleet.empty:
        motorista = df_fleet[df_fleet['driver_id'].astype(str) == d_id]
        if not motorista.empty:
            st.success(f"👤 {motorista['driver_name'].values[0]} | 🚛 {motorista['license_plate'].values[0]}")
        else:
            st.error("Motorista não cadastrado.")
