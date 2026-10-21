#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lê a COPARTICIPAÇÃO da linha Metais (e confere a da Tradicional) nos PDFs
de 21/10-31/12 -> /tmp/copart_metais.json

⚠️ O agrupamento de produtos MUDA entre as duas páginas de cada praça:

    copart PARCIAL ... {Prata, Prata Max, Ouro} | {Ouro Max, Diamante, Diamante Max}
    copart TOTAL ..... {Prata, Prata Max, Ouro} | {Ouro Max, Diamante} | {Diamante Max}

Por isso cada página é lida por si, com as colunas vindo das BORDAS do quadro e
os produtos do cabeçalho PROCEDIMENTO — nada de generalizar uma página para as
outras. A Tradicional é lida junto e serve de conferência: os valores dela já
estão no copart.json de produção.

Saída: {praça: {produto: {parcial:{proc:val}, total:{...}}}}
"""
import pdfplumber, glob, json, os, re, sys, unicodedata, collections

D = '/Users/marcoscorrea/Downloads/PPO/'
OUT = '/tmp/copart_metais.json'
PROCS = [('CONSULTASELETIVAS', 'Consultas eletivas'),
         ('CONSULTASDEURGENCIA', 'Consultas de urgência'),
         ('EXAMESSIMPLES', 'Exames simples'),
         ('EXAMESCOMPLEXOS', 'Exames complexos'),
         ('TERAPIASESPECIAIS', 'Terapias especiais'),
         ('DEMAISTERAPIAS', 'Demais terapias'),
         ('INTERNACOES', 'Internações'), ('INTERNACAO', 'Internações')]
# nome no quadro -> produtos do catálogo que a célula cobre
GRUPOS = {
    'PRATA|PRATAMAX|OURO': ['Prata', 'Prata Max', 'Ouro'],
    'OURAMAX|DIAMANTE|DIAMANTEMAX': ['Ouro Max', 'Diamante', 'Diamante Max'],
    'OUROMAX|DIAMANTE|DIAMANTEMAX': ['Ouro Max', 'Diamante', 'Diamante Max'],
    'OUROMAX|DIAMANTE': ['Ouro Max', 'Diamante'],
    'DIAMANTEMAX': ['Diamante Max'],
    'ADVANCE600/700': ['Adv 600', 'Adv 700'],
    'ADVANCE': ['Adv 600', 'Adv 700'],
    'PREMIUM900/CARE/INFINITY': ['Premium 900', 'Premium 900 Care', 'Infinity'],
    'PREMIUM900/CARE': ['Premium 900', 'Premium 900 Care'],
    'INFINITY': ['Infinity'],
}
PRACA_MAP = {'São Paulo - SP': 'SP / RMSP'}


def de(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').upper()


def ne(s):
    return de(s).replace(' ', '')


def linhas(pg):
    ws = sorted(pg.extract_words(x_tolerance=1.2), key=lambda w: (w['top'], w['x0']))
    g = []
    for w in ws:
        if g and abs(w['top'] - g[-1][0]) <= 2.5: g[-1][1].append(w)
        else: g.append([w['top'], [w]])
    return [sorted(x, key=lambda w: w['x0']) for _, x in g]


def bordas(pg, t0, t1, xmax):
    xs = set()
    for o in list(pg.lines) + list(pg.rects) + list(pg.edges):
        if o.get('orientation') == 'v' or abs(o['x1'] - o['x0']) < 0.9:
            if o['top'] <= t1 + 2 and o['bottom'] >= t0 - 2 and o['x0'] <= xmax:
                xs.add(round(o['x0'], 1))
    b = []
    for x in sorted(xs):
        if b and x - b[-1] < 1.5: continue
        b.append(x)
    return b


def faixa(b, x):
    for i in range(len(b) - 1):
        if b[i] - 1 <= x < b[i + 1]: return i
    return None


# "ADVANCE 600 / 700" precisa casar INTEIRO: senão o "/ 700" vira separador e
# cola a coluna do Advance com a do Premium que vem a seguir.
PRODS_RE = re.compile(
    r'ADVANCE 600 ?/ ?700|PRATA MAX|PRATA|OURO MAX|OURO|DIAMANTE MAX|DIAMANTE|'
    r'ADVANCE 600|ADVANCE 700|ADVANCE|PREMIUM 900 CARE|PREMIUM 900|CARE|INFINITY')
NOME_CAT = {'ADVANCE 600 / 700': ['Adv 600', 'Adv 700'], 'ADVANCE 600/700': ['Adv 600', 'Adv 700'],
            'ADVANCE': ['Adv 600', 'Adv 700'],
            'PRATA': 'Prata', 'PRATA MAX': 'Prata Max', 'OURO': 'Ouro', 'OURO MAX': 'Ouro Max',
            'DIAMANTE': 'Diamante', 'DIAMANTE MAX': 'Diamante Max',
            'ADVANCE 600': 'Adv 600', 'ADVANCE 700': 'Adv 700',
            'PREMIUM 900': 'Premium 900', 'PREMIUM 900 CARE': 'Premium 900 Care',
            'CARE': 'Premium 900 Care', 'INFINITY': 'Infinity'}
VAL_RE = re.compile(r'Valor fixo R\$ ?[\d.]+,\d\d|\d+% limitado a R\$ ?[\d.]+,\d\d|--|-')


def grupos_do_cabecalho(txt):
    """Produtos em ORDEM, agrupados por coluna.

    Dentro de uma coluna os produtos vêm separados por '|' ou '/'
    ("PRATA | PRATA MAX | OURO", "ADVANCE 600 / 700"); entre colunas, por
    espaço. É o que distingue as colunas — o quadro não tem réguas próprias e
    o agrupamento MUDA entre a página de copart parcial e a de total.
    """
    t = re.sub(r'\s+', ' ', txt)
    grupos, atual, fim = [], [], 0
    for m in PRODS_RE.finditer(t):
        sep = t[fim:m.start()]
        if atual and ('|' not in sep and '/' not in sep):
            grupos.append(atual); atual = []
        atual.append(m.group(0)); fim = m.end()
    if atual: grupos.append(atual)
    # "ADVANCE 600 / 700" vira ADVANCE 600 + 700? o regex já separa; "700" sozinho não casa,
    # então o '/ 700' some — trata-se aqui
    saida = []
    for g in grupos:
        nomes = []
        for x in g:
            n = NOME_CAT.get(x)
            if isinstance(n, list): nomes += n
            elif n: nomes.append(n)
        saida.append(nomes)
    return saida


def parse(pg):
    ls = linhas(pg)
    cab = (pg.extract_text() or '').split('\n')
    praca = PRACA_MAP.get(cab[1].strip(), cab[1].strip()) if len(cab) > 1 else None
    tier = 'parcial' if 'COM COPARTICIPAÇÃO PARCIAL' in '\n'.join(cab[:7]) else 'total'

    i = next((k for k, r in enumerate(ls)
              if ne(' '.join(w['text'] for w in r)).startswith('PROCEDIMENTO')
              and any(x in ne(' '.join(w['text'] for w in r)) for x in ('PRATA', 'ADVANCE'))), None)
    if i is None:
        return praca, tier, {}, []

    # a caixa de ODONTOLOGIA é uma coluna fixa à direita; tudo dali para lá é outro assunto
    odo = [w['x0'] for r in ls for w in r
           if ne(w['text']).startswith('ODONTO') and w['x0'] > pg.width * 0.4]
    xmax = (min(odo) - 4) if odo else pg.width
    texto = lambda r: re.sub(r'\s+', ' ', ' '.join(w['text'] for w in r if w['x1'] <= xmax)).strip()

    grupos = grupos_do_cabecalho(texto(ls[i]))
    if not grupos:
        return praca, tier, {}, ['%s/%s: cabeçalho sem produtos' % (praca, tier)]

    prim = min((w['x0'] for w in ls[i] if ne(w['text']) != 'PROCEDIMENTO'), default=999)
    dados = {p: {} for g in grupos for p in g}
    avisos = []

    # ⚠️ A coluna de rótulos e a de valores ficam em alturas ligeiramente
    # diferentes, e agrupar a página inteira por `top` cruzava o rótulo de uma
    # linha com o valor da seguinte (visto nos arquivos de porte II). Então: as
    # linhas são definidas pelos VALORES, e o rótulo é buscado pelo centro.
    todos = [w for r in ls for w in r]
    base = ls[i][0]['top']
    vals_ws = [w for w in todos if prim - 2 <= w['x0'] and w['x1'] <= xmax
               and base < w['top'] < base + 70]
    linhas_val = []
    for w in sorted(vals_ws, key=lambda x: ((x['top'] + x['bottom']) / 2, x['x0'])):
        c = (w['top'] + w['bottom']) / 2
        if linhas_val and abs(c - linhas_val[-1][0]) <= 2.2:
            linhas_val[-1][1].append(w)
        else:
            linhas_val.append([c, [w]])

    rot_ws = [w for w in todos if w['x0'] < prim - 2 and base < w['top'] < base + 70]
    for centro, ws in linhas_val:
        perto = [w for w in rot_ws if abs((w['top'] + w['bottom']) / 2 - centro) <= 2.6]
        rot = ne(' '.join(w['text'] for w in sorted(perto, key=lambda x: x['x0'])))
        nome = next((n for a, n in PROCS if rot.startswith(a)), None)
        if not nome:
            continue
        corpo = re.sub(r'\s+', ' ', ' '.join(w['text'] for w in sorted(ws, key=lambda x: x['x0']))).strip()
        vs = VAL_RE.findall(corpo)
        if len(vs) != len(grupos):
            avisos.append('%s/%s/%s: %d valores para %d colunas'
                          % (praca, tier, nome, len(vs), len(grupos)))
            continue
        for g, v in zip(grupos, vs):
            for pr in g:
                dados[pr][nome] = None if v in ('-', '--') else v
    return praca, tier, dados, avisos


def main():
    res, avisos = {}, []
    for f in sorted(glob.glob(D + '*.pdf')):
        pdf = pdfplumber.open(f)
        for pg in pdf.pages:
            praca, tier, dados, av = parse(pg)
            avisos += av
            if not dados: continue
            for prod, d in dados.items():
                cur = res.setdefault(praca, {}).setdefault(prod, {})
                if tier in cur and cur[tier] != d:
                    avisos.append('%s · %s · %s: valor diferente entre arquivos' % (praca, prod, tier))
                cur[tier] = d
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print('praças: %d · blocos: %d -> %s' % (len(res), sum(len(v) for v in res.values()), OUT))
    if avisos:
        print('\navisos (%d):' % len(avisos))
        for a, q in collections.Counter(avisos).most_common(10): print('   %-86s x%d' % (a[:86], q))
    ex = res.get('SP / RMSP', {})
    print('\nSP / RMSP:')
    for p in ('Prata', 'Ouro', 'Ouro Max', 'Diamante', 'Diamante Max', 'Adv 600', 'Infinity'):
        d = ex.get(p)
        if not d: print('   %-14s —' % p); continue
        print('   %-14s parcial: cons=%-10s terap=%-20s | total: cons=%-26s intern=%s'
              % (p, (d.get('parcial') or {}).get('Consultas eletivas') or '—',
                 (d.get('parcial') or {}).get('Terapias especiais') or '—',
                 (d.get('total') or {}).get('Consultas eletivas') or '—',
                 (d.get('total') or {}).get('Internações') or '—'))


if __name__ == '__main__':
    main()
