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

# --- 2. NORMALIZADOR DE DADOS ---
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
    'order_id': ['order_id', 'pedido', 'id', 'rastreio', 'corridor_cage', 'gaiola'],
    'latitude': ['latitude', 'lat', 'y'],
    'longitude': ['longitude', 'long', 'x', 'lng'],
    'corridor_cage': ['corridor_cage', 'gaiola', 'cluster', 'setor'],
    'driver_id': ['driver_id', 'id_motorista', 'cpf'],
    'driver_name': ['driver_name', 'nome', 'motorista'],
    'license_plate': ['license_plate', 'placa'],
    'planned_at': ['planned_at', 'id_planejamento', 'task_id']
}

# --- 3. CARREGAMENTO COM CORREÇÃO GEOGRÁFICA ---
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
                        # Correção de escala baseada na imagem f7e7be.png
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
    id_busca = st.text_input("🔎 Bipar Pedido ou Gaiola:", key="input_aloc").strip()
    if id_busca:
        # BUSCA INTEGRADA: Tenta achar no SPX ou no CLUSTER
        aloc_alvo = pd.DataFrame()
        if not df_spx.empty and id_busca in df_spx['order_id'].astype(str).values:
            aloc_alvo = df_spx[df_spx['order_id'].astype(str) == id_busca]
            st.success(f"📦 Pedido Localizado na Base SPX")
        elif not df_cluster.empty and id_busca in df_cluster['corridor_cage'].astype(str).values:
            aloc_alvo = df_cluster[df_cluster['corridor_cage'].astype(str) == id_busca]
            st.info(f"📍 Ponto Localizado na Base Cluster")

        if not aloc_alvo.empty:
            p_lat, p_lon = aloc_alvo['latitude'].iloc[0], aloc_alvo['longitude'].iloc[0]
            
            # Cruzamento Geográfico
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').head(3)
            
            cols = st.columns(3)
            for i, row in enumerate(sugestoes.itertuples()):
                with cols[i]:
                    st.markdown(f"""
                    <div style="background:#1e1e1e; padding:15px; border-radius:10px; border: 2px solid #ff4b4b; text-align:center">
                        <h2 style="color:white; margin:0">{row.corridor_cage}</h2>
                        <p style="color:#ff4b4b; font-weight:bold; margin:0">{row.dist_km:.2f} km</p>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("📥 Alocar", f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={getattr(row, 'planned_at', '')}", use_container_width=True)
                    if st.button(f"🖨️ Imprimir", key=f"print_{i}", use_container_width=True):
                        st.toast("Impressora acionada!")
        else:
            st.error("❌ ID não encontrado em nenhuma das bases.")

with tab2:
    st.write("### 📥 Registro de Movimentação")
    c_in, c_placa = st.columns([1, 1.2])
    with c_in:
        d_id = st.text_input("🆔 Bipar Driver ID:", key="fleet_scan_fix").strip()
    
    # TRAVA DE SEGURANÇA: Só processa se o valor mudar ou for o primeiro bip
    if d_id and st.session_state.get('last_bip') != d_id:
        match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id] if not df_fleet_base.empty else pd.DataFrame()
        if not match.empty:
            nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
            
            with c_placa:
                st.markdown(f"""
                <div style="width:250px; background:white; border-radius:10px; border: 5px solid #003399; text-align:center">
                    <div style="background:#003399; color:white; font-size:10px; padding:2px">BRASIL</div>
                    <h1 style="color:black; font-family:serif; font-size:45px; margin:0; letter-spacing:3px">{placa}</h1>
                </div>
                <h3>{nome}</h3>
                """, unsafe_allow_html=True)

            # Lógica de Registro Único
            aberto = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
            if aberto.data:
                conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": "Check"}).eq("id", aberto.data[0]['id']).execute()
                st.toast(f"🏁 SAÍDA: {nome}", icon="🏁")
            else:
                conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                st.toast(f"📥 ENTRADA: {nome}", icon="📥")
            
            st.session_state.last_bip = d_id
            time.sleep(1.5)
            st.rerun()
    elif not d_id:
        st.session_state.last_bip = None

    st.divider()
    logs = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
    if logs.data:
        st.dataframe(pd.DataFrame(logs.data)[['nome', 'placa', 'entrada', 'tempo_hub']], use_container_width=True)
