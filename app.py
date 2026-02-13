import streamlit as st
import pandas as pd
import re

# Configuração da página
st.set_page_config(page_title="Roteirizador SPX", layout="wide")

st.title("🔗 Integração Direta - Google Sheets")
st.markdown("Insira o link da sua planilha para cruzar a **Base SPX** com a **Base Cluster**.")

# 1. Campo para o Link na Barra Lateral
with st.sidebar:
    st.header("Configurações de Dados")
    sheet_url = st.text_input("Cole aqui a URL da Planilha Google:")
    
    st.info("💡 Certifique-se de que a planilha está compartilhada como 'Qualquer pessoa com o link'.")

# Função para converter link comum em link de exportação CSV para o Pandas
def get_csv_url(url):
    try:
        sheet_id = re.search(r"/d/(.*?)/", url).group(1)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    except:
        return None

if sheet_url:
    csv_url = get_csv_url(sheet_url)
    
    if csv_url:
        try:
            # Aqui assumimos que temos as abas ou arquivos carregados
            # Para múltiplas abas via URL, o ideal é usar o GID da aba
            st.success("Conexão estabelecida!")
            
            # Simulando o carregamento (No caso real, leríamos as duas abas)
            # df_spx = pd.read_csv(csv_url + "&gid=ID_DA_ABA_SPX")
            # df_cluster = pd.read_csv(csv_url + "&gid=ID_DA_ABA_CLUSTER")
            
            st.warning("Aguardando processamento do cruzamento: Coluna A (SPX) ↔ Coluna G (Cluster)")
            
        except Exception as e:
            st.error(f"Erro ao ler a planilha: {e}")
    else:
        st.error("URL inválida. Por favor, verifique o link.")

# 2. Área de Visualização da Interface
st.divider()
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📦 Base SPX (Pacotes no HUB)")
    st.caption("Foco na Coluna A: SPX TN")
    # st.dataframe(df_spx) 

with col2:
    st.subheader("🗺️ Base Cluster (Referência)")
    st.caption("Foco na Coluna G: SPX TN")
    # st.dataframe(df_cluster)