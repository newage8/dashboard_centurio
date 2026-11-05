import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

# ==============================================================================
# TUBASA LABS - CENTURIO GÊNESIS AUDITOR (ANCORAGEM BRT + RAIO-X ESTRUTURAL)
# AUTOR: Moisés Cubas / Cuba.i.
# ==============================================================================

CANDLES_ALVO = [5, 14, 18, 33, 38, 42]

def calcular_entropia_shannon_normalizada(simbolo, t_inicio_utc, t_fim_utc):
    ticks = mt5.copy_ticks_range(simbolo, t_inicio_utc - timedelta(seconds=2), t_fim_utc + timedelta(seconds=2), mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0: return 1.0, 0
    df_ticks = pd.DataFrame(ticks)
    if 'last' not in df_ticks.columns: return 1.0, 0
    df_ticks['diff'] = df_ticks['last'].diff()
    up = len(df_ticks[df_ticks['diff'] > 0])
    down = len(df_ticks[df_ticks['diff'] < 0])
    neutral = len(df_ticks[df_ticks['diff'] == 0])
    total = up + down + neutral
    if total == 0: return 1.0, 0
    p_up, p_down, p_neutral = up / total, down / total, neutral / total
    entropia = 0.0
    for p in [p_up, p_down, p_neutral]:
        if p > 0: entropia -= p * np.log2(p)
    entropia_norm = entropia / np.log2(3)
    return min(entropia_norm, 1.0), total

def auditar_genesis_precos():
    if not mt5.initialize():
        print("ERRO: Falha ao inicializar o MT5.")
        return

    simbolo = "WINZ26"
    rates = mt5.copy_rates_from_pos(simbolo, mt5.TIMEFRAME_M5, 0, 300)
    
    if rates is None or len(rates) == 0:
        simbolo = "WIN$N"
        rates = mt5.copy_rates_from_pos(simbolo, mt5.TIMEFRAME_M5, 0, 300)
        
    if rates is None or len(rates) == 0:
        print("ERRO: Não foi possível obter dados no MT5.")
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df['time_utc'] = pd.to_datetime(df['time'], unit='s', utc=True)
    fuso_br = pytz.timezone("America/Sao_Paulo")
    df['time_brt'] = df['time_utc'].dt.tz_convert(fuso_br)
    
    hoje_data = datetime.now(fuso_br).date()
    df_hoje = df[df['time_brt'].dt.date == hoje_data].copy().sort_values('time_brt').reset_index(drop=True)
    
    if df_hoje.empty:
        print(f"ERRO: Nenhum candle encontrado no MT5 para o dia de hoje ({hoje_data}). Atualize o gráfico no MT5.")
        mt5.shutdown()
        return
        
    idx_abertura = df_hoje[df_hoje['time_brt'].dt.hour == 9].index
    if not idx_abertura.empty:
        idx_start = idx_abertura[0]
        df_pregao = df_hoje.iloc[idx_start:].copy().reset_index(drop=True)
    else:
        df_pregao = df_hoje

    df_pregao['numero_candle'] = df_pregao.index + 1
    
    print("\n" + "="*80)
    print(f" CENTURIO GÊNESIS: AUDITORIA COM RAIO-X MATEMÁTICO ({simbolo})")
    print(f" Data: {hoje_data.strftime('%d/%m/%Y')} | Total Velas no Pregão: {len(df_pregao)}")
    print("="*80 + "\n")
    
    for num in CANDLES_ALVO:
        linha_candle = df_pregao[df_pregao['numero_candle'] == num]
        if linha_candle.empty:
            print(f"📌 [CANDLE {num}] Fora do intervalo. O MT5 precisa ser atualizado (tem apenas {len(df_pregao)} candles).")
            continue
            
        idx = linha_candle.index[0]
        if idx < 1: continue
            
        c_atual = df_pregao.iloc[idx]
        c_prev = df_pregao.iloc[idx - 1]
        hora_str = c_atual['time_brt'].strftime('%H:%M')
        
        era_baixa = c_prev['close'] <= c_prev['open']
        era_alta = c_prev['close'] >= c_prev['open']
        
        engolfo_alta = era_baixa and (c_atual['close'] > c_atual['open']) and (c_atual['close'] > c_prev['high'])
        engolfo_baixa = era_alta and (c_atual['close'] < c_atual['open']) and (c_atual['close'] < c_prev['low'])
        
        detalhe_falha = ""
        if engolfo_alta: 
            direcao = "COMPRA (+100% Engolfo Válido)"
        elif engolfo_baixa: 
            direcao = "VENDA (+100% Engolfo Válido)"
        else: 
            direcao = "FALHA ESTRUTURAL (Não engolfou 100%)"
            if era_baixa and c_atual['close'] > c_atual['open']:
                detalhe_falha = f"   [Raio-X]: Fechamento ({c_atual['close']:.0f}) não superou a Máxima do Pavio Anterior ({c_prev['high']:.0f})"
            elif era_alta and c_atual['close'] < c_atual['open']:
                detalhe_falha = f"   [Raio-X]: Fechamento ({c_atual['close']:.0f}) não rompeu a Mínima do Pavio Anterior ({c_prev['low']:.0f})"
            else:
                detalhe_falha = "   [Raio-X]: Candle não é o primeiro movimento contrário válido."
        
        t_start_utc = c_atual['time_utc'].to_pydatetime()
        t_end_utc = t_start_utc + timedelta(minutes=5)
        entropia_norm, total_ticks = calcular_entropia_shannon_normalizada(simbolo, t_start_utc, t_end_utc)
        estado_termo = "ORDEM (Baixa Entropia <= 0.75)" if entropia_norm <= 0.75 else "CAOS (Alta Entropia > 0.75)"
        
        amp = c_atual['high'] - c_atual['low']
        alvo_100 = c_atual['high'] + amp * 1.00 if engolfo_alta else c_atual['low'] - amp * 1.00
        alvo_197 = c_atual['high'] + amp * 1.97 if engolfo_alta else c_atual['low'] - amp * 1.97
        
        exp_max = 0
        atingiu_100 = atingiu_197 = False
        
        for j in range(idx + 1, min(idx + 25, len(df_pregao))):
            futuro = df_pregao.iloc[j]
            if engolfo_alta:
                exp = futuro['high'] - c_atual['close']
                if exp > exp_max: exp_max = exp
                if futuro['high'] >= alvo_100: atingiu_100 = True
                if futuro['high'] >= alvo_197: atingiu_197 = True
            elif engolfo_baixa:
                exp = c_atual['close'] - futuro['low']
                if exp > exp_max: exp_max = exp
                if futuro['low'] <= alvo_100: atingiu_100 = True
                if futuro['low'] <= alvo_197: atingiu_197 = True
                
        print(f"📌 CANDLE {num} | Horário Profit: {hora_str} BRT")
        print(f"   • Validação 100% (Gênesis) : {direcao}")
        if detalhe_falha != "":
            print(detalhe_falha)
        print(f"   • Amplitude do Candle      : {amp:.0f} pontos (Máx: {c_atual['high']:.0f} | Mín: {c_atual['low']:.0f})")
        print(f"   • Entropia Normalizada     : {entropia_norm:.4f} -> {estado_termo}")
        
        if engolfo_alta or engolfo_baixa:
            print(f"   • Deslocamento Máximo      : +{exp_max:.0f} pontos")
            print(f"   • Alvos de Fibonacci       : 100% {'[SIM]' if atingiu_100 else '[NÃO]'} | 197% {'[SIM]' if atingiu_197 else '[NÃO]'}")
        print("-" * 80)

    mt5.shutdown()

if __name__ == "__main__":
    auditar_genesis_precos()