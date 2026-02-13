import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- 2. O DETERMINANTE (MAPEADOR DE COLUNAS) ---
def normalizar_dados(df, mapa_sinonimos):
    if df is None or df.empty: return pd.DataFrame()
    df.columns = [str(c).lower().strip().replace(" ", "_") for c in df.columns]
    for nome_correto, sinonimos in mapa_sinonimos.items():
        for s in sinonimos:
            if s in df.columns:
                df = df.rename(columns={s: nome_correto})
                break
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
    return df

SINONIMOS = {
    'order_id': ['order_id', 'pedido', 'id', 'order', 'rastreio'],
    'latitude': ['latitude', 'lat', 'lat_y', 'y'],
    'longitude': ['longitude', 'long', 'lng', 'lon', 'x'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'corredor'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa', 'veiculo']
}

# --- 3. CARREGAMENTO ---
@st.cache_data(ttl=60) # Cache curto para facilitar testes milorde
def carregar_bases_sql():
    try:
        spx_raw = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster_raw = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet_raw = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        df_spx = normalizar_dados(spx_raw, SINONIMOS)
        df_cluster = normalizar_dados(cluster_raw, SINONIMOS)
        df_fleet = normalizar_dados(fleet_raw, SINONIMOS)

        for df in [df_spx, df_cluster]:
            if not df.empty and 'latitude' in df.columns:
                df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
                df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
        
        return df_spx, df_cluster, df_fleet
    except Exception as e:
        st.error(f"Erro ao carregar: {e}")
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
    color = 'white'
    try:
        tempo = row['tempo_hub']
        if pd.notna(tempo) and ":" in str(tempo):
            partes = list(map(int, str(tempo).split(':')))
            minutos = (partes[0] * 60 + partes[1]) if len(partes) >= 2 else 0
            if minutos >= 15: color = '#ff4b4b' # Vermelho
            elif minutos >= 11: color = '#f9d71c' # Amarelo
            else: color = '#28a745' # Verde
    except: pass
    return [f'background-color: {color}; color: black' if name == 'tempo_hub' else '' for name in row.index]

# --- 5. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador", "🚚 Fleet Pro"])

with tab1:
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID):").strip()
    if id_busca and not df_spx.empty:
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca]
        
        if not pacote.empty:
            p_lat, p_lon = pacote['latitude'].iloc[0], pacote['longitude'].iloc[0]
            st.success(f"📦 Pedido Localizado!")
            
            if not df_cluster.empty:
                df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
                sugestoes = df_cluster.sort_values('dist_km').head(3)
                
                cols = st.columns(3)
                for i, row in enumerate(sugestoes.itertuples()):
                    with cols[i]:
                        st.subheader(f"📍 {row.corridor_cage}")
                        st.metric("Distância", f"{row.dist_km:.2f} km")
                        if st.button(f"Imprimir Etiqueta {i}", key=f"btn_{i}"):
                            st.toast(f"Enviando para impressora: {row.corridor_cage}", icon="🖨️")
            else:
                st.warning("⚠️ Base Cluster (gaiolas) está vazia no banco.")
        else:
            st.warning("❌ Pedido não encontrado na Base SPX.")

with tab2:
    @st.fragment # Melhora a performance dos bips
    def app_fleet():
        c1, c2 = st.columns([1, 2])
        with c1:
            d_id = st.text_input("🆔 Bipar Driver ID:", key="scan").strip()
            if d_id and not df_fleet_base.empty:
                match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
                if not match.empty:
                    nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
                    
                    # Lógica SQL de Entrada/Saída
                    aberto = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
                    
                    if aberto.data: # Registrar Saída
                        row_id = aberto.data[0]['id']
                        entrada_dt = datetime.fromisoformat(aberto.data[0]['entrada'].replace('Z', '+00:00'))
                        delta = datetime.now().astimezone() - entrada_dt
                        tempo = str(delta).split('.')[0]
                        conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": tempo}).eq("id", row_id).execute()
                        st.toast(f"🏁 SAÍDA: {nome}", icon="👋")
                    else: # Registrar Entrada
                        conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                        st.toast(f"📥 ENTRADA: {nome}", icon="✅")
                else:
                    st.error("❌ Motorista não cadastrado.")
        
        with c2:
            st.write("### 🕒 Registros de Hoje")
            logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
            if logs.data:
                df_logs = pd.DataFrame(logs.data)
                st.dataframe(df_logs[['nome', 'placa', 'entrada', 'tempo_hub']].style.apply(style_sla, axis=1), use_container_width=True)
    app_fleet()
