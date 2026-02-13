import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135

# --- 2. O DETERMINANTE (TRADUTOR DE COLUNAS FLEXÍVEL) ---
def normalizar_dados(df, mapa_sinonimos):
    """Limpa colunas, traduz nomes e remove espaços invisíveis"""
    if df.empty: return df
    
    # Limpa nomes das colunas (tira espaços, pontos e deixa minúsculo)
    df.columns = [str(c).lower().strip().replace(" ", "_").replace(".", "") for c in df.columns]
    
    # Tradução de sinônimos
    for nome_correto, sinonimos in mapa_sinonimos.items():
        for s in sinonimos:
            if s in df.columns:
                df = df.rename(columns={s: nome_correto})
                break
    
    # Limpeza de conteúdo (tira espaços de dentro das células de texto)
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
        
    return df

SINONIMOS = {
    'order_id': ['order_id', 'pedido', 'id', 'order', 'rastreio', 'br2604465992725'],
    'latitude': ['latitude', 'lat', 'lat_y', 'y', 'coordenada_y'],
    'longitude': ['longitude', 'long', 'lng', 'lon', 'x', 'coordenada_x'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'corredor', 'cage'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf', 'motorista_id'],
    'driver_name': ['driver_name', 'nome', 'motorista', 'nome_motorista'],
    'license_plate': ['license_plate', 'placa', 'veiculo', 'placa_veiculo']
}

# --- 3. CARREGAMENTO COM TRATAMENTO DE CHOQUE ---
@st.cache_data(ttl=600)
def carregar_bases_sql():
    try:
        # Busca dados do banco
        spx_raw = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster_raw = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet_raw = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        # Normaliza as 3 bases
        df_spx = normalizar_dados(spx_raw, SINONIMOS)
        df_cluster = normalizar_dados(cluster_raw, SINONIMOS)
        df_fleet = normalizar_dados(fleet_raw, SINONIMOS)
        
        # Converte coordenadas para números (essencial para o cálculo)
        for df in [df_spx, df_cluster]:
            if not df.empty:
                if 'latitude' in df.columns:
                    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
                    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
        
        return df_spx.dropna(subset=['order_id']) if not df_spx.empty else df_spx, df_cluster, df_fleet
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
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
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID):").strip()
    if id_busca:
        if not df_spx.empty and 'order_id' in df_spx.columns:
            pacote = df_spx[df_spx['order_id'].astype(str) == id_busca]
            
            if not pacote.empty:
                lat, lon = pacote['latitude'].iloc[0], pacote['longitude'].iloc[0]
                st.success(f"✅ Pedido Localizado!")
                
                # Calcula distância e sugere as 3 melhores gaiolas
                df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(lat, lon, x['latitude'], x['longitude']), axis=1)
                sugestoes = df_cluster.sort_values('dist_km').head(3)
                
                cols = st.columns(3)
                for i, row in enumerate(sugestoes.itertuples()):
                    cols[i].metric(f"📍 {row.corridor_cage}", f"{row.dist_km:.2f} km")
            else:
                st.warning(f"⚠️ Pedido {id_busca} não encontrado na base_spx.")
        else:
            st.error("❌ Erro: A coluna de ID não foi reconhecida ou a base está vazia.")

with tab2:
    d_id = st.text_input("🆔 Bipar Motorista (Driver ID):").strip()
    if d_id and not df_fleet.empty:
        motorista = df_fleet[df_fleet['driver_id'].astype(str) == d_id]
        if not motorista.empty:
            st.success(f"👤 {motorista['driver_name'].values[0]} | 🚛 {motorista['license_plate'].values[0]}")
        else:
            st.error("Motorista não cadastrado na base_fleet.")
