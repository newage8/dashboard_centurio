import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import timedelta

# ==============================================================================
# TUBASA LABS - CENTURIO FIBO AUDITOR + ENTROPIA INSTITUCIONAL (COMPLETO)
# AUTOR: Moisés Cubas / Cuba.i.
# ==============================================================================

def calcular_alvos_fibo(high, low, direcao):
    amplitude = high - low
    if direcao == 1: # Compra
        return {'100%': high + amplitude, '161.8%': high + amplitude * 1.618, '197%': high + amplitude * 1.97, 'stop': low}
    else: # Venda
        return {'100%': low - amplitude, '161.8%': low - amplitude * 1.618, '197%': low - amplitude * 1.97, 'stop': high}

def calcular_entropia_shannon(simbolo, time_start, time_end):
    """Mede o caos interno do candle via Order Flow (Ticks) com ajuste temporal"""
    
    # Adicionamos uma margem de segurança de tempo para alinhar o fuso do servidor MT5
    t_inicio = time_start - timedelta(seconds=2)
    t_fim = time_end + timedelta(seconds=2)
    
    ticks = mt5.copy_ticks_range(simbolo, t_inicio, t_fim, mt5.COPY_TICKS_ALL)
    
    if ticks is None or len(ticks) == 0:
        return 1.0 # Retorna entropia máxima se o vácuo persistir
    
    df_ticks = pd.DataFrame(ticks)
    if 'last' not in df_ticks.columns: 
        return 1.0

    df_ticks['diff'] = df_ticks['last'].diff()
    up = len(df_ticks[df_ticks['diff'] > 0])
    down = len(df_ticks[df_ticks['diff'] < 0])
    neutral = len(df_ticks[df_ticks['diff'] == 0])
    
    total = up + down + neutral
    if total == 0: 
        return 1.0
    
    p_up, p_down, p_neutral = up / total, down / total, neutral / total
    
    entropia = 0
    for p in [p_up, p_down, p_neutral]:
        if p > 0:
            entropia -= p * np.log2(p)
            
    return entropia

def iniciar_auditoria():
    if not mt5.initialize():
        print("ERRO: Falha ao inicializar o MetaTrader 5.")
        return

    simbolo = "WIN$N"
    rates = mt5.copy_rates_from_pos(simbolo, mt5.TIMEFRAME_M5, 0, 300)
    
    if rates is None or len(rates) == 0:
        print("ERRO: Sem dados disponíveis para o Mini Índice.")
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    print("\n=== CENTURIO: AUDITORIA DE ENTROPIA E FIBONACCI ===")
    print(f"Ativo: {simbolo} | M5 | Varrendo fluxo e ticks internos...")
    
    resultados = []

    for i in range(1, len(df) - 1):
        c_atual, c_prev = df.iloc[i], df.iloc[i-1]
        meio_prev = (c_prev['high'] + c_prev['low']) / 2
        sinal = 0
        
        # Filtro Tubasa (Quebra 50% vs Engolfo 100%)
        if c_atual['close'] > c_prev['high'] and c_atual['close'] > c_atual['open']: 
            sinal = 2
        elif c_atual['close'] < c_prev['low'] and c_atual['close'] < c_atual['open']: 
            sinal = -2
        elif c_atual['close'] > meio_prev and c_atual['close'] > c_atual['open']: 
            sinal = 1
        elif c_atual['close'] < meio_prev and c_atual['close'] < c_atual['open']: 
            sinal = -1
            
        if sinal != 0:
            # 1. Calcular Entropia Interna do Candle com base nos Ticks
            time_start = c_atual['time']
            time_end = time_start + timedelta(minutes=5)
            entropia = calcular_entropia_shannon(simbolo, time_start, time_end)
            
            # 2. Projetar Fibo e Auditar Futuro (Alvos vs Stops)
            alvos = calcular_alvos_fibo(c_atual['high'], c_atual['low'], 1 if sinal > 0 else -1)
            hit_100 = hit_161 = hit_197 = stop_hit = False
            
            for j in range(i + 1, min(i + 25, len(df))):
                futuro = df.iloc[j]
                if sinal > 0: # Compras
                    if futuro['low'] <= alvos['stop']: 
                        stop_hit = True
                        break
                    if futuro['high'] >= alvos['100%']: hit_100 = True
                    if futuro['high'] >= alvos['161.8%']: hit_161 = True
                    if futuro['high'] >= alvos['197%']: hit_197 = True
                else: # Vendas
                    if futuro['high'] >= alvos['stop']: 
                        stop_hit = True
                        break
                    if futuro['low'] <= alvos['100%']: hit_100 = True
                    if futuro['low'] <= alvos['161.8%']: hit_161 = True
                    if futuro['low'] <= alvos['197%']: hit_197 = True
                    
            resultados.append({
                'Tipo': 'Engolfo (+100%)' if abs(sinal) == 2 else 'Quebra (50%)',
                'Entropia': entropia,
                'Alvo_100': hit_100,
                'Stop': stop_hit
            })

    mt5.shutdown()
    
    # === ANALÍTICA CENTURIO ===
    df_res = pd.DataFrame(resultados)
    if not df_res.empty:
        total = len(df_res)
        tx_100 = (df_res['Alvo_100'].sum() / total) * 100
        tx_stop = (df_res['Stop'].sum() / total) * 100
        
        print(f"\n--- RAIO-X GERAL (SEM FILTRO) ---")
        print(f"Total de Sinais Detectados: {total}")
        print(f"Taxa de Stop Acionado: {tx_stop:.1f}%")
        print(f"Taxa de Alvo 100%: {tx_100:.1f}%")
        
        # O FILTRO DA ENTROPIA
        df_engolfo = df_res[df_res['Tipo'] == 'Engolfo (+100%)']
        if len(df_engolfo) > 0:
            alta_entropia = df_engolfo[df_engolfo['Entropia'] > 0.8]
            baixa_entropia = df_engolfo[df_engolfo['Entropia'] <= 0.8]
            
            print(f"\n--- FILTRO DE ENTROPIA NOS ENGOLFOS (+100%) ---")
            print(f"Total de Engolfos: {len(df_engolfo)}")
            if len(alta_entropia) > 0:
                print(f"  > Engolfos Caóticos (> 0.8): {len(alta_entropia)} sinais")
                print(f"    -> Taxa de Stop no Caos: {(alta_entropia['Stop'].sum() / len(alta_entropia) * 100):.1f}%")
                
            if len(baixa_entropia) > 0:
                print(f"  > Engolfos Ordenados (<= 0.8): {len(baixa_entropia)} sinais")
                print(f"    -> Taxa de Acerto 100% na Ordem: {(baixa_entropia['Alvo_100'].sum() / len(baixa_entropia) * 100):.1f}%")
    else:
        print("Nenhum evento detectado na amostra.")

if __name__ == "__main__":
    iniciar_auditoria()