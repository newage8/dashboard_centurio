import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 1. Configuração do Painel Institucional
st.set_page_config(page_title="CENTURIO | Tubasa Labs", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
    <style>
    .reportview-container {background: #0E1117;}
    .main {background-color: #0E1117;}
    h1, h2, h3, p {color: #00FF00;} /* Verde Tubasa */
    </style>
    """, unsafe_allow_html=True)

st.title("CENTURIO • INTELLIGENCE DASHBOARD")
st.markdown("---")

# 2. VITIS: Aprendizado e Auditoria Pós-Mercado
st.subheader("🛡️ VITIS | Auditoria e Gestão de Risco Pós-Operacional")
caminho_csv = r"C:\Tubasa_Labs\data_profit\NewAgeTubasaLabSafe01.csv"

try:
    df = pd.read_csv(caminho_csv, encoding='iso-8859-1', sep=';', skiprows=5)
    df['Lucro_Prejuizo'] = df['Res. Operação'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)
    df['Patrimonio'] = df['Lucro_Prejuizo'].cumsum()
    
    col1, col2, col3, col4 = st.columns(4)
    total_trades = len(df)
    win_rate = (len(df[df['Lucro_Prejuizo'] > 0]) / total_trades) * 100 if total_trades > 0 else 0
    lucro_liq = df['Lucro_Prejuizo'].sum()
    lucro_bruto = df[df['Lucro_Prejuizo'] > 0]['Lucro_Prejuizo'].sum()
    prejuizo_bruto = abs(df[df['Lucro_Prejuizo'] < 0]['Lucro_Prejuizo'].sum())
    profit_factor = lucro_bruto / prejuizo_bruto if prejuizo_bruto > 0 else 0

    col1.metric("Resultado Líquido (WIN)", f"R$ {lucro_liq:.2f}")
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Fator de Lucro", f"{profit_factor:.2f}")
    col4.metric("Operações Auditadas", f"{total_trades}")

    # Gráfico de Evolução (Vitis)
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=df['Patrimonio'], mode='lines', name='Capital', line=dict(color='#00FF00', width=2), fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.1)'))
    fig.update_layout(title="Curva de Patrimônio (Estado de Presença)", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
    st.plotly_chart(fig, use_container_width=True)

except FileNotFoundError:
    st.error("Vitis informa: Arquivo de histórico não localizado na base de dados.")

st.markdown("---")

# 3. A.I.A.: A Ninfa dos Dados (Módulo de Caça)
st.subheader("🌐 A.I.A. | High-Frequency News & Sentiment (Em Ativação)")
st.info("A Ninfa está rastreando o oceano macroeconômico. Integração do Calendário de Notícias Globais em andamento para bloqueio de operações de Mesa Proprietária.")