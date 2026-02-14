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

# --- 2. TRADUTOR E NORMALIZADOR ---
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
    'license_plate': ['license_plate', 'placa'],
    'planned_at': ['planned_at', 'id_planejamento', 'task_id']
}

# --- 3. CARREGAMENTO COM SUPER CORREÇÃO GEOGRÁFICA ---
@st.cache_data(ttl=60)
def carregar_bases_sql():
    try:
        spx = pd.DataFrame(conn.table("base_spx").select("*").execute().data)
        cluster = pd.DataFrame(conn.table("base_cluster").select("*").execute().data)
        fleet = pd.DataFrame(conn.table("base_fleet").select("*").execute().data)
        
        df_spx = normalizar_dados(spx, SINONIMOS)
        df_cluster = normalizar_dados(cluster, SINONIMOS)
        df_fleet = normalizar_dados(fleet, SINONIMOS)

        # ⚡ CORREÇÃO MATEMÁTICA BRUTA (Resolve nan e 9999km)
        for df in [df_spx, df_cluster]:
            if not df.empty:
                for col in ['latitude', 'longitude']:
                    if col in df.columns:
                        # 1. Força tudo para string e substitui vírgulas
                        df[col] = df[col].astype(str).str.replace(',', '.')
                        # 2. Converte para numérico, transformando erros em NaN
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        # 3. Se o valor estiver multiplicado (ex: -87.0 em vez de -8.7), divide por 10
                        # Baseado na sua imagem image_f7e7be.png
                        df[col] = df[col].apply(lambda x: x/10 if pd.notna(x) and (x > 90 or x < -90 or x > 180 or x < -180) else x)
        
        return df_spx, df_cluster, df_fleet
    except:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_spx, df_cluster, df_fleet_base = carregar_bases_sql()

# --- 4. FUNÇÕES DE APOIO ---
def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        if any(pd.isna([lat1, lon1, lat2, lon2])): return 9999
        # Validação extra para garantir que são floats válidos
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        r = 6371 
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
        a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
        return 2 * r * np.arcsin(np.sqrt(a))
    except: return 9999

# --- 5. INTERFACE ---
tab1, tab2 = st.tabs(["🎯 Alocador", "🚚 Fleet Control"])

with tab1:
    id_busca = st.text_input("🔎 Bipar Pedido (Order ID):", key="search_input").strip()
    if id_busca:
        pacote = df_spx[df_spx['order_id'].astype(str) == id_busca] if not df_spx.empty else pd.DataFrame()
        if not pacote.empty:
            p_lat, p_lon = pacote['latitude'].iloc[0], pacote['longitude'].iloc[0]
            st.success(f"📦 Pedido Localizado! Coordenadas Corrigidas: {p_lat}, {p_lon}")
            
            df_cluster['dist_km'] = df_cluster.apply(lambda x: calcular_distancia(p_lat, p_lon, x['latitude'], x['longitude']), axis=1)
            sugestoes = df_cluster.sort_values('dist_km').head(3)
            
            cols = st.columns(3)
            for i, row in enumerate(sugestoes.itertuples()):
                with cols[i]:
                    st.markdown(f"""
                    <div style="background:#1e1e1e; padding:20px; border-radius:15px; border: 2px solid #ff4b4b; text-align:center; margin-bottom:10px">
                        <h1 style="color:white; margin:0; font-size:45px">{row.corridor_cage}</h1>
                        <p style="color:#ff4b4b; font-weight:bold; margin:0">{row.dist_km:.2f} km</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    id_shopee = getattr(row, 'planned_at', '')
                    st.link_button("📥 Alocar", f"https://spx.shopee.com.br/#/assignment-task/detailNoLabel?id={id_shopee}", use_container_width=True)
                    if st.button(f"🖨️ Imprimir", key=f"prt_{i}", use_container_width=True):
                        st.toast(f"Imprimindo {row.corridor_cage}...", icon="🖨️")
        else:
            st.error("Pedido não encontrado na base SPX.")

with tab2:
    st.write("### 📥 Registro de Movimentação")
    col_in, col_card = st.columns([1, 1.2])
    with col_in:
        # Usa o on_change para processar o bip apenas uma vez (Trava Anti-Loop)
        d_id = st.text_input("🆔 Bipar Driver ID:", key="f_scan_input").strip()
    
    if d_id and not df_fleet_base.empty:
        # Prevenção de loop: verifica se já processamos este ID nesta sessão
        if "last_bip" not in st.session_state or st.session_state.last_bip != d_id:
            match = df_fleet_base[df_fleet_base['driver_id'].astype(str) == d_id]
            if not match.empty:
                nome, placa = match['driver_name'].values[0], match['license_plate'].values[0]
                
                # Renderiza a placa Mercosul
                with col_card:
                    st.markdown(f"""
                    <div style="width:280px; background:white; border-radius:10px; border: 4px solid #003399; box-shadow: 2px 2px 10px rgba(0,0,0,0.3)">
                        <div style="background:#003399; color:white; font-size:10px; font-weight:bold; padding:2px 10px; display:flex; justify-content:space-between">
                            <span>BRASIL</span>
                            <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Flag_of_Brazil.svg/200px-Flag_of_Brazil.svg.png" width="15">
                        </div>
                        <div style="text-align:center; padding:10px">
                            <h1 style="color:black; font-family:serif; font-size:50px; margin:0; letter-spacing:4px">{placa}</h1>
                        </div>
                    </div>
                    <h3 style="margin-top:10px">{nome}</h3>
                    """, unsafe_allow_html=True)

                # Lógica de Registro Único
                aberto = conn.table("log_fleet").select("*").eq("driver_id", d_id).is_("saida", "null").execute()
                if aberto.data:
                    conn.table("log_fleet").update({"saida": datetime.now().isoformat(), "tempo_hub": "Calc..."}).eq("id", aberto.data[0]['id']).execute()
                    st.toast(f"🏁 Saída Registrada para {nome}!", icon="🏁")
                else:
                    conn.table("log_fleet").insert({"driver_id": d_id, "nome": nome, "placa": placa, "data": hoje_str}).execute()
                    st.toast(f"📥 Entrada Registrada para {nome}!", icon="📥")
                
                st.session_state.last_bip = d_id # Marca como processado
                time.sleep(1)
                st.rerun()
            else:
                st.error("Motorista não cadastrado.")
    elif not d_id:
        st.session_state.last_bip = None # Reseta quando o campo limpa

    # Tabela de Histórico fixa com refresh
    st.divider()
    logs_res = conn.table("log_fleet").select("*").eq("data", hoje_str).order("entrada", desc=True).execute()
    if logs_res.data:
        st.dataframe(pd.DataFrame(logs_res.data)[['nome', 'placa', 'entrada', 'tempo_hub']], use_container_width=True)
