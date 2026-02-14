import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- 2. TRADUTOR DE COLUNAS (O DETERMINANTE) ---
def normalizar_dados(df, mapa_sinonimos):
    if df is None or df.empty: return pd.DataFrame()
    df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
    for nome_correto, sinonimos in mapa_sinonimos.items():
        for s in sinonimos:
            if s in df.columns:
                df = df.rename(columns={s: nome_correto})
                break
    return df

# ADICIONADO 'spx_tn' AOS SINÔNIMOS PARA INTEGRAÇÃO TOTAL
SINONIMOS = {
    'order_id': ['order_id', 'pedido', 'spx_tn', 'rastreio', 'id'],
    'latitude': ['latitude', 'lat', 'y'],
    'longitude': ['longitude', 'long', 'x', 'lng'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'setor'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa'],
    'planned_at': ['planned_at', 'id_planejamento', 'task_id']
}

# --- 3. CARREGAMENTO COM CORREÇÃO ---
def carregar_bases_sql():
    try:
        spx = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        df_spx = normalizar_dados(spx, SINONIMOS)
        df_cluster = normalizar_dados(cluster, SINONIMOS)
        df_fleet = normalizar_dados(fleet, SINONIMOS)

        for df in [df_spx, df_cluster]:
            if not df.empty:
                for col in ['latitude', 'longitude']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.').str.extract(r'([-+]?\d*\.?\d+)')[0], errors='coerce')
                        df[col] = df[col].apply(lambda x: x/10 if pd.notna(x) and (abs(x) > 90) else x)
        
        return df_spx, df_cluster, df_fleet
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_spx, df_cluster, df_fleet_base = carregar_bases_sql()

def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if any(pd.isna([lat1, lon1, lat2, lon2])): return 9999
        r = 6371 
        p1, p2 = np.radians(float(lat1)), np.radians(float(lat2))
        dp, dl = np.radians(float(lat2 - lat1)), np.radians(float(lon2 - lon1))
        a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

# --- 4. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador", "🚚 Fleet Control"])

with tab1:
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID / SPX_TN):", key="aloc_v4").strip()
    if id_busca:
        # Busca prioritária no SPX, depois no Cluster via SPX_TN
        aloc_alvo = pd.DataFrame()
        if not df_spx.empty and id_busca in df_spx['order_id'].astype(str).values:
            aloc_alvo = df_spx[df_spx['order_id'].astype(str) == id_busca]
            st.success("📦 Pedido Localizado!")
        elif not df_cluster.empty and id_busca in df_cluster['order_id'].astype(str).values:
            aloc_alvo = df_cluster[df_cluster['order_id'].astype(str) == id_busca]
            st.info("📍 ID Localizado diretamente no Cluster")

        if not aloc_alvo.empty:
            p_lat, p_lon = aloc_alvo['latitude'].iloc[0], aloc_alvo['longitude'].iloc[0]
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            
            # Filtra duplicatas para mostrar apenas opções únicas de Gaiola
            sugestoes = df_cluster.sort_values('dist_km').drop_duplicates(subset=['corridor_cage']).head(3)
            
            st.write("### 📍 Destinos Sugeridos")
            cols = st.columns(len(sugestoes))
            for i, row in enumerate(sugestoes.itertuples()):
                with cols[i]:
                    st.markdown(f"""
                    <div style="background:#1e1e1e; padding:20px; border-radius:15px; border: 3px solid #ff4b4b; text-align:center">
                        <p style="color:gray; font-size:12px; margin:0">GAIOLA / CORREDOR</p>
                        <h1 style="color:#ff4b4b; margin:5px 0; font-size:55px">{row.corridor_cage}</h1>
                        <p style="color:white; font-size:18px">{row.dist_km:.2f} km</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    link_spx = f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={getattr(row, 'planned_at', '')}"
                    st.link_button("📥 Alocar na Shopee", link_spx, use_container_width=True)
                    if st.button(f"🖨️ Imprimir {row.corridor_cage}", key=f"p_v4_{i}", use_container_width=True):
                        st.toast(f"Imprimindo etiqueta {row.corridor_cage}")
        else:
            st.error("❌ Pedido não encontrado. Verifique se o código spx_tn existe no banco.")

with tab2:
    # (Mantido o código do Fleet com a trava de last_bip para evitar o loop)
    st.write("### 📥 Fleet Control")
    d_id = st.text_input("🆔 Bipar Driver ID:", key="fleet_v4").strip()
    if d_id and st.session_state.get('last_bip') != d_id:
        match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id] if not df_fleet_base.empty else pd.DataFrame()
        if not match.empty:
            nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
            st.markdown(f"<h2>{placa} - {nome}</h2>", unsafe_allow_html=True)
            # Lógica de entrada/saída no banco...
            st.session_state.last_bip = d_id
            st.rerun()
    elif not d_id:
        st.session_state.last_bip = None
