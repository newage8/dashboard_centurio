import pandas as pd
import numpy as np

def simular_estrategia_ntsl():
    arquivo = "historico_26_03.csv"
    
    print(f"[CENTURIO] Carregando dados: {arquivo}")
    try:
        # Lê pulando o cabeçalho, pois o print do Excel mostra que há um cabeçalho.
        df = pd.read_csv(arquivo, header=None, skiprows=1)
    except FileNotFoundError:
        print(f"[ERRO] Arquivo {arquivo} não encontrado na pasta.")
        return

    # O print mostra as colunas: 0=Data, 1=Open, 2=High, 3=Low, 4=Close
    # Vamos renomear para garantir a consistência independente do idioma
    df = df[[0, 1, 2, 3, 4]].copy()
    df.columns = ['Data', 'Open', 'High', 'Low', 'Close']
    
    # Converte numérico para garantir
    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # --- MOTOR 1: ESTOCÁSTICO LENTO (55, 1) ---
    periodo = 55
    lowest_low = df['Low'].rolling(window=periodo).min()
    highest_high = df['High'].rolling(window=periodo).max()
    
    # Estocástico puro
    estoc_rapido = 100 * (df['Close'] - lowest_low) / (highest_high - lowest_low)
    lento21 = estoc_rapido.ewm(span=21, adjust=False).mean()
    sinal5 = lento21.ewm(span=5, adjust=False).mean()

    # --- MOTOR 2: IDENTIFICAÇÃO DE REVERSAL PURO ---
    # Condição de estar verde ou vermelho
    condicao_verde = lento21 > sinal5
    condicao_vermelho = lento21 < sinal5
    
    # Sinal de reversão ocorre quando muda o estado
    df['Sinal'] = 0
    df.loc[condicao_verde & (lento21.shift(1) <= sinal5.shift(1)), 'Sinal'] = 1  # 1 = Compra
    df.loc[condicao_vermelho & (lento21.shift(1) >= sinal5.shift(1)), 'Sinal'] = -1 # -1 = Venda

    # --- MOTOR 3: BACKTEST COM GESTÃO DINÂMICA ---
    trades = []
    
    # Ignorar os primeiros candles para o estocástico ter janela (warm-up)
    for i in range(periodo, len(df)-1):
        sinal = df.loc[i, 'Sinal']
        
        if sinal != 0:
            data_hora = df.loc[i, 'Data']
            direcao = 'COMPRA' if sinal == 1 else 'VENDA'
            entrada = df.loc[i, 'Close']
            
            # Definição de Risco Inicial
            if direcao == 'COMPRA':
                stop_inicial = df.loc[i, 'Low']
                alvo1 = entrada + 65
                range_candle = df.loc[i, 'High'] - df.loc[i, 'Low']
                alvo2 = entrada + range_candle
            else:
                stop_inicial = df.loc[i, 'High']
                alvo1 = entrada - 65
                range_candle = df.loc[i, 'High'] - df.loc[i, 'Low']
                alvo2 = entrada - range_candle
                
            # Variáveis de controle do trade
            stop_dinamico = None
            alvo1_atingido = False
            resultado_final = "ABERTO"
            pnl_trade = 0
            
            # Varre os candles subsequentes
            for j in range(i+1, len(df)):
                high_atual = df.loc[j, 'High']
                low_atual = df.loc[j, 'Low']
                
                # 1. Verifica se bateu o Stop Inicial (Antes do Alvo 1)
                if not alvo1_atingido:
                    if direcao == 'COMPRA' and low_atual <= stop_inicial:
                        resultado_final = "LOSS INICIAL"
                        pnl_trade = - (entrada - stop_inicial) * 2 # 2 contratos
                        break
                    elif direcao == 'VENDA' and high_atual >= stop_inicial:
                        resultado_final = "LOSS INICIAL"
                        pnl_trade = - (stop_inicial - entrada) * 2 # 2 contratos
                        break
                        
                    # 2. Verifica se bateu o Alvo 1 (Parcial de 65 pts)
                    if direcao == 'COMPRA' and high_atual >= alvo1:
                        alvo1_atingido = True
                        stop_dinamico = entrada - 65
                    elif direcao == 'VENDA' and low_atual <= alvo1:
                        alvo1_atingido = True
                        stop_dinamico = entrada + 65
                
                # 3. Se o Alvo 1 foi atingido, verifica o Stop Dinâmico e o Alvo 2
                if alvo1_atingido:
                    # Verifica se bateu o Alvo 2 primeiro (para pegar o máximo de tendência)
                    if direcao == 'COMPRA' and high_atual >= alvo2:
                        resultado_final = "GAIN TOTAL (Alvo 2)"
                        pnl_trade = 65 + (alvo2 - entrada) # 1 contrato no alvo1 + 1 contrato no alvo2
                        break
                    elif direcao == 'VENDA' and low_atual <= alvo2:
                        resultado_final = "GAIN TOTAL (Alvo 2)"
                        pnl_trade = 65 + (entrada - alvo2)
                        break
                        
                    # Verifica o Stop Dinâmico (O "Zero a Zero" ajustado)
                    if direcao == 'COMPRA' and low_atual <= stop_dinamico:
                        resultado_final = "STOP NO ZERO A ZERO"
                        pnl_trade = 65 + (stop_dinamico - entrada) # 65 + (-65) = 0 pontos reais de dano, mas 65 garantidos da parcial
                        break
                    elif direcao == 'VENDA' and high_atual >= stop_dinamico:
                        resultado_final = "STOP NO ZERO A ZERO"
                        pnl_trade = 65 + (entrada - stop_dinamico)
                        break

            trades.append({
                'Data_Hora': data_hora,
                'Direcao': direcao,
                'Entrada': entrada,
                'Stop_Ini': stop_inicial,
                'Alvo1': alvo1,
                'Alvo2': alvo2,
                'Resultado': resultado_final,
                'PnL (pts)': pnl_trade
            })

    # --- EXIBIÇÃO ---
    print("\n" + "="*90)
    print(f"{'DATA / HORA':<18} | {'DIR':<7} | {'ENTRADA':<9} | {'STOP':<9} | {'RESULTADO':<22} | {'PnL (pts)':<10}")
    print("-" * 90)
    
    total_trades = 0
    gains = 0
    losses = 0
    saldo = 0
    
    for t in trades:
        print(f"{t['Data_Hora']:<18} | {t['Direcao']:<7} | {t['Entrada']:<9.0f} | {t['Stop_Ini']:<9.0f} | {t['Resultado']:<22} | {t['PnL (pts)']:<10.0f}")
        total_trades += 1
        if t['PnL (pts)'] > 0: gains += 1
        elif t['PnL (pts)'] < 0: losses += 1
        saldo += t['PnL (pts)']
        
    print("="*90)
    print(f"TOTAL DE TRADES: {total_trades} | WINS: {gains} | LOSSES: {losses}")
    if total_trades > 0:
        assertividade = (gains / total_trades) * 100
        print(f"ASSERTIVIDADE: {assertividade:.1f}%")
    print(f"SALDO FINAL: {saldo:.0f} pontos (R$ {saldo * 0.20:.2f} por contrato base)")
    print("="*90)

if __name__ == "__main__":
    simular_estrategia_ntsl()