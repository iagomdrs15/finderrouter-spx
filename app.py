import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time
from st_supabase_connection import SupabaseConnection
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# --- 1. CONFIGURAÇÕES E CONEXÃO ---
st.set_page_config(page_title="Alocador SPX Pro SQL", layout="wide", page_icon="🚀")
conn = st.connection("supabase", type=SupabaseConnection)

# Atualização estável de 30 segundos
st_autorefresh(interval=30000, key="ops_pulse_stable")

HUB_LAT, HUB_LON = -8.791172513071563, -63.847713631142135
hoje_str = datetime.now().strftime("%d/%m/%Y")

# --- 2. TRADUTOR DE COLUNAS ---
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

# --- 3. CARREGAMENTO ---
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

# --- 4. OPS CLOCK ---
if 'ops_clock_running' not in st.session_state: st.session_state.ops_clock_running = False
if 'ops_start_time' not in st.session_state: st.session_state.ops_start_time = None

st.markdown("""
    <style>
    .ops-clock-container { background: #1e1e1e; padding: 10px; border-radius: 10px; border-left: 5px solid #ff4b4b; text-align: center; }
    .ops-time { font-family: 'Courier New', Courier, monospace; font-size: 32px; font-weight: bold; color: #ff4b4b; }
    .fleet-card { padding: 8px; border-radius: 8px; color: white; text-align: center; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.3); }
    </style>
""", unsafe_allow_html=True)

c_clock, c_clock_btn = st.columns([3, 1])
tempo_exibicao = "00:00"

if st.session_state.ops_clock_running and st.session_state.ops_start_time:
    decorrido = datetime.now() - st.session_state.ops_start_time
    h, r = divmod(decorrido.total_seconds(), 3600)
    m, _ = divmod(r, 60)
    tempo_exibicao = f"{int(h):02d}:{int(m):02d}"

with c_clock:
    st.markdown(f'<div class="ops-clock-container"><span style="color:gray; font-size:10px;">OPERATIONS COMMAND</span><br><span class="ops-time">{tempo_exibicao}</span></div>', unsafe_allow_html=True)

with c_clock_btn:
    if st.session_state.ops_clock_running:
        if st.button("🛑 PARAR OPS", use_container_width=True, type="primary"):
            conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "status": "Finalizado via Master Stop"}).is_("saida", "null").eq("data", hoje_str).execute()
            st.session_state.ops_clock_running = False
            st.session_state.ops_start_time = None
            st.rerun()
    else:
        if st.button("🚀 INICIAR OPS", use_container_width=True):
            st.session_state.ops_clock_running = True
            st.session_state.ops_start_time = datetime.now()
            st.rerun()

# --- 5. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador", "🚚 Fleet Control"])

with tab1:
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID / SPX_TN):", key="aloc_v7_final").strip()
    if id_busca:
        # 1. BUSCA INTELIGENTE: Cluster como prioridade para erros de separação
        aloc_alvo = pd.DataFrame()
        
        # Primeiro, verificamos se o ID já existe no Cluster (Indica re-alocação ou erro de triagem)
        if not df_cluster.empty and id_busca in df_cluster['order_id'].astype(str).values:
            aloc_alvo = df_cluster[df_cluster['order_id'].astype(str) == id_busca]
            st.warning("⚠️ Erro de Separação Detectado: ID localizado diretamente no Cluster.")
        
        # Se não estiver no cluster, buscamos no SPX
        elif not df_spx.empty and id_busca in df_spx['order_id'].astype(str).values:
            aloc_alvo = df_spx[df_spx['order_id'].astype(str) == id_busca]
            st.success("📦 Pedido Localizado no SPX.")

        if not aloc_alvo.empty:
            p_lat, p_lon = aloc_alvo['latitude'].iloc[0], aloc_alvo['longitude'].iloc[0]
            
            # 2. FILTRAGEM DINÂMICA: Apenas rotas de motoristas ATIVOS no pátio
            logs_ativos = conn.table("log_fleet").select("placa").eq("data", hoje_str).is_("saida", "null").execute()
            placas_no_patio = [r['placa'] for r in logs_ativos.data] if logs_ativos.data else []
            
            # Calculamos distância para todos
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            
            # Filtramos o cluster: Somente se a placa estiver no pátio OU se não houver ninguém (para não travar)
            if placas_no_patio:
                df_sugestao = df_cluster[df_cluster['license_plate'].isin(placas_no_patio)]
                # Se não houver correspondência exata no pátio, voltamos ao cluster geral para não deixar o pacote sem destino
                if df_sugestao.empty: df_sugestao = df_cluster
            else:
                df_sugestao = df_cluster

            sugestoes = df_sugestao.sort_values('dist_km').drop_duplicates(subset=['corridor_cage']).head(3)

            if 'selecao_index' not in st.session_state: st.session_state.selecao_index = 0
            row_sel = sugestoes.iloc[st.session_state.selecao_index]

            c1, c2 = st.columns([1, 1.2])
            with c1:
                st.write("### Sugestões Ativas")
                for i, row in enumerate(sugestoes.itertuples()):
                    status_patio = "🚚 No Pátio" if row.license_plate in placas_no_patio else "⚪ Geral"
                    if st.button(f"🎯 {row.corridor_cage} ({row.dist_km:.2f}km) - {status_patio}", key=f"sel_{i}", use_container_width=True):
                        st.session_state.selecao_index = i
                        st.rerun()

            with c2:
                # Layout de Impressão
                p = str(row_sel.corridor_cage).split('-')
                corredor, gaiola = p[0], p[1] if len(p) > 1 else "0"
                html_label = f"""
                <div style="width:330px; height:230px; border:4px solid #000; font-family:Arial; background:white; margin:auto; color:black;">
                    <div style="background:#000; color:#fff; text-align:center; padding:5px; font-weight:bold; font-size:14px;">SPX - PORTO VELHO HUB</div>
                    <div style="display:flex; border-bottom:3px solid #000; height:110px;">
                        <div style="flex:1; text-align:center; border-right:3px solid #000; display:flex; flex-direction:column; justify-content:center;"><div>CORREDOR</div><div style="font-size:65px; font-weight:bold;">{corredor}</div></div>
                        <div style="flex:1; text-align:center; display:flex; flex-direction:column; justify-content:center;"><div>GAIOLA</div><div style="font-size:65px; font-weight:bold;">{gaiola}</div></div>
                    </div>
                    <div style="background:#eee; text-align:center; padding:8px; font-weight:bold; text-transform:uppercase; border-bottom:2px dashed black; font-size:16px;">{getattr(row_sel, 'cluster', 'PVH')}</div>
                    <div style="text-align:center; padding:5px; font-size:10px;"><b>ALOCAÇÃO INTELIGENTE</b><br>ID: {id_busca} | {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
                </div>"""
                st.markdown(html_label, unsafe_allow_html=True)
                if st.button("🖨️ CONFIRMAR IMPRESSÃO", use_container_width=True, type="primary"):
                    components.html(html_label + "<script>window.onload = function() { window.print(); };</script>", height=0)
                    st.toast("Etiqueta de Re-alocação Gerada!", icon="✅")
        else: st.error("❌ ID não encontrado em nenhuma base.")

with tab2:
    st.write("### 🚚 Registro de Pátio (Anti-Loop)")
    if "input_key" not in st.session_state: st.session_state.input_key = 0
    d_id = st.text_input("🆔 Bipar Driver ID:", key=f"fleet_input_{st.session_state.input_key}", value="").strip()

    if d_id:
        match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id] if not df_fleet_base.empty else pd.DataFrame()
        if not match.empty:
            nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
            aberto = conn.table("log_fleet").select("*").eq("driver_id", str(d_id)).is_("saida", "null").eq("data", hoje_str).execute()
            
            if aberto.data:
                ent = datetime.fromisoformat(aberto.data[0]['entrada'].replace('Z', '+00:00'))
                tempo_txt = f"{int((datetime.now().astimezone() - ent).total_seconds() // 60)} min"
                conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "status": "Finalizado", "tempo_hub": tempo_txt}).eq("id", aberto.data[0]['id']).execute()
            else:
                conn.table("log_fleet").insert({"driver_id": str(d_id), "nome": nome, "placa": placa, "data": hoje_str, "status": "Em Carregamento", "entrada": datetime.now().isoformat()}).execute()
                if not st.session_state.ops_clock_running:
                    st.session_state.ops_clock_running, st.session_state.ops_start_time = True, datetime.now()
            
            st.session_state.input_key += 1
            time.sleep(0.5)
            st.rerun()
        else: st.error("Driver não cadastrado.")

    st.divider()
    logs_live = conn.table("log_fleet").select("*").eq("data", hoje_str).is_("saida", "null").execute()
    if logs_live.data:
        cols_mon = st.columns(4)
        for i, row in enumerate(pd.DataFrame(logs_live.data).itertuples()):
            minutos = int((datetime.now().astimezone() - datetime.fromisoformat(row.entrada.replace('Z', '+00:00'))).total_seconds() / 60)
            cor = "#28a745" if minutos <= 10 else "#ffc107" if minutos <= 15 else "#dc3545"
            with cols_mon[i % 4]:
                st.markdown(f'<div class="fleet-card" style="background:{cor};"><p style="margin:0; font-weight:bold;">{row.placa}</p><p style="font-size:10px; margin:0;">{row.nome[:15]}</p><h2 style="margin:0;">{minutos}m</h2></div>', unsafe_allow_html=True)
    else: st.info("Pátio vazio.")
