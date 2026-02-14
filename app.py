import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
from st_supabase_connection import SupabaseConnection
import streamlit.components.v1 as components

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
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID / SPX_TN):", key="aloc_final_v6").strip()
    
    if id_busca:
        # 1. BUSCA INTEGRADA
        aloc_alvo = pd.DataFrame()
        if not df_spx.empty and id_busca in df_spx['order_id'].astype(str).values:
            aloc_alvo = df_spx[df_spx['order_id'].astype(str) == id_busca]
        elif not df_cluster.empty and id_busca in df_cluster['order_id'].astype(str).values:
            aloc_alvo = df_cluster[df_cluster['order_id'].astype(str) == id_busca]

        if not aloc_alvo.empty:
            p_lat, p_lon = aloc_alvo['latitude'].iloc[0], aloc_alvo['longitude'].iloc[0]
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').drop_duplicates(subset=['corridor_cage']).head(3)

            # --- 🚀 LÓGICA DE SELEÇÃO DINÂMICA ---
            if 'selecao_index' not in st.session_state:
                st.session_state.selecao_index = 0

            row_selecionada = sugestoes.iloc[st.session_state.selecao_index]

            # --- 🖼️ LAYOUT DE DUAS COLUNAS (SOLICITADO) ---
            c1, c2 = st.columns([1, 1.2])

            with c1:
                st.success(f"📍 Referência: {'Pacote' if id_busca in df_spx['order_id'].values else 'HUB'}")
                st.write("### Sugestões")
                
                for i, row in enumerate(sugestoes.itertuples()):
                    # Botão para mudar a pré-visualização
                    if st.button(f"🎯 Selecionar {row.corridor_cage} ({row.dist_km:.2f}km)", key=f"sel_{i}", use_container_width=True):
                        st.session_state.selecao_index = i
                        st.rerun()
                    
                    # Ações rápidas dentro da lista
                    with st.expander(f"⚙️ Opções para {row.corridor_cage}"):
                        pid = str(getattr(row, 'planned_at', '')).strip()
                        st.link_button("🔗 Alocar na Shopee", f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={pid}", use_container_width=True)

            with c2:
                st.write("### 📄 Pré-visualização e Impressão")
                # Detalhamento para o layout de impressão
                p = str(row_selecionada.corridor_cage).split('-')
                corredor = p[0]
                gaiola = p[1] if len(p) > 1 else "0"
                bairro = getattr(row_selecionada, 'cluster', 'PVH')
                obs = "ALOCAÇÃO IMEDIATA"

                # LAYOUT DE IMPRESSÃO PROFISSIONAL (O DETERMINANTE)
                html_label = f"""
                <style>
                    .box {{ width: 330px; height: 230px; border: 4px solid #000; font-family: Arial; background: white; margin: auto; }}
                    .header {{ background: #000; color: #fff; text-align: center; padding: 5px; font-weight: bold; font-size: 14px; }}
                    .split {{ display: flex; border-bottom: 3px solid #000; height: 110px; }}
                    .side {{ flex: 1; text-align: center; border-right: 3px solid #000; display: flex; flex-direction: column; justify-content: center; }}
                    .big {{ font-size: 65px; font-weight: bold; line-height: 0.9; color: black; }}
                    .bairro {{ background: #eee; text-align: center; padding: 8px; font-weight: bold; text-transform: uppercase; border-bottom: 2px dashed black; font-size: 16px; color: black; }}
                    .footer {{ text-align: center; padding: 5px; font-size: 10px; color: black; }}
                </style>
                <div class="box">
                    <div class="header">SPX - PORTO VELHO HUB</div>
                    <div class="split">
                        <div class="side"><div>CORREDOR</div><div class="big">{corredor}</div></div>
                        <div class="side" style="border:none;"><div>GAIOLA</div><div class="big">{gaiola}</div></div>
                    </div>
                    <div class="bairro">{bairro}</div>
                    <div class="footer"><b>{obs}</b><br>ID: {id_busca} | {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
                </div>
                """
                st.markdown(html_label, unsafe_allow_html=True)
                
                if st.button("🖨️ CONFIRMAR IMPRESSÃO", use_container_width=True, type="primary"):
                    # Dispara a impressão real
                    print_script = html_label + "<script>window.print();</script>"
                    components.html(print_script, height=0)
                    st.toast("Enviando para a Zebra...", icon="✅")
        else:
            st.error("❌ Pedido não encontrado.")

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


