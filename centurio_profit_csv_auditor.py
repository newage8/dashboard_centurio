#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CENTURIO PROFIT CSV AUDITOR  -  Tubasa Labs  -  WINZ26 M5
=========================================================
Analisa SOMENTE PRECO. Sem entrada, parcial, lote, stop, break even ou trailing.

O que o script faz
  1. Le o CSV exportado do ProfitChart e isola UM pregao (padrao: o ultimo da base).
  2. Detecta os candles de ENGOLFO por regra explicita (ver DEFINICOES abaixo).
  3. Confere a SUA lista visual (--candles 5,14,18,33,38,42): cada candle
     engolfou de verdade? E o codigo achou algum engolfo que voce nao marcou?
  4. Mede, em cada engolfo: forma do candle, estrutura ANTES, movimento gerado DEPOIS
     (horizontes fixos e "perna" ate o proximo engolfo contrario) e ORDEM x CAOS.
  5. Compara os engolfos com um CONTROLE (candles comuns da mesma direcao), para nao
     confundir "bonito a olho nu" com "estatisticamente diferente".
  6. Opcional (--ticks): entropia de Shannon, Hurst, SampEn e dimensao fractal DENTRO
     do candle, a partir do arquivo de negocios (tick a tick).

DEFINICOES (todas em pontos do WIN; 1 tick = 5 pontos)
  ENGOLFO DE ALTA  (E1): candle de alta  (Close > Open) com Close  > High do candle anterior.
  ENGOLFO DE BAIXA (E1): candle de baixa (Close < Open) com Close  < Low  do candle anterior.
  Fechar exatamente na maxima/minima anterior NAO conta (e marcado como LIMITE).
  anterior_oposto : o candle anterior tem cor oposta ao candle atual.
  tipo REVERSAO   : o movimento dos ultimos --lookback candles ANTES do engolfo era contrario a ele.
  tipo CONTINUACAO: o movimento anterior era na mesma direcao do engolfo.
  ENGOLFO ESTRITO = E1 + anterior_oposto + tipo REVERSAO (o "primeiro candle contrario").

  Origem das medidas depois do engolfo = Close do proprio candle engolfante. Isso e uma
  referencia de MEDIDA, nao uma entrada.
    fav_H : maior excursao a favor nos proximos H candles (pts; 0 se nunca passou do Close)
    adv_H : maior recuo contra       nos proximos H candles (pts)
    liq_H : deslocamento liquido Close[i+H] - Close[i], na direcao do engolfo
    perna : do Close ate o extremo atingido antes do proximo engolfo contrario
            (ou ate o fim do pregao = perna_aberta)
    er_*  : razao de eficiencia de Kaufman (|deslocamento| / caminho percorrido).
            Proxy de ORDEM (perto de 1) x CAOS (perto de 0) usando so candles.

Uso (terminal do VS Code, com o venv ativo):
  python centurio_profit_csv_auditor.py --csv win_hoje.csv --candles 5,14,18,33,38,42
  python centurio_profit_csv_auditor.py --csv win_hoje.csv --ticks negocios_hoje.csv
  python centurio_profit_csv_auditor.py --csv win_hoje.csv --data 2026-11-03 --base 0

Dependencias: pandas, numpy, matplotlib.
"""
import argparse
import io
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

HORIZONTES = (1, 3, 6, 12)
MULT_AMPLITUDE = (1.0, 1.618, 1.97)
H_ER = 6
MIN_TICKS_HURST = 1000

SYN = {
    'open': {'abertura', 'open', 'abert', 'o'},
    'high': {'maximo', 'maxima', 'high', 'max', 'h'},
    'low': {'minimo', 'minima', 'low', 'min', 'l'},
    'close': {'fechamento', 'fecha', 'fech', 'close', 'ultimo', 'c'},
    'vol': {'volume', 'vol'},
    'ativo': {'ativo', 'symbol', 'papel', 'ticker'},
    'data': {'data', 'date', 'dia'},
    'hora': {'hora', 'time', 'horario'},
    'dt': {'datahora', 'datetime', 'timestamp', 'dthr', 'abertura'},
    'preco': {'preco', 'price', 'ultimo', 'valor', 'negocio'},
}


# ----------------------------------------------------------------------------
# LEITURA ROBUSTA DO CSV DO PROFIT
# ----------------------------------------------------------------------------
def norm(txt):
    t = unicodedata.normalize('NFKD', str(txt))
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]', '', t.lower())


def num_br(serie):
    """Converte numeros no padrao brasileiro. Ex.: '170.185' (milhar) e '170185,00'."""
    def conv(x):
        x = str(x).strip().replace('\u00a0', '')
        if x in ('', 'nan', 'None', '-', '<NA>'):
            return np.nan
        if ',' in x:
            x = x.replace('.', '').replace(',', '.')
        elif '.' in x:
            partes = x.split('.')
            if len(partes) >= 2 and len(partes[-1]) == 3:
                x = x.replace('.', '')
        try:
            return float(x)
        except ValueError:
            return np.nan
    return serie.map(conv).astype(float)


DATA_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}')
HORA_RE = re.compile(r'^\d{1,2}:\d{2}')


def ler_texto(caminho):
    with open(caminho, 'rb') as f:
        raw = f.read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16')
    if raw[:3] == b'\xef\xbb\xbf':
        return raw.decode('utf-8-sig')
    if b'\x00' in raw[:400]:
        return raw.decode('utf-16-le', errors='ignore')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def _sep(lin):
    for s in (';', '\t', '|'):
        if lin.count(s) >= 2:
            return s
    return ',' if lin.count(',') >= 4 else r'\s+'


def _split(lin, sep):
    return [x.strip().strip('"') for x in re.split(sep if sep == r'\s+' else re.escape(sep), lin)]


def _eh_num(x):
    return not np.isnan(num_br(pd.Series([x])).iloc[0])


def ler_tabela(caminho):
    linhas = ler_texto(caminho).splitlines()
    for i, lin in enumerate(linhas[:200]):
        toks = {norm(t) for t in re.split(r'[;\t,|]|\s+', lin) if t.strip()}
        n_ohlc = sum(bool(toks & SYN[k]) for k in ('open', 'high', 'low', 'close'))
        tem_tempo = bool(toks & (SYN['data'] | SYN['hora'] | SYN['dt']))
        modo = 'candles' if n_ohlc >= 4 else ('ticks' if (toks & SYN['preco'] and tem_tempo) else None)
        if modo:
            df = pd.read_csv(io.StringIO('\n'.join(linhas[i:])), sep=_sep(lin), dtype=str,
                             engine='python', skipinitialspace=True)
            df.columns = [str(c).strip().strip('"') for c in df.columns]
            df = df.loc[:, [c for c in df.columns if not c.lower().startswith('unnamed')]]
            return df.dropna(how='all'), modo
    for i, lin in enumerate(linhas[:200]):
        if not lin.strip():
            continue
        sep = _sep(lin)
        f = _split(lin, sep)
        if len(f) >= 6 and DATA_RE.match(f[0]) and HORA_RE.match(f[1]) and all(_eh_num(x) for x in f[2:6]):
            nomes = ['Data', 'Hora', 'Abertura', 'Maximo', 'Minimo', 'Fechamento']
        elif len(f) >= 7 and DATA_RE.match(f[1]) and HORA_RE.match(f[2]) and all(_eh_num(x) for x in f[3:7]):
            nomes = ['Ativo', 'Data', 'Hora', 'Abertura', 'Maximo', 'Minimo', 'Fechamento']
        elif len(f) >= 5 and DATA_RE.match(f[0]) and ' ' in f[0] and all(_eh_num(x) for x in f[1:5]):
            nomes = ['Data', 'Abertura', 'Maximo', 'Minimo', 'Fechamento']
        else:
            continue
        print('AVISO: CSV sem cabecalho; assumi a ordem: %s' % ', '.join(nomes))
        nomes = nomes + ['Extra%d' % k for k in range(len(f) - len(nomes))]
        df = pd.read_csv(io.StringIO('\n'.join(linhas[i:])), sep=sep, header=None, names=nomes[:len(f)],
                         usecols=range(len(f)), dtype=str, engine='python', skipinitialspace=True)
        return df.dropna(how='all'), 'candles'
    print('ERRO: formato nao reconhecido. Primeiras linhas do arquivo:')
    for l in linhas[:8]:
        print('  ' + repr(l[:200]))
    raise SystemExit('Envie estas linhas ao Cuba.i.')


def pegar_col(df, chave, numerica=False, excluir=()):
    for c in df.columns:
        if norm(c) in SYN[chave] and c not in excluir:
            if not numerica or num_br(df[c]).notna().mean() > 0.9:
                return c
    return None


def montar_datetime(df, usadas):
    for c in df.columns:
        if norm(c) in SYN['dt'] and c not in usadas:
            dt = pd.to_datetime(df[c], dayfirst=True, errors='coerce')
            if dt.notna().mean() > 0.9:
                return dt
    c_data = pegar_col(df, 'data', excluir=usadas)
    c_hora = pegar_col(df, 'hora', excluir=usadas)
    if c_data and c_hora:
        txt = df[c_data].astype(str).str.strip() + ' ' + df[c_hora].astype(str).str.strip()
        return pd.to_datetime(txt, dayfirst=True, errors='coerce')
    if c_data:
        return pd.to_datetime(df[c_data], dayfirst=True, errors='coerce')
    raise SystemExit('ERRO: nao achei colunas de data/hora.')


def candles_de_tabela(df):
    col = {k: pegar_col(df, k, numerica=True) for k in ('open', 'high', 'low', 'close')}
    faltam = [k for k, v in col.items() if v is None]
    if faltam:
        raise SystemExit('ERRO: colunas OHLC nao encontradas: %s' % faltam)
    dt = montar_datetime(df, list(col.values()))
    out = pd.DataFrame({'dt': dt})
    for k, c in col.items():
        out[k] = num_br(df[c])
    cv = pegar_col(df, 'vol', numerica=True)
    out['vol'] = num_br(df[cv]) if cv else np.nan
    ca = pegar_col(df, 'ativo')
    out['ativo'] = df[ca].astype(str).str.strip() if ca else ''
    out = out.dropna(subset=['dt', 'open', 'high', 'low', 'close'])
    return out.sort_values('dt', kind='mergesort').reset_index(drop=True)


def ticks_de_tabela(df):
    cp = pegar_col(df, 'preco', numerica=True)
    if cp is None:
        raise SystemExit('ERRO: coluna de preco nao encontrada no arquivo de negocios.')
    dt = montar_datetime(df, [cp])
    t = pd.DataFrame({'dt': dt, 'preco': num_br(df[cp])}).dropna()
    if len(t) > 1 and t['dt'].iloc[0] > t['dt'].iloc[-1]:
        t = t.iloc[::-1]
    return t.sort_values('dt', kind='mergesort').reset_index(drop=True)


def candles_de_ticks(t, tf):
    o = t.set_index('dt')['preco'].resample('%dmin' % tf, label='left', closed='left').ohlc()
    o = o.dropna().reset_index()
    o['vol'] = np.nan
    o['ativo'] = ''
    return o


def achar_arquivo(arg):
    base = os.path.dirname(os.path.abspath(__file__))
    lista = [arg, os.path.join(os.getcwd(), arg), os.path.join(base, arg),
             os.path.join(base, '..', 'data_profit', arg),
             os.path.join('C:\\Tubasa_Labs', 'data_profit', arg),
             os.path.join('C:\\Tubasa_Labs', arg)]
    for c in lista:
        if os.path.isfile(c):
            return c
    raise SystemExit('ERRO: arquivo nao encontrado: %s' % arg)


def isolar_pregao(c, ativo, data):
    if ativo and (c['ativo'] != '').any():
        m = c['ativo'].str.upper().str.contains(ativo.upper(), regex=False)
        if m.any():
            c = c[m]
        else:
            print('AVISO: ativo %s nao encontrado na coluna Ativo; usando todas as linhas.' % ativo)
    dias = c['dt'].dt.date
    dia = pd.to_datetime(data).date() if data else dias.max()
    s = c[dias == dia].copy()
    if s.empty:
        raise SystemExit('ERRO: sem candles em %s' % dia)
    return s.reset_index(drop=True), dia


def garantir_tf(s, tf):
    d = s['dt'].diff().dt.total_seconds().div(60).dropna()
    d = d[d > 0]
    med = float(d.median()) if len(d) else float(tf)
    if med > tf * 1.1:
        raise SystemExit('ERRO: a base tem candles de ~%.1f min; preciso de %d min ou menos.' % (med, tf))
    if med < tf * 0.9:
        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'vol': 'sum'}
        r = s.set_index('dt').resample('%dmin' % tf, label='left', closed='left').agg(agg)
        r = r.dropna(subset=['open']).reset_index()
        r['ativo'] = ''
        return r, True
    return s.reset_index(drop=True), False


# ----------------------------------------------------------------------------
# ESTRUTURA E ENGOLFOS
# ----------------------------------------------------------------------------
def marcar_estrutura(s, lookback, min_mov):
    O = s['open'].to_numpy(float)
    H = s['high'].to_numpy(float)
    L = s['low'].to_numpy(float)
    C = s['close'].to_numpy(float)
    n = len(s)
    rng = H - L
    corpo = np.abs(C - O)
    alta, baixa = C > O, C < O

    d = pd.DataFrame({
        'idx1': np.arange(1, n + 1),
        'hora': s['dt'].dt.strftime('%H:%M').to_numpy(),
        'open': O, 'high': H, 'low': L, 'close': C,
        'range': rng, 'corpo': corpo,
    })
    with np.errstate(divide='ignore', invalid='ignore'):
        d['corpo_pct'] = np.where(rng > 0, corpo / rng, np.nan)
        d['clv'] = np.where(rng > 0, (C - L) / rng, np.nan)
    d['pavio_sup'] = H - np.maximum(O, C)
    d['pavio_inf'] = np.minimum(O, C) - L
    d['cor'] = np.where(alta, 'alta', np.where(baixa, 'baixa', 'doji'))

    e_alta = np.zeros(n, bool)
    e_baixa = np.zeros(n, bool)
    margem = np.full(n, np.nan)
    ant_oposto = np.zeros(n, bool)
    abs_corpo = np.zeros(n, bool)
    abs_range = np.zeros(n, bool)
    raz_range = np.full(n, np.nan)
    raz_corpo = np.full(n, np.nan)
    for i in range(1, n):
        if alta[i]:
            margem[i] = C[i] - H[i - 1]
            e_alta[i] = C[i] > H[i - 1]
        elif baixa[i]:
            margem[i] = L[i - 1] - C[i]
            e_baixa[i] = C[i] < L[i - 1]
        ant_oposto[i] = (alta[i] and baixa[i - 1]) or (baixa[i] and alta[i - 1])
        topo, base = max(O[i - 1], C[i - 1]), min(O[i - 1], C[i - 1])
        if alta[i]:
            abs_corpo[i] = (C[i] >= topo) and (O[i] <= base)
        elif baixa[i]:
            abs_corpo[i] = (C[i] <= base) and (O[i] >= topo)
        abs_range[i] = (H[i] >= H[i - 1]) and (L[i] <= L[i - 1])
        if rng[i - 1] > 0:
            raz_range[i] = rng[i] / rng[i - 1]
        if corpo[i - 1] > 0:
            raz_corpo[i] = corpo[i] / corpo[i - 1]
    d['margem'] = margem
    d['e1'] = e_alta | e_baixa
    d['direcao'] = np.where(e_alta, 1, np.where(e_baixa, -1, 0))
    d['anterior_oposto'] = ant_oposto
    d['corpo_abs_corpo'] = abs_corpo
    d['range_abs_range'] = abs_range
    d['razao_range'] = raz_range
    d['razao_corpo'] = raz_corpo

    mov = np.full(n, np.nan)
    er = np.full(n, np.nan)
    for i in range(n):
        a = i - 1 - lookback
        if a >= 0:
            mov[i] = C[i - 1] - C[a]
            caminho = np.abs(np.diff(C[a:i])).sum()
            er[i] = abs(mov[i]) / caminho if caminho > 0 else np.nan
    d['mov_antes'] = mov
    d['er_antes'] = er
    tipo = np.full(n, '', dtype=object)
    for i in np.where(d['e1'].to_numpy())[0]:
        m, dr = mov[i], d['direcao'].iat[i]
        if np.isnan(m) or abs(m) <= min_mov:
            tipo[i] = 'INDEFINIDO'
        elif np.sign(m) == -dr:
            tipo[i] = 'REVERSAO'
        else:
            tipo[i] = 'CONTINUACAO'
    d['tipo'] = tipo
    d['estrito'] = d['e1'] & d['anterior_oposto'] & (d['tipo'] == 'REVERSAO')
    mx, mn = np.maximum.accumulate(H), np.minimum.accumulate(L)
    with np.errstate(divide='ignore', invalid='ignore'):
        d['pos_dia'] = np.where(mx > mn, (C - mn) / (mx - mn), np.nan)
    return d


def excursoes(i, dirc, H, L, C):
    """fav/adv/liq e ER nos horizontes fixos. NaN se nao houver candles suficientes."""
    n = len(C)
    out = {}
    for h in HORIZONTES:
        if i + h > n - 1:
            out['fav_%d' % h] = out['adv_%d' % h] = out['liq_%d' % h] = np.nan
            continue
        hi, lo = H[i + 1:i + h + 1].max(), L[i + 1:i + h + 1].min()
        if dirc == 1:
            out['fav_%d' % h] = max(hi - C[i], 0.0)
            out['adv_%d' % h] = max(C[i] - lo, 0.0)
            out['liq_%d' % h] = C[i + h] - C[i]
        else:
            out['fav_%d' % h] = max(C[i] - lo, 0.0)
            out['adv_%d' % h] = max(hi - C[i], 0.0)
            out['liq_%d' % h] = C[i] - C[i + h]
    if i + H_ER <= n - 1:
        cam = np.abs(np.diff(C[i:i + H_ER + 1])).sum()
        out['er_depois'] = abs(C[i + H_ER] - C[i]) / cam if cam > 0 else np.nan
    else:
        out['er_depois'] = np.nan
    return out


def perna(i, dirc, dir_arr, H, L, C, amp):
    n = len(C)
    vazio = {'perna_pts': np.nan, 'perna_candles': np.nan, 'perna_min': np.nan,
             'recuo_ate_ext': np.nan, 'perna_aberta': np.nan, 'perna_x_amp': np.nan}
    for m in MULT_AMPLITUDE:
        vazio['perna_ge_%sx' % m] = np.nan
    if i >= n - 1:
        return vazio
    opp = np.where(dir_arr[i + 1:] == -dirc)[0]
    j = i + 1 + int(opp[0]) if len(opp) else n - 1
    if dirc == 1:
        seg = H[i + 1:j + 1]
        k = i + 1 + int(np.argmax(seg))
        pts = max(seg.max() - C[i], 0.0)
        rec = max(C[i] - L[i + 1:k + 1].min(), 0.0)
    else:
        seg = L[i + 1:j + 1]
        k = i + 1 + int(np.argmin(seg))
        pts = max(C[i] - seg.min(), 0.0)
        rec = max(H[i + 1:k + 1].max() - C[i], 0.0)
    out = {'perna_pts': pts, 'perna_candles': k - i, 'perna_min': 5 * (k - i),
           'recuo_ate_ext': rec, 'perna_aberta': len(opp) == 0,
           'perna_x_amp': pts / amp if amp > 0 else np.nan}
    for m in MULT_AMPLITUDE:
        out['perna_ge_%sx' % m] = bool(pts >= m * amp) if amp > 0 else np.nan
    return out


def medir(d):
    H, L, C = d['high'].to_numpy(float), d['low'].to_numpy(float), d['close'].to_numpy(float)
    dir_arr = d['direcao'].to_numpy(int)
    linhas = []
    for i in np.where(d['e1'].to_numpy())[0]:
        dirc = int(dir_arr[i])
        r = {'i': i}
        r.update(excursoes(i, dirc, H, L, C))
        r.update(perna(i, dirc, dir_arr, H, L, C, float(d['range'].iat[i])))
        linhas.append(r)
    ev = pd.DataFrame(linhas)
    if ev.empty:
        return ev
    base = d.iloc[ev['i'].to_numpy()].reset_index(drop=True)
    return pd.concat([base, ev.drop(columns=['i'])], axis=1)


def controle(d):
    H, L, C = d['high'].to_numpy(float), d['low'].to_numpy(float), d['close'].to_numpy(float)
    linhas = []
    for i in range(1, len(d)):
        if d['e1'].iat[i] or d['cor'].iat[i] == 'doji':
            continue
        dirc = 1 if d['cor'].iat[i] == 'alta' else -1
        linhas.append(excursoes(i, dirc, H, L, C))
    return pd.DataFrame(linhas)


# ----------------------------------------------------------------------------
# ORDEM x CAOS DENTRO DO CANDLE (precisa de negocios tick a tick)
# ----------------------------------------------------------------------------
def shannon(inc):
    n = len(inc)
    if n == 0:
        return np.nan, np.nan
    up, dn = int((inc > 0).sum()), int((inc < 0).sum())
    fl = n - up - dn

    def h(cont, k):
        p = np.array([c / sum(cont) for c in cont if c > 0])
        return float(-(p * np.log(p)).sum() / np.log(k)) if len(p) else np.nan
    return h([up, dn, fl], 3), (h([up, dn], 2) if (up + dn) > 0 else np.nan)


def hurst_rs(x):
    x = np.asarray(x, float)
    n = len(x)
    tams = [s for s in (8, 16, 32, 64, 128, 256, 512, 1024) if s <= n // 2]
    if len(tams) < 3:
        return np.nan
    lr = []
    for s in tams:
        m = n // s
        b = x[:m * s].reshape(m, s)
        z = np.cumsum(b - b.mean(axis=1, keepdims=True), axis=1)
        R = z.max(axis=1) - z.min(axis=1)
        S = b.std(axis=1)
        ok = S > 0
        if ok.sum() == 0:
            return np.nan
        lr.append(np.log((R[ok] / S[ok]).mean()))
    return float(np.polyfit(np.log(tams), lr, 1)[0])


def sampen(x, m=2, r_frac=0.2, nmax=2000):
    x = np.asarray(x, float)[:nmax]
    n = len(x)
    if n < 50:
        return np.nan
    r = r_frac * x.std()
    if r == 0:
        return np.nan
    N = n - m

    def cont(mm):
        T = np.lib.stride_tricks.sliding_window_view(x, mm)[:N]
        c = 0
        for i in range(N - 1):
            c += int(np.sum(np.max(np.abs(T[i + 1:] - T[i]), axis=1) <= r))
        return c
    B, A = cont(m), cont(m + 1)
    if A == 0 or B == 0:
        return np.nan
    return float(-np.log(A / B))


def higuchi_fd(x, kmax=10):
    x = np.asarray(x, float)
    N = len(x)
    if N < 4 * kmax:
        return np.nan
    ks = np.arange(1, kmax + 1)
    Lk = []
    for k in ks:
        Lm = []
        for m in range(k):
            idx = np.arange(m, N, k)
            if len(idx) < 2:
                continue
            Lm.append(np.abs(np.diff(x[idx])).sum() * (N - 1) / ((len(idx) - 1) * k) / k)
        Lk.append(np.mean(Lm))
    if not np.all(np.array(Lk) > 0):
        return np.nan
    return float(np.polyfit(np.log(1.0 / ks), np.log(Lk), 1)[0])


def metricas_ticks(t, inicio, tf):
    fim = inicio + pd.Timedelta(minutes=tf)
    p = t.loc[(t['dt'] >= inicio) & (t['dt'] < fim), 'preco'].to_numpy(float)
    inc = np.diff(p)
    s3, s2 = shannon(inc)
    return {'n_ticks': len(p), 'shannon3': s3, 'shannon_dir': s2,
            'hurst': hurst_rs(inc) if len(inc) >= 64 else np.nan,
            'hurst_confiavel': len(inc) >= MIN_TICKS_HURST,
            'sampen': sampen(inc), 'fractal_fd': higuchi_fd(p)}


# ----------------------------------------------------------------------------
# RELATORIOS
# ----------------------------------------------------------------------------
def fmt(df, cols, nd=1):
    return df[cols].to_string(index=False, float_format=lambda v: ('%.' + str(nd) + 'f') % v)


def status_candidato(r):
    if r['e1']:
        extra = 'estrito' if r['estrito'] else (
            '%s, anterior %s' % (r['tipo'], 'oposto' if r['anterior_oposto'] else 'MESMA cor'))
        return 'ENGOLFO (%s)' % extra
    if r['cor'] == 'doji':
        return 'NAO engolfa: doji'
    if r['margem'] == 0:
        return 'LIMITE: fechou exatamente no extremo anterior'
    return 'NAO engolfa: fecha dentro (faltaram %.0f pts para passar do extremo anterior)' % abs(r['margem'])


def conferir_lista(d, lista, base):
    n = len(d)

    def acertos(b):
        return sum(1 for k in lista if 0 <= k - b < n and bool(d['e1'].iat[k - b]))
    a1, a0 = acertos(1), acertos(0)
    print('\n' + '=' * 78)
    print('CONFERENCIA DA SUA LISTA VISUAL  (numeracao: candle %d = primeiro do pregao, %s)' %
          (base, d['hora'].iat[0]))
    print('=' * 78)
    linhas = []
    for k in lista:
        i = k - base
        if not (0 <= i < n):
            print('candle %d: fora do pregao (%d candles)' % (k, n))
            continue
        r = d.iloc[i]
        ant = d.iloc[i - 1] if i > 0 else None
        linhas.append({
            'candle': k, 'hora': r['hora'], 'cor': r['cor'], 'close': r['close'],
            'high_ant': ant['high'] if ant is not None else np.nan,
            'low_ant': ant['low'] if ant is not None else np.nan,
            'margem': r['margem'], 'status': status_candidato(r)})
    if linhas:
        t = pd.DataFrame(linhas)
        print(t.to_string(index=False, float_format=lambda v: '%.0f' % v))
    achados = d.index[d['e1']] + base
    marcados = {k for k in lista}
    sobrou = [int(k) for k in achados if int(k) not in marcados]
    faltou = [k for k in lista if 0 <= k - base < n and not d['e1'].iat[k - base]]
    print('\nEngolfos E1 detectados no pregao: %d  -> candles %s' % (len(achados), [int(x) for x in achados]))
    print('Da sua lista, CONFIRMADOS: %d de %d' % (len(lista) - len(faltou), len(lista)))
    print('Da sua lista, NAO engolfaram: %s' % faltou)
    print('Engolfos detectados que NAO estavam na sua lista: %s' % sobrou)
    if 0 < len(sobrou) <= 12:
        sub = d[d['e1'] & ~d.index.isin([k - base for k in lista])]
        print(fmt(sub, ['idx1', 'hora', 'cor', 'close', 'margem', 'tipo', 'anterior_oposto'], 0))
    print('\nConferencia da numeracao: acertos com base 1 = %d | com base 0 = %d' % (a1, a0))
    if base == 1 and a0 - a1 >= 2:
        print('ATENCAO: sua lista bate bem mais com a numeracao iniciando em 0. Rode com --base 0.')
    if base == 0 and a1 - a0 >= 2:
        print('ATENCAO: sua lista bate bem mais com a numeracao iniciando em 1. Rode com --base 1.')
    return faltou, sobrou


def relatorio_medidas(ev, ctrl, d):
    print('\n' + '=' * 78)
    print('MOVIMENTO GERADO DEPOIS DE CADA ENGOLFO  (pontos; origem = Close do engolfo)')
    print('=' * 78)
    if ev.empty:
        print('Nenhum engolfo E1 no pregao.')
        return
    cols = ['idx1', 'hora', 'cor', 'tipo', 'range', 'corpo_pct', 'margem', 'fav_3', 'adv_3',
            'fav_6', 'adv_6', 'liq_6', 'perna_pts', 'perna_min', 'recuo_ate_ext', 'perna_aberta']
    print(fmt(ev, cols, 1))
    print('\nORDEM x CAOS (proxy por candles; 1 = ordem, 0 = caos)')
    print(fmt(ev, ['idx1', 'hora', 'corpo_pct', 'clv', 'er_antes', 'er_depois', 'pos_dia'], 2))
    print('\nA perna alcancou multiplos da AMPLITUDE do candle engolfante (a partir do Close):')
    cm = ['idx1', 'hora', 'perna_x_amp'] + ['perna_ge_%sx' % m for m in MULT_AMPLITUDE]
    print(fmt(ev, cm, 2))
    print('\nCOMPARACAO COM O CONTROLE (mediana, pontos)')
    est = ev[ev['estrito']]
    linhas = []
    for nome, g in (('Engolfos E1', ev), ('Engolfos estritos', est), ('Controle (candles comuns)', ctrl)):
        r = {'grupo': nome, 'n': len(g)}
        for h in (3, 6, 12):
            for k in ('fav', 'adv', 'liq'):
                col = '%s_%d' % (k, h)
                r[col] = g[col].median() if len(g) and col in g else np.nan
        linhas.append(r)
    print(pd.DataFrame(linhas).to_string(index=False, float_format=lambda v: '%.1f' % v))
    print('Amostra de UM pregao: leitura DESCRITIVA, sem conclusao estatistica.')


def relatorio_ticks(tk):
    print('\n' + '=' * 78)
    print('ORDEM x CAOS DENTRO DO CANDLE (tick a tick)')
    print('=' * 78)
    print(fmt(tk, ['idx1', 'hora', 'n_ticks', 'shannon3', 'shannon_dir', 'hurst', 'hurst_confiavel',
                   'sampen', 'fractal_fd'], 3))
    print('shannon3: 3 estados (alta/baixa/estavel) normalizada por ln3. '
          'shannon_dir: so alta x baixa, normalizada por ln2 (1.0 = 50/50).')
    print('hurst (R/S nos incrementos): so confiavel com >= %d ticks; abaixo disso ele passa de 0.65 '
          'por acaso com frequencia alta.' % MIN_TICKS_HURST)
    print('fractal_fd (Higuchi no preco): ~1.0 trajeto liso/direcional; ~1.5 passeio aleatorio; ~2.0 ruido.')


def grafico(d, cand_idx, dia, pasta, mostrar):
    import matplotlib
    if not mostrar:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(17, 7.5), facecolor='#0b0f14')
    ax.set_facecolor('#0b0f14')
    off = max((d['high'].max() - d['low'].min()) * 0.012, 5)
    for i, r in d.iterrows():
        cor = '#00e676' if r['close'] > r['open'] else ('#ff1744' if r['close'] < r['open'] else '#ffee58')
        ax.plot([i, i], [r['low'], r['high']], color=cor, lw=1)
        ax.add_patch(Rectangle((i - 0.3, min(r['open'], r['close'])), 0.6,
                               max(abs(r['close'] - r['open']), 2), color=cor))
    for i, r in d[d['e1']].iterrows():
        if r['direcao'] == 1:
            ax.scatter(i, r['low'] - off, marker='^', color='#00e676', s=70, zorder=5)
            ax.text(i, r['low'] - 3 * off, str(r['idx1']), color='#00e676', ha='center', fontsize=8)
        else:
            ax.scatter(i, r['high'] + off, marker='v', color='#ff1744', s=70, zorder=5)
            ax.text(i, r['high'] + 2 * off, str(r['idx1']), color='#ff1744', ha='center', fontsize=8)
    for i in cand_idx:
        if 0 <= i < len(d):
            ax.scatter(i, d['low'].iat[i] - 5.5 * off, marker='o', facecolors='none',
                       edgecolors='#40c4ff', s=170, zorder=6)
    passo = max(len(d) // 18, 1)
    ax.set_xticks(range(0, len(d), passo))
    ax.set_xticklabels(d['hora'].iloc[::passo], color='#9fb3c8', fontsize=8)
    ax.tick_params(axis='y', colors='#9fb3c8')
    ax.grid(color='#1c2733', lw=0.5)
    for sp in ax.spines.values():
        sp.set_color('#1c2733')
    ax.set_title('Centurio Auditor - WINZ26 M5 - %s   (triangulos = engolfo E1; circulo azul = sua lista)' % dia,
                 color='white', fontsize=11)
    os.makedirs(pasta, exist_ok=True)
    arq = os.path.join(pasta, 'grafico_engolfos_%s.png' % dia)
    fig.savefig(arq, dpi=130, facecolor=fig.get_facecolor(), bbox_inches='tight')
    if mostrar:
        plt.show()
    plt.close(fig)
    return arq


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='Centurio - auditor de engolfos (so preco).')
    ap.add_argument('--csv', default='win_hoje.csv', help='CSV do ProfitChart (candles ou negocios)')
    ap.add_argument('--ticks', default=None, help='CSV de negocios tick a tick (opcional)')
    ap.add_argument('--data', default=None, help='pregao AAAA-MM-DD (padrao: ultimo da base)')
    ap.add_argument('--ativo', default='WINZ26')
    ap.add_argument('--tf', type=int, default=5, help='timeframe em minutos (padrao 5)')
    ap.add_argument('--candles', default='', help='sua lista visual, ex.: 5,14,18,33,38,42')
    ap.add_argument('--base', type=int, default=1, choices=(0, 1),
                    help='numeracao da sua lista: 1 = primeiro candle e o 1 (padrao); 0 = comeca em 0')
    ap.add_argument('--lookback', type=int, default=3, help='candles usados p/ definir o movimento anterior')
    ap.add_argument('--min-mov', type=float, default=0.0, help='movimento anterior minimo (pts) p/ nao ser INDEFINIDO')
    ap.add_argument('--excluir-ultimo', action='store_true', help='descarta o ultimo candle (pode estar em formacao)')
    ap.add_argument('--saida', default='saida_auditor')
    ap.add_argument('--sem-grafico', action='store_true')
    ap.add_argument('--mostrar', action='store_true', help='abre o grafico na tela')
    a = ap.parse_args()

    caminho = achar_arquivo(a.csv)
    tabela, modo = ler_tabela(caminho)
    ticks = None
    if modo == 'ticks':
        ticks = ticks_de_tabela(tabela)
        cand = candles_de_ticks(ticks, a.tf)
    else:
        cand = candles_de_tabela(tabela)
    if a.ticks:
        ticks = ticks_de_tabela(ler_tabela(achar_arquivo(a.ticks))[0])

    s, dia = isolar_pregao(cand, a.ativo, a.data)
    s, reamostrado = garantir_tf(s, a.tf)
    if a.excluir_ultimo and len(s) > 1:
        s = s.iloc[:-1].reset_index(drop=True)
    if len(s) < 5:
        raise SystemExit('ERRO: poucos candles (%d) no pregao.' % len(s))

    print('=' * 78)
    print('CENTURIO AUDITOR | arquivo: %s | modo: %s' % (os.path.basename(caminho), modo))
    print('Pregao %s | %d candles de %d min | %s a %s%s' % (
        dia, len(s), a.tf, s['dt'].iloc[0].strftime('%H:%M'), s['dt'].iloc[-1].strftime('%H:%M'),
        ' | reamostrado de timeframe menor' if reamostrado else ''))
    resto = (s[['open', 'high', 'low', 'close']].to_numpy() % 5 != 0).mean()
    if resto > 0.05:
        print('AVISO: %.0f%% dos precos nao sao multiplos de 5 pts. Confira o formato numerico do CSV.' % (resto * 100))
    print('AVISO: o ultimo candle (%s) pode estar em formacao; use --excluir-ultimo se o pregao nao fechou.' %
          s['dt'].iloc[-1].strftime('%H:%M'))
    print('Hora do candle assumida = abertura do candle (verifique no Profit).')

    d = marcar_estrutura(s, a.lookback, a.min_mov)
    lista = [int(x) for x in re.split(r'[,\s;]+', a.candles.strip()) if x] if a.candles else []
    if lista:
        conferir_lista(d, lista, a.base)

    ev = medir(d)
    ctrl = controle(d)
    relatorio_medidas(ev, ctrl, d)

    tk = pd.DataFrame()
    if ticks is not None and len(ticks):
        alvo = set(ev['idx1'].tolist()) if not ev.empty else set()
        alvo |= {k - a.base + 1 for k in lista if 0 <= k - a.base < len(d)}
        linhas = []
        for idx1 in sorted(alvo):
            r = d.iloc[idx1 - 1]
            m = metricas_ticks(ticks, s['dt'].iloc[idx1 - 1], a.tf)
            m.update({'idx1': idx1, 'hora': r['hora']})
            linhas.append(m)
        tk = pd.DataFrame(linhas)
        relatorio_ticks(tk)
    elif a.ticks is None and modo == 'candles':
        print('\n(Sem arquivo de negocios: entropia/Hurst/SampEn/fractal dentro do candle nao foram calculados. Use --ticks.)')

    os.makedirs(a.saida, exist_ok=True)
    kw = dict(sep=';', decimal=',', index=False, encoding='utf-8-sig')
    d.to_csv(os.path.join(a.saida, 'candles_%s.csv' % dia), **kw)
    if not ev.empty:
        ev.to_csv(os.path.join(a.saida, 'engolfos_%s.csv' % dia), **kw)
    if len(tk):
        tk.to_csv(os.path.join(a.saida, 'ticks_%s.csv' % dia), **kw)
    print('\nArquivos salvos em: %s' % os.path.abspath(a.saida))
    if not a.sem_grafico:
        cand_idx = [k - a.base for k in lista]
        print('Grafico: %s' % grafico(d, cand_idx, dia, a.saida, a.mostrar))


if __name__ == '__main__':
    main()