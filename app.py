import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit.components.v1 as components
from st_supabase_connection import SupabaseConnection

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")

# --- CONEXÃO COM BANCO DE DADOS (SUPABASE) ---
# As chaves 'supabase_url' e 'supabase_key' devem estar nos Secrets do Cloud
conn = st.connection("supabase", type=SupabaseConnection)

# --- COORDENADAS DO HUB (PORTO VELHO) ---
HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- FUNÇÕES DE ESTILO E GEOGRAFIA ---
def style_sla(row):
    """SLA Rigoroso: Verde < 10min | Amarelo 11-14min | Vermelho >= 15min"""
    color = 'white'
    text_color = 'black'
    try:
        tempo = row['tempo_hub']
        if pd.notna(tempo) and tempo != "":
            partes = list(map(int, tempo.split(':')))
            # Lida com formatos H:M:S ou M:S
            total_segundos = (partes[0] * 3600 + partes[1] * 60 + partes[2]) if len(partes) == 3 else (partes[0] * 60 + partes[1])
            minutos = total_segundos / 60
            
            if minutos >= 15: 
                color, text_color = '#ff4b4b', 'white' # Alerta Vermelho
            elif minutos >= 11: 
                color, text_color = '#f9d71c', 'black' # Atenção Amarela
            else: 
                color, text_color = '#28a745', 'white' # OK Verde
    except: pass
    return [f'background-color: {color}; color: {text_color}' if name == 'tempo_hub' else '' for name in row.index]

def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if any(pd.isna([lat1, lon1, lat2, lon2])): return 9999
        r = 6371 
        phi1, phi2 = np.radians(lat1), np.radians(lat2)
        dphi, dlambda = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
        a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

# --- CARREGAMENTO DE DADOS (SQL) ---
@st.cache_data(ttl=600)
def carregar_bases_sql():
    # Consulta as tabelas que você criou no Supabase
    spx = conn.table("Base SPX").select("*").execute()
    cluster = conn.table("Base Cluster").select("*").execute()
    fleet = conn.table("Base Fleet").select("*").execute()
    return pd.DataFrame(spx.data), pd.DataFrame(cluster.data), pd.DataFrame(fleet.data)

# --- INTERFACE ---
with st.sidebar:
    st.header("⚙️ Painel Admin")
    st.success("🟢 Supabase SQL Conectado")
    if st.button("🔄 Sincronizar Tabelas", width='stretch'):
        st.cache_data.clear()
        st.rerun()

# Carregamento inicial das bases
df_spx, df_cluster, df_fleet_base = carregar_bases_sql()

tab_alocador, tab_fleet = st.tabs(["🎯 Alocador de Pacotes", "🚚 Gestão de Fleet (SQL)"])

# --- ABA 1: ALOCADOR ---
with tab_alocador:
    col_s, col_o = st.columns([1, 1])
    with col_s: id_busca = st.text_input("🔎 Bipar Order ID / Cluster:", key="aloc_scan").strip()
    with col_o: obs_label = st.text_input("📝 Obs Etiqueta:", placeholder="Opcional...")

    if id_busca:
        # Busca por Order ID ou Cluster Name
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca] if not df_spx.empty else pd.DataFrame()
        item_cluster = df_cluster[df_cluster.apply(lambda x: id_busca.lower() in str(x).lower(), axis=1)]

        ref_lat = pacote['latitude'].iloc[0] if not pacote.empty else (item_cluster['latitude'].iloc[0] if not item_cluster.empty else HUB_LAT)
        ref_lon = pacote['longitude'].iloc[0] if not pacote.empty else (item_cluster['longitude'].iloc[0] if not item_cluster.empty else HUB_LON)

        df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(ref_lat, ref_lon, x['latitude'], x['longitude']), axis=1)
        sugestoes = df_cluster.sort_values('dist_km').drop_duplicates('corridor_cage').head(3)

        c1, c2 = st.columns([1, 1.2])
        with c1:
            st.success(f"📍 Referência: {'Pacote' if not pacote.empty else 'HUB'}")
            for i, row in sugestoes.iterrows():
                with st.expander(f"📍 {row['corridor_cage']} ({row['dist_km']:.2f}km)"):
                    if st.button("🖨️ Imprimir", key=f"print_{i}"):
                        st.info("Simulando impressão térmica...")
                        # Aqui mantemos a lógica de componentes.html se desejar reativar
        with c2:
            m_df = pd.DataFrame({'lat': [ref_lat], 'lon': [ref_lon]})
            st.map(m_df, zoom=14)

# --- ABA 2: GESTÃO DE FLEET (SQL) ---
with tab_fleet:
    @st.fragment
    def sessao_fleet_sql():
        st.header(f"⏱️ Controle de Carregamento SQL - {hoje_str}")
        col_f1, col_f2 = st.columns([1, 2])
        
        with col_f1:
            d_id = st.text_input("🆔 Bipar Driver ID:", key="sql_bip").strip()
            if d_id:
                # Busca na base de motoristas do SQL (df_fleet_base)
                match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
                if not match.empty:
                    nome, placa = match['driver_name'].values[0], str(match['license_plate'].values[0])
                    agora = datetime.now()
                    
                    # Pergunta ao SQL: Existe este Driver ID sem horário de saída (null)?
                    res = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
                    
                    if res.data:
                        # Registro de Saída
                        row_id = res.data[0]['id']
                        # Converte string UTC para datetime com fuso
                        entrada_dt = datetime.fromisoformat(res.data[0]['entrada'].replace('Z', '+00:00'))
                        delta = agora.astimezone() - entrada_dt
                        tempo_s = str(delta).split('.')[0]
                        
                        conn.table("log_fleet").update({
                            "saida": agora.isoformat(), 
                            "tempo_hub": tempo_s
                        }).eq("id", row_id).execute()
                        st.toast(f"Saída: {nome} | Tempo: {tempo_s}", icon="🏁")
                    else:
                        # Registro de Entrada
                        conn.table("log_fleet").insert({
                            "driver_id": d_id, 
                            "nome": nome, 
                            "placa": placa, 
                            "data": hoje_str
                        }).execute()
                        st.toast(f"Entrada: {nome}", icon="📥")
                    
                    # Preview visual da placa
                    p_html = f"""<div style="background:#FFF;border:3px solid #000;border-radius:6px;width:200px;height:70px;margin:10px auto;display:flex;flex-direction:column;align-items:center;justify-content:space-between;font-family:sans-serif;border-top:12px solid #003399;"><div style="color:white;font-size:7px;font-weight:bold;margin-top:-11px;">BRASIL</div><div style="font-size:28px;font-weight:900;letter-spacing:1px;color:#000;padding-bottom:5px;">{placa.upper()}</div></div>"""
                    components.html(p_html, height=90)
            
        with col_f2:
            st.subheader("📋 Painel de Monitoramento (Dia)")
            # Puxa os bips do dia direto do servidor SQL
            logs_sql = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
            if logs_sql.data:
                df_view = pd.DataFrame(logs_sql.data)
                # Seleção de colunas para o operador
                df_final = df_view[['driver_id', 'nome', 'placa', 'entrada', 'saida', 'tempo_hub']]
                st.dataframe(df_final.style.apply(style_sla, axis=1), use_container_width=True)
            else:
                st.info("Aguardando registros...")

    sessao_fleet_sql()
