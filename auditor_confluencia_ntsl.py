import pandas as pd
import numpy as np
import re
import unicodedata

def norm(txt):
    t = unicodedata.normalize('NFKD', str(txt))
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]', '', t.lower())

def num_br(serie):
    def conv(x):
        x = str(x).strip().replace('\u00a0', '')
        if x in ('', 'nan', 'None', '-', '<NA>'): return np.nan
        if ',' in x: x = x.replace('.', '').replace(',', '.')
        elif '.' in x:
            partes = x.split('.')
            if len(partes) >= 2 and len(partes[-1]) == 3: x = x.replace('.', '')
        try: return float(x)
        except ValueError: return np.nan
    return serie.map(conv).astype(float)

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def analisar_confluencia(arquivo_csv):
    print(f"[CENTURIO] Lendo dados de: {arquivo_csv}")
    
    try:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
    except FileNotFoundError:
        print(f"[ERRO] Arquivo {arquivo_csv} não encontrado.")
        return

    if 'Data' not in df.columns and 'data' not in df.columns:
        if re.match(r'\d{2}/\d{2}/\d{4}', str(df.columns[1])):
            nomes_padrao = ['Ativo', 'Data', 'Hora', 'Abertura', 'Maximo', 'Minimo', 'Fechamento', 'Volume', 'Quantidade']
            df.columns = nomes_padrao[:len(df.columns)]
    
    colunas_norm = {norm(c): c for c in df.columns}
    col_open, col_high = colunas_norm.get('abertura'), colunas_norm.get('maximo')
    col_low, col_close = colunas_norm.get('minimo'), colunas_norm.get('fechamento')
    col_data, col_hora = colunas_norm.get('data'), colunas_norm.get('hora')

    df = df.rename(columns={col_open: 'Abertura', col_high: 'Maximo', col_low: 'Minimo', col_close: 'Fechamento'})
    df['dt'] = pd.to_datetime(df[col_data].astype(str) + ' ' + df[col_hora].astype(str), dayfirst=True, errors='coerce')
    df = df.dropna(subset=['dt']).sort_values('dt').reset_index(drop=True)
    for col in ['Abertura', 'Maximo', 'Minimo', 'Fechamento']: df[col] = num_br(df[col])
    
    # 1. CALCULAR INDICADORES NO ARQUIVO INTEIRO (AQUECIMENTO)
    lowest_low = df['Minimo'].rolling(window=55).min()
    highest_high = df['Maximo'].rolling(window=55).max()
    denominador = (highest_high - lowest_low).replace(0, np.nan)
    
    estoc_rapido = ((df['Fechamento'] - lowest_low) / denominador) * 100
    lento21 = ema(estoc_rapido, 21)
    sinal5 = ema(lento21, 5)

    delta = df['Fechamento'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=13).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=13).mean()
    rs = gain / loss.replace(0, np.nan)
    valor_ifr = 100 - (100 / (1 + rs))
    
    ema13_ifr = ema(valor_ifr, 13)
    ema34_ifr = ema(valor_ifr, 34)

    df['lento21'] = lento21
    df['valor_ifr'] = valor_ifr
    df['Estoc_Comprado'] = df['lento21'] > sinal5
    df['Estoc_Vendido'] = df['lento21'] < sinal5
    df['IFR_Comprado'] = (df['valor_ifr'] > 50) & (ema13_ifr > ema34_ifr)
    df['IFR_Vendido'] = (df['valor_ifr'] < 50) & (ema13_ifr < ema34_ifr)

    def obter_cor(row):
        if pd.isna(row['lento21']) or pd.isna(row['valor_ifr']): return 'BRANCO' 
        if row['Estoc_Comprado'] and row['IFR_Comprado']: return 'VERDE'
        elif row['Estoc_Vendido'] and row['IFR_Vendido']: return 'VERMELHO'
        else: return 'BRANCO'

    df['Cor'] = df.apply(obter_cor, axis=1)

    # 2. FILTRAR APENAS O DIA DE HOJE PARA MEDIR OS SINAIS
    dia_foco = df['dt'].dt.date.max()
    df_dia = df[df['dt'].dt.date == dia_foco].reset_index(drop=True)
    print(f"[CENTURIO] Medindo sinais do pregão de: {dia_foco} ({len(df_dia)} candles)")

    sinais = []
    for i in range(1, len(df_dia)):
        cor_atual, cor_anterior = df_dia['Cor'].iloc[i], df_dia['Cor'].iloc[i-1]
        
        if cor_anterior == 'BRANCO' and cor_atual in ['VERDE', 'VERMELHO']:
            direcao = 1 if cor_atual == 'VERDE' else -1
            preco_entrada = df_dia['Fechamento'].iloc[i]
            max_favor = 0
            
            for j in range(i+1, len(df_dia)):
                if direcao == 1: excursao = df_dia['Maximo'].iloc[j] - preco_entrada
                else: excursao = preco_entrada - df_dia['Minimo'].iloc[j]
                if excursao > max_favor: max_favor = excursao
                if df_dia['Cor'].iloc[j] == ('VERMELHO' if direcao == 1 else 'VERDE'): break
            
            sinais.append({'Hora': df_dia['dt'].iloc[i].strftime('%H:%M'), 'Tipo': cor_atual, 'Preco': preco_entrada, 'Max_Favor': max_favor})

    df_sinais = pd.DataFrame(sinais)
    
    print("\n" + "="*60)
    if df_sinais.empty:
        print("Nenhum sinal encontrado (Verifique se o CSV tem dados suficientes para o aquecimento dos indicadores).")
        return

    print(df_sinais.to_string(index=False))
    vendas, compras = df_sinais[df_sinais['Tipo'] == 'VERMELHO'], df_sinais[df_sinais['Tipo'] == 'VERDE']

    print("\n" + "-"*60)
    if not compras.empty:
        print(f"[COMPRAS - VERDE] Média: {compras['Max_Favor'].mean():.1f} pts | Pior: {compras['Max_Favor'].min():.1f} | <100 pts: {len(compras[compras['Max_Favor'] < 100])} de {len(compras)}")
    if not vendas.empty:
        print(f"[VENDAS - VERMELHO] Média: {vendas['Max_Favor'].mean():.1f} pts | Pior: {vendas['Max_Favor'].min():.1f} | <100 pts: {len(vendas[vendas['Max_Favor'] < 100])} de {len(vendas)}")

if __name__ == "__main__":
    analisar_confluencia('win_hoje.csv')        