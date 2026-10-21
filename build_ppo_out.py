#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga PPO NotreDame Saúde, vigência 21/10/2026 a 31/12/2026 -> /tmp/ppo_out_parsed.json

A remessa de 20/10 trouxe 5 PDFs (~/Downloads/PPO), 9 praças cada:
    porte I  1 vida
    porte I  2 a 29 vidas · MEI
    porte I  2 a 29 vidas · Demais Empresas
    porte II (30 a 99)   · Compulsório
    porte II (30 a 99)   · Adesão

Cada praça tem 2 páginas (coparticipação parcial e total) e, em cada uma, blocos:

    LINHA METAIS ....... PRATA, PRATA MAX, OURO, OURO MAX (reembolso PARCIAL)
                         DIAMANTE, DIAMANTE MAX          (reembolso TOTAL)
    LINHA TRADICIONAL .. ADVANCE 600/700, PREMIUM 900 (CARE)   reembolso PARCIAL
                         + PREMIUM 900 e INFINITY 1000.11      reembolso TOTAL

A LINHA METAIS é NOVA no catálogo. Na Tradicional o reembolso é um eixo que o
vendedor escolhe (campo `pr2`); na Metais ele é propriedade do produto — Prata e
Ouro só existem com reembolso parcial, Diamante só com total. Por isso a entrada
sai com `reembTipo` (gancho que o reembTipoDe() do index já lê) e SEM `pr2`.

Colunas ancoradas no CÓD. INTERNO — o rótulo PRODUTO cobre mais de uma coluna
(PRATA tem enfermaria e apartamento) e só o código distingue.

NÃO grava no catálogo: escreve o JSON e imprime o diff contra o catalog.json.
"""
import pdfplumber, json, os, re, sys, unicodedata, collections

D = '/Users/marcoscorrea/Downloads/PPO/'
OUT = '/tmp/ppo_out_parsed.json'
CAT = '/Users/marcoscorrea/comparativo-ppo/catalog.json'
BANDS = ["00 a 18","19 a 23","24 a 28","29 a 33","34 a 38",
         "39 a 43","44 a 48","49 a 53","54 a 58","59 ou mais"]

def acha(*chaves):
    """Os nomes dos PDFs vieram com acento corrompido ('Compulsขrio'), então
       casa por pedaços ASCII em vez do nome inteiro."""
    for f in sorted(os.listdir(D)):
        if f.lower().endswith('.pdf') and all(k.lower() in f.lower() for k in chaves):
            return f
    return None


ARQS = [
    (acha('porte I 1 Vida'),            dict(vmin=1, vmax=1, mei=False)),
    (acha('2 a 29', 'MEI'),             dict(vmin=2, vmax=29, mei=True)),
    (acha('2 a 29', 'Demais'),          dict(vmin=2, vmax=29, mei=False)),
    (acha('porte II', 'Compuls'),       dict(vmin=30, vmax=99, mei=False, contratacao='Compulsório')),
    (acha('porte II', 'Ades'),          dict(vmin=30, vmax=99, mei=False, contratacao='Adesão')),
]

# nome do PDF -> (plano, label) do catálogo. Os 5 primeiros já existem.
PROD = {
    'ADVANCE 600':        ('600', 'Adv 600'),
    'ADVANCE 700':        ('700', 'Adv 700'),
    'PREMIUM 900 (CARE)': ('900 Care', 'Premium 900 Care'),
    'PREMIUM 900 CARE':   ('900 Care', 'Premium 900 Care'),
    'PREMIUM 900':        ('900', 'Premium 900'),
    'INFINITY 1000.11':   ('Infinity', 'Infinity'),
    'INFINITY':           ('Infinity', 'Infinity'),
    'PRATA':              ('Prata', 'Prata'),
    'PRATA MAX':          ('Prata Max', 'Prata Max'),
    'OURO':               ('Ouro', 'Ouro'),
    'OURO MAX':           ('Ouro Max', 'Ouro Max'),
    'DIAMANTE':           ('Diamante', 'Diamante'),
    'DIAMANTE MAX':       ('Diamante Max', 'Diamante Max'),
}
ACOM = {'ENFERM': 'Enfermaria', 'ENFERMARIA': 'Enfermaria',
        'APART': 'Apartamento', 'APARTAMENTO': 'Apartamento'}
PRACA_MAP = {'São Paulo - SP': 'SP / RMSP'}
PROD_N = None   # preenchido no fim do módulo (depende de ne())
ACOM_N = None


def ne(s):
    """Chave de comparação: sem acento, caixa alta e SEM espaços."""
    return de(s).replace(' ', '')


def de(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').upper()


def linhas(pg):
    """Agrupa por proximidade de `top`. Faixa fixa (round(top/3)) partia
       cabeçalhos cujos tokens ficam a 1-2 pt de diferença — foi o que fazia
       'ADVANCE 600' sumir da linha PRODUTO."""
    ws = sorted(pg.extract_words(x_tolerance=1.2), key=lambda w: (w['top'], w['x0']))
    grupos = []
    for w in ws:
        if grupos and abs(w['top'] - grupos[-1][0]) <= 2.5:
            grupos[-1][1].append(w)
        else:
            grupos.append([w['top'], [w]])
    return [sorted(g, key=lambda w: w['x0']) for _, g in grupos]


def bordas(pg, t0, t1):
    """Bordas verticais da tabela na faixa [t0,t1] — é o que separa as colunas."""
    xs = set()
    for o in list(pg.lines) + list(pg.rects) + list(pg.edges):
        if o.get('orientation') == 'v' or abs(o['x1'] - o['x0']) < 0.9:
            if o['top'] <= t1 + 2 and o['bottom'] >= t0 - 2:
                xs.add(round(o['x0'], 1))
    b = []
    for x in sorted(xs):
        if b and x - b[-1] < 1.5: continue
        b.append(x)
    return b


def faixa_de(b, x):
    """Índice da coluna (par de bordas) que contém x."""
    for i in range(len(b) - 1):
        if b[i] - 1 <= x < b[i + 1]:
            return i
    return None


def rotulo_por_coluna(pg, r, b, ncols, lacuna=9):
    """Texto do cabeçalho `r` para cada coluna de dados.

    O rótulo que cobre várias colunas é CENTRALIZADO sobre elas — o
    "C O M  R E E M B O L S O  P A R C I A L" abrange 6 colunas mas só encosta
    nas do meio, então sobreposição de texto não serve. O que serve é a borda
    da CÉLULA MESCLADA: as linhas verticais desenhadas na faixa desta linha são
    exatamente os limites dela.
    """
    y0, y1 = min(w['top'] for w in r), max(w['bottom'] for w in r)
    bh = [x for x in bordas(pg, y0 + 0.5, y1 - 0.5) if b[0] - 3 <= x <= b[-1] + 3]
    ws = [w for w in r if w['x0'] >= b[1] - 4]     # fora o nome da linha
    out = [None] * ncols
    if len(bh) >= 2:
        # texto de cada célula mesclada
        txt = {}
        for w in ws:
            k = faixa_de(bh, (w['x0'] + w['x1']) / 2)
            if k is not None:
                txt.setdefault(k, []).append(w)
        cel = {k: re.sub(r'\s+', ' ', ' '.join(x['text'] for x in sorted(v, key=lambda w: w['x0']))).strip()
               for k, v in txt.items()}
        for ci in range(ncols):
            k = faixa_de(bh, (b[ci] + b[ci + 1]) / 2)
            out[ci] = cel.get(k)
        if any(out):
            return out
    # sem bordas próprias: cai no agrupamento por lacuna + sobreposição
    grupos, atual = [], []
    for w in ws:
        if atual and w['x0'] - atual[-1]['x1'] > lacuna:
            grupos.append(atual); atual = []
        atual.append(w)
    if atual: grupos.append(atual)
    cels = [(g[0]['x0'], g[-1]['x1'], re.sub(r'\s+', ' ', ' '.join(x['text'] for x in g)).strip())
            for g in grupos]
    for ci in range(ncols):
        a, z = b[ci], b[ci + 1]
        melhor, area = None, 0
        for c in cels:
            ov = min(c[1], z) - max(c[0], a)
            if ov > area: melhor, area = c[2], ov
        out[ci] = melhor
    return out


def valor(t):
    return float(t.replace(' ', '').replace('.', '').replace(',', '.'))


def corte_reajuste(pg, ls):
    """x a partir do qual a página vira tabela de REAJUSTE.

    Só corta quando o reajuste está AO LADO (arquivo de 1 vida): a palavra
    REAJUSTE divide a faixa vertical com uma linha CÓD. INTERNO. Nos demais
    arquivos ele vem ABAIXO das tabelas — cortar ali comeria a tabela de preços.
    """
    cods = [r[0]['top'] for r in ls
            if de(' '.join(w['text'] for w in r)).startswith('COD. INTERNO')]
    if not cods:
        return pg.width
    alvo = [w for r in ls for w in r
            if w['text'].upper().startswith('REAJUSTE')
            and any(abs(w['top'] - t) < 9 for t in cods)]
    return min(w['x0'] for w in alvo) - 6 if alvo else pg.width


def parse_pagina(pg):
    ls0 = linhas(pg)
    lim = corte_reajuste(pg, ls0)
    ls = [r for r in ([w for w in r if w['x1'] <= lim] for r in ls0) if r]
    cab = (pg.extract_text() or '').split('\n')
    praca = PRACA_MAP.get(cab[1].strip(), cab[1].strip()) if len(cab) > 1 else None
    copart = 'Parcial' if 'COM COPARTICIPAÇÃO PARCIAL' in '\n'.join(cab[:7]) else 'Completa'
    saida, avisos = [], []
    for i, r in enumerate(ls):
        if not de(' '.join(w['text'] for w in r)).startswith('COD. INTERNO'):
            continue
        cods = [w for w in r if re.fullmatch(r'\d{4,6}\*?', w['text'])]
        if len(cods) < 2:
            continue

        # linhas de faixa etária deste bloco
        precos, fim = {}, None
        for j in range(i + 1, min(len(ls), i + 26)):
            t = ' '.join(w['text'] for w in ls[j])
            m = re.match(r'^(\d\d a \d\d) anos', t) or re.match(r'^59 anos ou mais', t)
            if not m:
                if precos: break
                continue
            banda = '59 ou mais' if t.startswith('59') else m.group(1)
            toks = [w for w in ls[j] if re.fullmatch(r'[\d.]*,\d\d|[\d.]+', w['text'])]
            nums, k = [], 0
            while k < len(toks):
                t1 = toks[k]['text']
                if ',' not in t1 and k + 1 < len(toks) and toks[k+1]['x0'] - toks[k]['x1'] < 3.2:
                    nums.append((toks[k]['x0'], toks[k+1]['x1'], valor(t1 + toks[k+1]['text'].lstrip('.'))))
                    k += 2
                else:
                    if ',' in t1: nums.append((toks[k]['x0'], toks[k]['x1'], valor(t1)))
                    k += 1
            precos[banda] = nums
            fim = ls[j][0]['bottom']
            if len(precos) == 10: break
        if len(precos) != 10:
            continue

        # bordas reais da tabela, do cabeçalho ate a ultima faixa
        topo = ls[max(0, i - 6)][0]['top']
        b = [x for x in bordas(pg, topo, fim) if cods[0]['x0'] - 110 <= x <= lim]
        if len(b) < 3:
            avisos.append('%s: bloco sem bordas (top=%.0f)' % (praca, r[0]['top'])); continue
        ncols = len(b) - 1
        col_de = {}
        for w in cods:
            ci = faixa_de(b, w['x0'])
            if ci is not None: col_de[ci] = w['text']
        if len(col_de) != len(cods):
            avisos.append('%s: %d códigos em %d colunas (top=%.0f)'
                          % (praca, len(cods), len(col_de), r[0]['top'])); continue

        x_ini = b[0] - 2
        cabs = {}
        for j in range(i - 1, max(-1, i - 14), -1):
            t = de(' '.join(w['text'] for w in ls[j]))
            for ch in ('REEMBOLSO', 'PRODUTO', 'ACOMODACAO'):
                if t.startswith(ch) and ch not in cabs:
                    cabs[ch] = rotulo_por_coluna(pg, ls[j], b, ncols)
        if 'PRODUTO' not in cabs or 'ACOMODACAO' not in cabs:
            continue
        reembs = cabs.get('REEMBOLSO') or [None] * ncols
        distintos = {x for x in reembs if x}
        reemb_unico = list(distintos)[0] if len(distintos) == 1 else None

        for ci, cod in sorted(col_de.items()):
            prod, acom = cabs['PRODUTO'][ci], cabs['ACOMODACAO'][ci]
            if not prod or not acom: continue
            p = PROD_N.get(ne(prod))
            a = ACOM_N.get(ne(acom))
            if not p or not a:
                avisos.append('%s: coluna %d sem de-para (%r / %r)' % (praca, ci, prod, acom)); continue
            # quando a coluna da ponta fica fora das bordas do cabeçalho, vale o
            # reembolso do bloco — ele só tem um valor quando há uma célula só
            rb_txt = reembs[ci] or (reemb_unico if reemb_unico else '')
            rb = ne(rb_txt)             # o rótulo vem com letras espaçadas
            rb = 'Parcial' if 'PARCIAL' in rb else ('Total' if 'TOTAL' in rb else None)
            pr, ok = {}, True
            for bd in BANDS:
                cand = [v for v in precos[bd] if faixa_de(b, v[0]) == ci or faixa_de(b, v[1]) == ci]
                if not cand: ok = False; break
                pr[bd] = cand[-1][2]
            if not ok:
                avisos.append('%s: coluna %d (%s) sem preço completo' % (praca, ci, p[1])); continue
            saida.append(dict(plano=p[0], label=p[1], acomodacao=a, coparticipacao=copart,
                              reembTipo=rb, precos=pr, praca=praca, cod=cod))
    return praca, saida, avisos


PROD_N = {ne(k): v for k, v in PROD.items()}
ACOM_N = {ne(k): v for k, v in ACOM.items()}

TODOS_AVISOS = []


def main():
    res = {}
    for arq, meta in ARQS:
        p = D + arq
        if not os.path.exists(p):
            print('FALTA:', arq); continue
        pdf = pdfplumber.open(p)
        n = 0
        for pg in pdf.pages:
            praca, ents, avisos = parse_pagina(pg)
            TODOS_AVISOS.extend(avisos)
            if not praca or not ents: continue
            for e in ents:
                e.update(meta)
                e['operadora'] = 'Hapvida'
                e['tipo'] = 'Empresarial'
                e['categoria'] = 'Geral'
                e.setdefault('mei', False)
                e['fonte'] = arq
            res.setdefault(praca, []).extend(ents)
            n += len(ents)
        print('%-62s %5d entradas' % (arq[:62], n))
    if TODOS_AVISOS:
        print('\navisos (%d):' % len(TODOS_AVISOS))
        import collections as _c
        for a, q in _c.Counter(TODOS_AVISOS).most_common(12): print('   %-92s x%d' % (a[:92], q))
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    tot = sum(len(v) for v in res.values())
    print('\nTotal: %d entradas em %d praças -> %s' % (tot, len(res), OUT))
    linha = collections.Counter(
        ('METAIS' if e['plano'] in ('Prata','Prata Max','Ouro','Ouro Max','Diamante','Diamante Max')
         else 'TRADICIONAL') for v in res.values() for e in v)
    print('por linha:', dict(linha))
    c = collections.Counter((e['plano'], e['acomodacao'], e['reembTipo']) for v in res.values() for e in v)
    print('\n%-14s %-12s %-8s %s' % ('PLANO','ACOM.','REEMB.','n'))
    for k, v in sorted(c.items(), key=str):
        print('%-14s %-12s %-8s %d' % (k[0], k[1], k[2], v))


if __name__ == '__main__':
    main()
