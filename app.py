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
    'order_id': ['order_id', 'pedido', 'id', 'rastreio'],
    'latitude': ['latitude', 'lat', 'y'],
    'longitude': ['longitude', 'long', 'x', 'lng'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'setor'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa']
}

# --- 3. CARREGAMENTO COM TRATAMENTO NUMÉRICO ---
@st.cache_data(ttl=60)
def carregar_bases_sql():
    try:
        # Busca dados e força conversão para garantir cálculo de distância
        spx = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        df_spx = normalizar_dados(spx, SINONIMOS)
        df_cluster = normalizar_dados(cluster, SINONIMOS)
        df_fleet = normalizar_dados(fleet, SINONIMOS)

        # CORREÇÃO DA DISTÂNCIA 9999: Força colunas a serem números
        for df in [df_spx, df_cluster]:
            if not df.empty:
                df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
                df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
        
        return df_spx, df_cluster, df_fleet
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_spx, df_cluster, df_fleet_base = carregar_bases_sql()

# --- 4. FUNÇÕES DE APOIO ---
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
    color = '#28a745' # Verde
    try:
        if pd.notna(row['tempo_hub']) and ":" in str(row['tempo_hub']):
            m = int(str(row['tempo_hub']).split(':')[1])
            if m >= 15: color = '#ff4b4b' # Vermelho
            elif m >= 11: color = '#f9d71c' # Amarelo
    except: pass
    return [f'background-color: {color}; color: black' if name == 'tempo_hub' else '' for name in row.index]

# --- 5. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador de Pacotes", "🚚 Fleet Control"])

with tab1:
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID):", placeholder="Scan aqui...").strip()
    if id_busca:
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca] if not df_spx.empty else pd.DataFrame()
        
        if not pacote.empty:
            p_lat, p_lon = pacote['latitude'].iloc[0], pacote['longitude'].iloc[0]
            st.success(f"📦 Pedido {id_busca} Localizado!")
            
            # Cruzamento de dados para Alocação
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').head(3)
            
            st.write("### 📍 Sugestões de Alocação")
            cols = st.columns(3)
            for i, row in enumerate(sugestoes.itertuples()):
                with cols[i]:
                    # Visualização da Etiqueta em destaque
                    st.markdown(f"""
                    <div style="background:#1e1e1e; padding:20px; border-radius:10px; border: 2px solid #ff4b4b; text-align:center">
                        <h1 style="color:#ff4b4b; margin:0">{row.corridor_cage}</h1>
                        <p style="color:gray; margin:0">{row.dist_km:.2f} km de distância</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🖨️ Alocar em {row.corridor_cage}", key=f"btn_{i}"):
                        st.balloons() # Animação de sucesso
                        st.toast(f"Alocado com sucesso: {row.corridor_cage}", icon="✅")
        else:
            st.error("❌ Pedido não encontrado na base SQL.")

with tab2:
    st.write("### 📥 Registro de Movimentação")
    col_in, col_card = st.columns([1, 1])
    
    with col_in:
        d_id = st.text_input("🆔 Bipar Driver ID:", key="fleet_scan").strip()
    
    if d_id and not df_fleet_base.empty:
        match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
        if not match.empty:
            nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
            
            # Animação da Placa em Destaque
            with col_card:
                st.markdown(f"""
                <div style="background:white; padding:10px; border-radius:5px; border: 4px solid black; text-align:center; width:200px">
                    <p style="color:black; font-weight:bold; font-size:12px; margin:0; border-bottom:1px solid black">BRASIL</p>
                    <h2 style="color:black; margin:5px 0; font-family:serif">{placa}</h2>
                </div>
                <h3 style="margin-top:10px">{nome}</h3>
                """, unsafe_allow_html=True)

            # Lógica de Registro SQL
            aberto = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
            if aberto.data:
                res = aberto.data[0]
                entrada_dt = datetime.fromisoformat(res['entrada'].replace('Z', '+00:00'))
                tempo = str(datetime.now().astimezone() - entrada_dt).split('.')[0]
                conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": tempo}).eq("id", res['id']).execute()
                st.toast(f"🏁 Saída Registrada!", icon="🏁")
            else:
                conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                st.toast(f"📥 Entrada Registrada!", icon="📥")
            
            time.sleep(1) # Pausa para ver a animação
            st.rerun()

    # Tabela de Histórico
    st.divider()
    logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
    if logs.data:
        st.dataframe(pd.DataFrame(logs.data)[['nome', 'placa', 'entrada', 'tempo_hub']].style.apply(style_sla, axis=1), use_container_width=True)

