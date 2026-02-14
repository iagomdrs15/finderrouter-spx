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
    'latitude': ['latitude', 'lat', 'y', 'lat_y'],
    'longitude': ['longitude', 'long', 'x', 'lng', 'lon_x'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'setor'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa'],
    'planned_at': ['planned_at', 'id_planejamento', 'task_id']
}

# --- 3. CARREGAMENTO COM TRATAMENTO NUMÉRICO ---
@st.cache_data(ttl=60)
def carregar_bases_sql():
    try:
        spx = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        df_spx = normalizar_dados(spx, SINONIMOS)
        df_cluster = normalizar_dados(cluster, SINONIMOS)
        df_fleet = normalizar_dados(fleet, SINONIMOS)

        # RESOLUÇÃO DA DISTÂNCIA: Limpa e força conversão numérica
        for df in [df_spx, df_cluster]:
            if not df.empty:
                for col in ['latitude', 'longitude']:
                    if col in df.columns:
                        df[col] = df[col].astype(str).str.replace(',', '.')
                        df[col] = pd.to_numeric(df[col], errors='coerce')
        
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
    color = '#28a745'
    try:
        if pd.notna(row['tempo_hub']) and ":" in str(row['tempo_hub']):
            m = int(str(row['tempo_hub']).split(':')[1])
            if m >= 15: color = '#ff4b4b'
            elif m >= 11: color = '#f9d71c'
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
                    # Visualização da Etiqueta Premium
                    st.markdown(f"""
                    <div style="background:#1e1e1e; padding:20px; border-radius:15px; border: 2px solid #ff4b4b; text-align:center; margin-bottom:10px">
                        <p style="color:gray; font-size:12px; margin:0">CLUSTER</p>
                        <h1 style="color:white; margin:5px 0; font-size:50px">{row.corridor_cage}</h1>
                        <p style="color:#ff4b4b; font-weight:bold; margin:0">{row.dist_km:.2f} km</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Botões Separados: Alocar (Link) e Imprimir
                    c_btn1, c_btn2 = st.columns(2)
                    id_shopee = getattr(row, 'planned_at', '')
                    link_shopee = f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={id_shopee}"
                    
                    with c_btn1:
                        st.link_button("📥 Alocar", link_shopee, use_container_width=True)
                    with c_btn2:
                        if st.button(f"🖨️ Imprimir", key=f"prt_{i}", use_container_width=True):
                            st.toast(f"Etiqueta {row.corridor_cage} enviada!", icon="🖨️")
        else:
            st.error("❌ Pedido não encontrado na base SQL.")

with tab2:
    st.write("### 📥 Registro de Movimentação")
    col_in, col_card = st.columns([1, 1.2])
    
    with col_in:
        d_id = st.text_input("🆔 Bipar Driver ID:", key="fleet_scan").strip()
    
    if d_id and not df_fleet_base.empty:
        match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
        if not match.empty:
            nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
            
            # Placa Mercosul Refinada
            with col_card:
                st.markdown(f"""
                <div style="width:280px; background:white; border-radius:12px; border: 6px solid #003399; box-shadow: 5px 5px 15px rgba(0,0,0,0.5); overflow:hidden">
                    <div style="background:#003399; height:35px; display:flex; align-items:center; justify-content:space-between; padding:0 15px">
                        <span style="color:white; font-size:10px; font-weight:bold">BRASIL</span>
                        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Flag_of_Brazil.svg/200px-Flag_of_Brazil.svg.png" width="20">
                    </div>
                    <div style="height:80px; display:flex; align-items:center; justify-content:center">
                        <h1 style="color:black; font-family:serif; font-size:55px; margin:0; letter-spacing:5px">{placa}</h1>
                    </div>
                </div>
                <h3 style="margin-top:15px">{nome}</h3>
                """, unsafe_allow_html=True)

            # Lógica de Registro SQL
            aberto = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
            if aberto.data:
                res = aberto.data[0]
                entrada_dt = datetime.fromisoformat(res['entrada'].replace('Z', '+00:00'))
                tempo = str(datetime.now().astimezone() - entrada_dt).split('.')[0]
                conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": tempo}).eq("id", res['id']).execute()
                st.toast(f"🏁 Saída: {nome}", icon="🏁")
            else:
                conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                st.toast(f"📥 Entrada: {nome}", icon="📥")
            
            time.sleep(1)
            st.rerun()

    st.divider()
    logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
    if logs.data:
        st.dataframe(pd.DataFrame(logs.data)[['nome', 'placa', 'entrada', 'tempo_hub']].style.apply(style_sla, axis=1), use_container_width=True)
