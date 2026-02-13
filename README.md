# 🚀 Alocador SPX Pro - HUB Porto Velho

Sistema inteligente para otimização de alocação de pacotes e gestão de SLA de carregamento (Fleet) desenvolvido para a operação do HUB SPX em Porto Velho.

## 🎯 Funcionalidades Principais

* **Alocador de Pacotes:** Identifica a gaiola/corredor mais próximo baseado na geolocalização do pacote ou do HUB.
* **Impressão de Etiquetas:** Geração instantânea de etiquetas térmicas (70mm x 50mm) para identificação de gaiolas.
* **Gestão de Fleet (SLA):** Controle de entrada e saída de veículos com monitoramento de tempo de permanência no HUB.
* **Indicadores Visuais (SLA):** * 🟢 **Verde:** Até 10 min (Operação ideal).
    * 🟡 **Amarelo:** 11 a 14 min (Atenção).
    * 🔴 **Vermelho:** Acima de 15 min (Crítico).

## 🛠️ Tecnologias Utilizadas

* [Streamlit](https://streamlit.io/) - Framework para interface web.
* [Pandas](https://pandas.pydata.org/) - Manipulação e análise de dados.
* [Google Sheets API](https://developers.google.com/sheets/api) - Como base de dados dinâmica para consulta.
* [CSV Local](https://docs.python.org/3/library/csv.html) - Persistência de logs para contingência e velocidade.

## 🚀 Como Executar o Projeto

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/SEU_USUARIO/NOME_DO_REPOSITORIO.git](https://github.com/SEU_USUARIO/NOME_DO_REPOSITORIO.git)
