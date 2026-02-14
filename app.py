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

SINONIMOS = {
    'order_id': ['order_id', 'pedido', 'spx_tn', 'rastreio', 'id'],
    'latitude': ['latitude', 'lat', 'y'],
    'longitude': ['longitude', 'long', 'x', 'lng'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'setor'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa'],
    'planned_at': ['planned_at', 'id_planejamento', 'task_id', 'id_tarefa']
}

# --- 3. CARREGAMENTO COM CORREÇÃO ---
@st.cache_data(ttl=60)
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
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID / SPX_TN):", key="aloc_print_v5").strip()
    if id_busca:
        aloc_alvo = pd.DataFrame()
        # Busca integrada nas bases
        if not df_spx.empty and id_busca in df_spx['order_id'].astype(str).values:
            aloc_alvo = df_spx[df_spx['order_id'].astype(str) == id_busca]
            st.success("📦 Pedido Localizado!")
        elif not df_cluster.empty and id_busca in df_cluster['order_id'].astype(str).values:
            aloc_alvo = df_cluster[df_cluster['order_id'].astype(str) == id_busca]
            st.info("📍 ID Localizado no Cluster")

        if not aloc_alvo.empty:
            p_lat, p_lon = aloc_alvo['latitude'].iloc[0], aloc_alvo['longitude'].iloc[0]
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').drop_duplicates(subset=['corridor_cage']).head(3)
            
            # --- 🖼️ PRÉ-VISUALIZAÇÃO DA ETIQUETA (O DETERMINANTE VISUAL) ---
            melhor_opcao = sugestoes.iloc[0]
            st.write("### 📄 Pré-visualização da Etiqueta")
            st.markdown(f"""
            <div style="background:white; padding:30px; border-radius:10px; border: 5px solid black; width:350px; margin:auto; text-align:center; box-shadow: 10px 10px 0px #ff4b4b">
                <p style="color:black; font-weight:bold; font-size:18px; margin:0; border-bottom:2px solid black">SPX EXPRESS - HUB PVH</p>
                <h1 style="color:black; font-size:85px; margin:10px 0; font-family: 'Arial Black', Gadget, sans-serif">{melhor_opcao.corridor_cage}</h1>
                <p style="color:black; font-size:14px; margin:0">ROTA: {melhor_opcao.corridor_cage} | DIST: {melhor_opcao.dist_km:.2f}km</p>
                <div style="margin-top:15px; background:black; color:white; padding:5px; font-weight:bold">PARA ALOCAÇÃO IMEDIATA</div>
            </div>
            """, unsafe_allow_html=True)
            
            st.divider()
            
            # --- 📍 OPÇÕES DE ALOCAÇÃO ---
            st.write("### ⚙️ Ações de Alocação")
            cols = st.columns(len(sugestoes))
            for i, row in enumerate(sugestoes.itertuples()):
                with cols[i]:
                    st.markdown(f"""
                    <div style="background:#1e1e1e; padding:15px; border-radius:10px; border: 2px solid #ff4b4b; text-align:center; margin-bottom:10px">
                        <h2 style="color:white; margin:0">{row.corridor_cage}</h2>
                        <p style="color:#ff4b4b; font-weight:bold; margin:0">{row.dist_km:.2f} km</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Botão de Alocação Shopee
                    planned_id = str(getattr(row, 'planned_at', '')).strip()
                    if planned_id and planned_id != 'nan' and planned_id != '':
                        st.link_button("📥 Alocar na Shopee", f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={planned_id}", use_container_width=True)
                    else:
                        st.button("⚠️ Sem ID Task", use_container_width=True, disabled=True)

                    if st.button(f"🖨️ Imprimir {row.corridor_cage}", key=f"print_v5_{i}", use_container_width=True):
                        st.balloons()
                        st.toast(f"Enviando etiqueta {row.corridor_cage} para a Zebra...", icon="✅")
        else:
            st.error("❌ Pedido não encontrado. Verifique a coluna spx_tn.")

with tab2:
    st.write("### 📥 Fleet Control")
    d_id = st.text_input("🆔 Bipar Driver ID:", key="fleet_v4").strip()
    if d_id and st.session_state.get('last_bip') != d_id:
        match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id] if not df_fleet_base.empty else pd.DataFrame()
        if not match.empty:
            nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
            st.markdown(f"<h2>{placa} - {nome}</h2>", unsafe_allow_html=True)
            st.session_state.last_bip = d_id
            st.rerun()
    elif not d_id:
        st.session_state.last_bip = None

