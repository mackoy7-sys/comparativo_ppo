#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parser da familia NDI MINAS (Adapt / Personal UP) — 5 pracas de MG.

Por que um parser proprio: nem o build_ago (Hapvida nacional), nem o build_set
(NDI Sede), nem o build_sul (PR/SC/RS) leem este layout — todos devolveram 0
entradas. As diferencas sao:
  - o cabecalho diz "PRODUTOS" (plural), nao "PRODUTO";
  - as paginas de PME trazem DUAS tabelas LADO A LADO na mesma faixa vertical
    (dois rotulos ACOMODACAO na mesma linha), uma por coparticipacao;
  - o "+ Odonto" vem da linha ASSISTENCIA (Medica1 = com desconto por contratar
    o odonto junto; Medica2 = sem), quando ela existe.

Cada tabela e delimitada horizontalmente pelo x do seu rotulo ACOMODACAO ate o
rotulo seguinte. Dentro dela, coluna de acomodacao, assistencia e valor sao
casados por INDICE (mesma licao da carga NDI: proximidade de x quebra quando ha
caixa lateral).

Saida: /tmp/mg_parsed.json  (praca -> lista de entradas), no formato do merge.
"""
import json, re, unicodedata, collections
import pdfplumber

DIR = '/Users/marcoscorrea/Downloads/OneDrive_4_08-09-2026/'
OUT = '/tmp/mg_parsed.json'
FILES = [
    ('20260908 a 20260930 - Super Simples.pdf', dict(vmin=2, vmax=29)),
    ('20260908 a 20260930 - PME.pdf', dict(vmin=30, vmax=99)),
]
# O Individual (Divinopolis) veio com vigencia 01/07-30/09, igual a anterior,
# e nao entra nesta carga.

BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38", "39 a 43",
         "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
ORDEM = ["00 A 18", "19 A 23", "24 A 28", "29 A 33", "34 A 38", "39 A 43",
         "44 A 48", "49 A 53", "54 A 58", "59 ANOS OU MAIS", "59 OU MAIS"]
NAME = {
    'PERSONAL UP NV': 'Personal UP',
    'PERSONAL UP': 'Personal UP',
    'ADAPT 300 SUL': 'Adapt 300 Sul',
    'ADAPT 300 ESTADUAL': 'Adapt 300 Estadual',
    'ADAPT 500 ESTADUAL': 'Adapt 500 Estadual',
}
PRACA_MAP = {'Poços De Caldas - MG': 'Poços de Caldas - MG'}

def deacc(s):
    return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()

def rows_of(page, tol=3.0):
    rows = []
    for w in sorted(page.extract_words(), key=lambda w: (w['top'], w['x0'])):
        for r in rows:
            if abs(r['top'] - w['top']) <= tol:
                r['w'].append(w); break
        else:
            rows.append({'top': w['top'], 'w': [w]})
    for r in rows:
        r['w'].sort(key=lambda w: w['x0'])
    return sorted(rows, key=lambda r: r['top'])

def city_of(page):
    for r in rows_of(page)[:6]:
        t = ' '.join(w['text'] for w in r['w']).strip()
        m = re.match(r'^([A-ZÀ-Ý][A-ZÀ-Ý \'\-\.]{2,40})\s*-\s*([A-Z]{2})$', t)
        if m:
            nome = ' '.join(p.capitalize() if p.lower() not in ('de', 'da', 'do', 'dos', 'das')
                            else p.lower() for p in m.group(1).strip().split())
            c = '%s - %s' % (nome, m.group(2))
            return PRACA_MAP.get(c, c)
    return None

def num(t):
    t = t.replace('.', '').replace(',', '.')
    try:
        return round(float(t), 2)
    except ValueError:
        return None

def merge_nums(ws):
    """Junta tokens numericos quebrados ('1' + '19,72' -> 119,72)."""
    out, i = [], 0
    toks = [w for w in ws if w['text'] != 'R$' and re.match(r'^[\d\.,]+$', w['text'])]
    while i < len(toks):
        t, x = toks[i]['text'], toks[i]['x0']
        while (i + 1 < len(toks) and (',' not in t or len(t.split(',')[-1]) < 2)
               and toks[i + 1]['x0'] - toks[i]['x1'] < 8):
            i += 1; t += toks[i]['text']
        v = num(t)
        if v is not None:
            out.append((v, x))
        i += 1
    return out

def banda_de(t):
    n = deacc(t).upper().strip()
    for b in ORDEM:
        if n.startswith(b):
            return '59 ou mais' if b.startswith('59') else b.title().replace('A', 'a')
    return None

def parse_page(page, praca, meta):
    rs = rows_of(page)
    lab = lambda r, p: [w for w in r['w'] if deacc(w['text']).upper().startswith(p)]
    r_prod = next((r for r in rs if lab(r, 'PRODUTO')), None)
    r_acom = next((r for r in rs if lab(r, 'ACOMODA')), None)
    if not (r_prod and r_acom):
        return []
    r_ass = next((r for r in rs if lab(r, 'ASSIST')), None)
    r_cop = next((r for r in rs if lab(r, 'COPARTICIPA')), None)

    # limites horizontais: um por rotulo ACOMODACAO
    marks = sorted(w['x0'] for w in lab(r_acom, 'ACOMODA'))
    faixas = [(marks[k], marks[k + 1] if k + 1 < len(marks) else 1e9) for k in range(len(marks))]

    out = []
    for x0, x1 in faixas:
        dentro = lambda w: x0 <= w['x0'] < x1
        acoms = [('Enfermaria' if deacc(w['text']).upper().startswith('ENFERM') else 'Apartamento')
                 for w in r_acom['w'] if dentro(w)
                 and deacc(w['text']).upper().startswith(('ENFERM', 'APART'))]
        if not acoms:
            continue
        xr = max(w['x1'] for w in r_acom['w'] if dentro(w)
                 and deacc(w['text']).upper().startswith(('ENFERM', 'APART'))) + 25
        dentro2 = lambda w: x0 <= w['x0'] < min(x1, xr)

        ass = [deacc(w['text']).upper().replace(' ', '') for w in (r_ass['w'] if r_ass else [])
               if dentro2(w) and deacc(w['text']).upper().startswith('MEDICA')]
        if ass and len(ass) != len(acoms):
            ass = []

        # nomes dos produtos: agrupa palavras da linha PRODUTOS por lacuna de x
        pw = [w for w in r_prod['w'] if dentro2(w)
              and not deacc(w['text']).upper().startswith('PRODUTO')]
        grupos, atual = [], []
        for w in pw:
            if atual and w['x0'] - atual[-1]['x1'] > 18:
                grupos.append(atual); atual = []
            atual.append(w)
        if atual:
            grupos.append(atual)
        prods = []
        for g in grupos:
            nome = deacc(' '.join(w['text'] for w in g)).upper().strip()
            nome = re.sub(r'\s+', ' ', nome)
            if nome in NAME:
                prods.append(NAME[nome])
        if not prods or len(acoms) % len(prods):
            continue
        por = len(acoms) // len(prods)

        cop_txt = ''
        if r_cop:
            cop_txt = deacc(''.join(w['text'] for w in r_cop['w'] if dentro(w))).upper().replace(' ', '')
        cop = 'Parcial' if 'PARCIAL' in cop_txt else 'Completa'

        precos = {}
        for r in rs:
            b = banda_de(' '.join(w['text'] for w in r['w'][:4]))
            if not b:
                continue
            # comeca depois do primeiro "R$": senao os digitos do rotulo da faixa
            # ("00 a 18") entram como se fossem preco
            ws = [w for w in r['w'] if dentro2(w)]
            k = next((j for j, w in enumerate(ws) if w['text'] == 'R$'), None)
            if k is None:
                continue
            vals = [v for v, x in merge_nums(ws[k:])]
            if len(vals) == len(acoms):
                precos[b] = vals
        if len(precos) < 10:
            continue

        for i, acom in enumerate(acoms):
            base = prods[i // por]
            label = base + (' + Odonto' if ass and ass[i].endswith('1') else '')
            e = dict(operadora='Hapvida', plano=base, label=label, acomodacao=acom,
                     coparticipacao=cop, categoria='Geral', tipo='Empresarial',
                     mei=False, praca=praca,
                     precos={b: precos[b][i] for b in BANDS})
            e.update(meta)
            out.append(e)
    return out

def main():
    result = collections.defaultdict(list)
    for fn, meta in FILES:
        with pdfplumber.open(DIR + fn) as doc:
            for pg in doc.pages:
                c = city_of(pg)
                if not c:
                    continue
                ents = parse_page(pg, c, meta)
                if ents:
                    result[c].extend(ents)
                    print('%-42s %-24s %d entradas' % (fn[:42], c, len(ents)))
    json.dump(result, open(OUT, 'w'), ensure_ascii=False, indent=1)
    print('\nTotal: %d entradas em %d praças -> %s'
          % (sum(len(v) for v in result.values()), len(result), OUT))

    # spot-checks contra valores que eu li na propria pagina
    def get(praca, label, acom, vmin, banda='00 a 18'):
        for e in result.get(praca, []):
            if e['label'] == label and e['acomodacao'] == acom and e['vmin'] == vmin:
                return e['precos'][banda]
    checks = [
        ('Belo Horizonte - MG', 'Adapt 300 Estadual', 'Enfermaria', 2, 119.72),
        ('Belo Horizonte - MG', 'Adapt 300 Estadual', 'Apartamento', 2, 155.25),
        ('Belo Horizonte - MG', 'Adapt 500 Estadual', 'Enfermaria', 2, 132.85),
        ('Belo Horizonte - MG', 'Adapt 300 Estadual + Odonto', 'Enfermaria', 30, 106.61),
        ('Belo Horizonte - MG', 'Adapt 300 Estadual', 'Enfermaria', 30, 146.59),
        ('Belo Horizonte - MG', 'Adapt 500 Estadual + Odonto', 'Apartamento', 30, 153.94),
    ]
    ok = True
    for praca, label, acom, vmin, esperado in checks:
        got = get(praca, label, acom, vmin)
        s = 'OK ' if got == esperado else 'FALHOU'
        if got != esperado:
            ok = False
        print('  %s %-30s %-12s vmin=%-3d esperado=%8.2f obtido=%s'
              % (s, label, acom, vmin, esperado, got))
    print('spot-checks:', 'OK' if ok else 'FALHAS')

if __name__ == '__main__':
    main()
