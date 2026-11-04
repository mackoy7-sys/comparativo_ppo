# -*- coding: utf-8 -*-
"""SP/RMSP - Super Simples 2 a 29 vidas - bloco COM COPARTICIPACAO TOTAL (Completa).

Por que um script so para esta pagina: nela o PDF embaralha o texto — as linhas
SEGMENTACAO / ACOMODACAO / REGISTRO ANS saem interleavadas caractere a caractere
com o texto da caixa lateral de desconto promocional, e 6 das 10 faixas etarias
tambem. Por isso o build_set.py so conseguiu ler o 1o bloco (Parcial) e o
catalogo ficou com as 8 entradas Completa existindo SO na versao MEI.

A saida aqui nao depende do texto embaralhado: ancora no CÓD. INTERNO 41722
(1a coluna do bloco), pega as linhas de faixa por proximidade vertical e junta os
caracteres SEM espaco antes de aplicar o regex de R$ — o embaralhamento quebra as
palavras, mas nao troca a ORDEM em x, que e o que importa.

Saida: /tmp/sp229_parsed.json (formato do scratchpad/merge_set.py)
"""
import json, re, collections
import pdfplumber

PDF = ('/Users/marcoscorrea/Downloads/OneDrive_5_08-09-2026/'
       '20260908 a 20260930 - Super Simples 2 a 29 vidas - Demais Empresas [HMO].pdf')
OUT = '/tmp/sp229_parsed.json'
PRACA = 'SP / RMSP'
ANCORA = '41722'          # cod. interno do Nosso Medico RMSP Enfermaria, bloco Completa
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38", "39 a 43",
         "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
# ordem das 8 colunas, conforme a linha PRODUTO (top=125.3) e ACOMODACAO (134.4)
COLS = [('Nosso Médico RMSP', 'Nosso Médico', 'Enfermaria'),
        ('Nosso Médico RMSP', 'Nosso Médico', 'Apartamento'),
        ('Smart UP', 'Smart UP', 'Enfermaria'),
        ('Smart UP', 'Smart UP', 'Apartamento'),
        ('Smart Flex', 'Smart Flex', 'Enfermaria'),
        ('Smart Flex', 'Smart Flex', 'Apartamento'),
        ('Smart Prime', 'Smart Prime', 'Enfermaria'),
        ('Smart Prime', 'Smart Prime', 'Apartamento')]
RE_VAL = re.compile(r'R\$([\d]{1,3}(?:\.?\d{3})*,\d{2})')
# rotulo da faixa com os caracteres colados (o PDF separa "0 0 a 1 8 a n o s")
RE_BANDA = re.compile(r'^(\d\d)a(\d\d)anos') 
RE_59 = re.compile(r'^59anosoumais')

def num(s):
    return round(float(s.replace('.', '').replace(',', '.')), 2)

def linhas(ws, y0, y1, tol=0.6):
    """Agrupa palavras em linhas com tolerancia FINA: nesta pagina o rotulo da
    faixa e os precos ficam a ~0.4pt de distancia mas sao linhas distintas; a
    tolerancia 3.0 do parser normal funde tres faixas numa so."""
    rows = []
    for w in sorted(ws, key=lambda w: (w['top'], w['x0'])):
        if not (y0 <= w['top'] <= y1):
            continue
        for r in rows:
            if abs(r['top'] - w['top']) <= tol:
                r['w'].append(w); break
        else:
            rows.append({'top': w['top'], 'w': [w]})
    for r in rows:
        r['w'].sort(key=lambda w: w['x0'])
    return sorted(rows, key=lambda r: r['top'])

def main():
    with pdfplumber.open(PDF) as doc:
        pg = doc.pages[0]
        txt = pg.extract_text() or ''
        ws = pg.extract_words(x_tolerance=1.2)
    assert 'São Paulo - SP' in txt, 'pagina 1 nao e São Paulo'
    anc = [w for w in ws if w['text'] == ANCORA]
    assert len(anc) == 1, 'ancora %s encontrada %d vezes' % (ANCORA, len(anc))
    y = anc[0]['top']

    # a caixa lateral de desconto comeca em x~560; fora dela so ha o quadro de precos
    corpo = [w for w in ws if w['x0'] < 560]
    # o rotulo da faixa e os 8 precos saem na MESMA linha na maior parte das
    # faixas, mas em "49 a 53" e "54 a 58" o rotulo fica numa linha e os precos
    # na seguinte — dai o "banda corrente" em vez de casar por posicao.
    tab, banda = {}, None
    for r in linhas(corpo, y, y + 50):
        s = ''.join(w['text'] for w in r['w']).replace(' ', '')
        m = RE_BANDA.match(s)
        if m:
            banda = '%s a %s' % (m.group(1), m.group(2))
        elif RE_59.match(s):
            banda = '59 ou mais'
        vals = [num(v) for v in RE_VAL.findall(s)]
        if banda and len(vals) == len(COLS) and banda not in tab:
            tab[banda] = vals
    faltou = [b for b in BANDS if b not in tab]
    assert not faltou, 'faixas nao lidas: %s' % faltou

    res = collections.defaultdict(list)
    for i, (plano, label, acom) in enumerate(COLS):
        res[PRACA].append(dict(
            operadora='Hapvida', plano=plano, label=label, acomodacao=acom,
            coparticipacao='Completa', categoria='Geral', tipo='Empresarial',
            mei=False, praca=PRACA, vmin=2, vmax=29, alinhado=True,
            precos={b: tab[b][i] for b in BANDS}))
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=1)

    print('=== BLOCO COM COPARTICIPACAO TOTAL — %s — 2 a 29 vidas' % PRACA)
    print('%-20s %-12s ' % ('produto', 'acom') + ' '.join('%9s' % b for b in BANDS))
    for i, (plano, label, acom) in enumerate(COLS):
        print('%-20s %-12s ' % (label, acom) + ' '.join('%9.2f' % tab[b][i] for b in BANDS))

    # spot-checks contra as 4 faixas que o extract_text() devolve limpas
    checks = [('44 a 48', [195.46, 244.32, 234.91, 293.66, 284.38, 355.50, 410.35, 434.52]),
              ('49 a 53', [254.10, 317.62, 305.39, 381.76, 369.70, 462.16, 496.16, 525.38]),
              ('54 a 58', [330.33, 412.90, 397.02, 496.30, 480.62, 600.82, 620.60, 657.15]),
              ('59 ou mais', [476.10, 595.11, 572.21, 715.30, 692.70, 865.94, 987.37, 1045.52])]
    ok = True
    for b, esp in checks:
        got = tab[b]
        if got != esp:
            ok = False
        print('  %s %-11s %s' % ('OK ' if got == esp else 'FALHOU', b, got))
    print('spot-checks:', 'OK' if ok else 'FALHAS')

if __name__ == '__main__':
    main()
