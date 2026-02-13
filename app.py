import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")

# Conexão nativa que busca SUPABASE_URL e SUPABASE_KEY nos Secrets
conn = st.connection("supabase", type=SupabaseConnection)

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- 2. FUNÇÕES DE APOIO E MAPEAMENTO ---
def mapear_colunas(df, de_para):
    """Traduz nomes de colunas do CSV para o padrão do SQL"""
    for padrao, variacoes in de_para.items():
        for var in variacoes:
            if var in df.columns:
                df = df.rename(columns={var: padrao})
                break
    return df

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
    text_color = 'black'
    try:
        tempo = row['tempo_hub']
        if pd.notna(tempo) and tempo != "":
            partes = list(map(int, tempo.split(':')))
            minutos = (partes[0] * 60 + partes[1]) if len(partes) >= 2 else 0
            if minutos >= 15: color, text_color = '#ff4b4b', 'white'
            elif minutos >= 11: color, text_color = '#f9d71c', 'black'
            else: color, text_color = '#28a745', 'white'
    except: pass
    return [f'background-color: {color}; color: {text_color}' if name == 'tempo_hub' else '' for name in row.index]

# --- 3. CARREGAMENTO DE DADOS COM CACHE ---
@st.cache_data(ttl=600)
def carregar_bases_sql():
    try:
        spx = conn.table("base_spx").select("*").execute()
        cluster = conn.table("base_cluster").select("*").execute()
        fleet = conn.table("base_fleet").select("*").execute()
        return pd.DataFrame(spx.data), pd.DataFrame(cluster.data), pd.DataFrame(fleet.data)
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_spx, df_cluster, df_fleet_base = carregar_bases_sql()

# --- 4. INTERFACE PRINCIPAL ---
tab_aloc, tab_fleet, tab_admin = st.tabs(["🎯 Alocador", "🚚 Fleet", "⚙️ Admin Bases"])

# --- ABA ALOCADOR ---
with tab_aloc:
    col_id, col_obs = st.columns(2)
    id_busca = col_id.text_input("🔎 Order ID / Cluster:").strip()
    
    if id_busca and not df_spx.empty:
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca]
        ref_lat = pacote['latitude'].iloc[0] if not pacote.empty else HUB_LAT
        ref_lon = pacote['longitude'].iloc[0] if not pacote.empty else HUB_LON

        df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(ref_lat, ref_lon, x['latitude'], x['longitude']), axis=1)
        sugestoes = df_cluster.sort_values('dist_km').drop_duplicates('corridor_cage').head(3)

        c1, c2 = st.columns([1, 1.2])
        with c1:
            for i, row in sugestoes.iterrows():
                st.info(f"📍 {row['corridor_cage']} ({row['dist_km']:.2f}km)")
        with c2:
            st.map(pd.DataFrame({'lat': [ref_lat], 'lon': [ref_lon]}), zoom=14)

# --- ABA FLEET ---
with tab_fleet:
    @st.fragment
    def sessao_fleet():
        c_in, c_list = st.columns([1, 2])
        with c_in:
            d_id = st.text_input("🆔 Bipar Driver ID:", key="scan_sql").strip()
            if d_id and not df_fleet_base.empty:
                match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
                if not match.empty:
                    nome, placa = match['driver_name'].values[0], str(match['license_plate'].values[0])
                    res = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
                    
                    if res.data: # Saída
                        row_id = res.data[0]['id']
                        delta = datetime.now().astimezone() - datetime.fromisoformat(res.data[0]['entrada'].replace('Z', '+00:00'))
                        conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": str(delta).split('.')[0]}).eq("id", row_id).execute()
                        st.success(f"🏁 Saída: {nome}")
                    else: # Entrada
                        conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                        st.info(f"📥 Entrada: {nome}")
        with c_list:
            logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
            if logs.data:
                st.dataframe(pd.DataFrame(logs.data)[['nome', 'placa', 'entrada', 'tempo_hub']].style.apply(style_sla, axis=1), use_container_width=True)
    sessao_fleet()

# --- ABA ADMIN: ATUALIZAÇÃO AUTOMÁTICA ---
with tab_admin:
    st.header("🔄 Central de Atualização de Bases (CSV)")
    
    # Configuração de mapeamento para as 3 bases principais
    config_bases = {
        "base_spx": {'order_id': ['order_id','pedido','ID'], 'latitude': ['latitude','lat'], 'longitude': ['longitude','lng']},
        "base_cluster": {'corridor_cage': ['corridor_cage','gaiola'], 'latitude': ['latitude','lat'], 'longitude': ['longitude','lng']},
        "base_fleet": {'driver_id': ['driver_id','id'], 'driver_name': ['driver_name','nome'], 'license_plate': ['license_plate','placa']}
    }
    
    escolha = st.selectbox("Selecione a base para atualizar:", list(config_bases.keys()))
    arquivo = st.file_uploader(f"Subir novo CSV para {escolha}", type=["csv"])
    
    if arquivo and st.button(f"🚀 Substituir dados em {escolha}"):
        df_novo = pd.read_csv(arquivo)
        df_mapeado = mapear_colunas(df_novo, config_bases[escolha])
        
        # Garante apenas as colunas necessárias
        colunas_finais = list(config_bases[escolha].keys())
        df_final = df_mapeado[colunas_finais].dropna()
        
        try:
            # Limpa e insere
            conn.table(escolha).delete().neq("id", -1).execute()
            conn.table(escolha).insert(df_final.to_dict(orient="records")).execute()
            st.success(f"✅ {len(df_final)} registros atualizados! Limpe o cache para aplicar.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Erro: {e}")
