# -*- coding: utf-8 -*-
"""Gera o bloco LAB_INI/LAB_FIM do index.html a partir dos PDFs de rede laboratorial.

Fonte: "REDE LAB NOTREDAME SP.pdf" e "REDE LAB NOTREDAME RJ.pdf" (material
comercial NotreDame, "Conheca os destaques da Rede").

Layout dos PDFs (identico nos dois, pagina deitada de 842pt):
  CIDADE | PRESTADOR | ADVANCE 600 | ADVANCE 700 | PREMIUM 900 | PREMIUM 900 CARE | INFINITY 100
Cidade e prestador tem varias palavras, entao NAO da para fatiar a linha de
texto por espaco ("CAMPOS DO JORDAO LABORATORIO SAO LUCAS" nao tem divisor).
A divisao e por COORDENADA X, que e fixa nos dois arquivos:
  cidade    x0 < 170 | prestador 170 <= x0 < 300 | marcas x0 >= 300
As 5 marcas ('X' credenciado, '-' nao) caem no mais proximo de 5 centros fixos.

Saida: reescreve o trecho entre /*LAB_INI*/ e /*LAB_FIM*/ no index.html com
  LAB_VIG   vigencia impressa no PDF
  LAB_COLS  os 5 produtos, no nome do material
  LAB_PRACA pracas com produto NotreDame -> uf + cidades (de rede_full.json),
            para o folder separar "cidades da praca" de "demais do estado"
  LAB       uf -> [[CIDADE, PRESTADOR, bitmask de 5 bits], ...]

Use --apply para gravar; sem a flag e simulacao.
"""
import sys, os, json, re, unicodedata, collections, shutil, datetime
sys.path[:] = [p for p in sys.path if p not in ('', '.', os.getcwd())]
import pdfplumber  # noqa: E402

PROJ = '/Users/marcoscorrea/comparativo-ppo/'
HTML = PROJ + 'index.html'
RFULL = PROJ + 'rede_full.json'
CAT = PROJ + 'catalog.json'
PDFS = {'SP': os.path.expanduser('~/Downloads/REDE LAB NOTREDAME SP.pdf'),
        'RJ': os.path.expanduser('~/Downloads/REDE LAB NOTREDAME RJ.pdf')}
APPLY = '--apply' in sys.argv

CENTROS = [329.0, 401.0, 469.0, 539.0, 617.0]
COLS = ['Advance 600', 'Advance 700', 'Premium 900', 'Premium 900 Care', 'Infinity 100']
X_CIDADE, X_PREST = 170.0, 300.0
RUIDO = ('As informações contidas', 'Laboratórios da rede', 'CIDADE PRESTADOR',
         'Conheça os destaques', 'Rede de')


def dea(s):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKD', s or '')
                  .encode('ascii', 'ignore').decode()).strip()


def linhas_de(pg, tol=3.0):
    rows = []
    for w in sorted(pg.extract_words(x_tolerance=1.5), key=lambda w: (w['top'], w['x0'])):
        for r in rows:
            if abs(r['top'] - w['top']) <= tol:
                r['w'].append(w); break
        else:
            rows.append({'top': w['top'], 'w': [w]})
    for r in rows:
        r['w'].sort(key=lambda w: w['x0'])
    return sorted(rows, key=lambda r: r['top'])


def parse(caminho):
    vig, saida = None, []
    with pdfplumber.open(caminho) as doc:
        for pg in doc.pages:
            txt = pg.extract_text() or ''
            m = re.search(r'Vig[eê]ncia:\s*([^\n|]+)', txt)
            if m and not vig:
                vig = m.group(1).strip()
            for r in linhas_de(pg):
                marcas = [w for w in r['w'] if w['text'] in ('X', '-') and w['x0'] >= X_PREST]
                if len(marcas) != 5:
                    continue
                cid = ' '.join(w['text'] for w in r['w'] if w['x0'] < X_CIDADE)
                pre = ' '.join(w['text'] for w in r['w'] if X_CIDADE <= w['x0'] < X_PREST)
                if not cid or not pre or any(s in cid or s in pre for s in RUIDO):
                    continue
                col = [None] * 5
                for w in marcas:
                    c = (w['x0'] + w['x1']) / 2
                    i = min(range(5), key=lambda k: abs(CENTROS[k] - c))
                    assert abs(CENTROS[i] - c) < 12, 'marca fora de coluna: %s (x=%.1f)' % (cid, c)
                    assert col[i] is None, 'duas marcas na mesma coluna: %s / %s' % (cid, pre)
                    col[i] = (w['text'] == 'X')
                assert all(v is not None for v in col), 'coluna vazia: %s / %s' % (cid, pre)
                saida.append((dea(cid).upper(), dea(pre).upper(), col))
    return vig, saida


def conferir(caminho, n):
    """Conta no TEXTO CRU as linhas com 5 marcas e compara com o parse por x.
    Duas leituras independentes do mesmo PDF: se divergirem, alguma linha se
    perdeu no fatiamento por coordenada."""
    rx = re.compile(r'(?:\s+[X-]){5}\s*$')
    bruto = 0
    with pdfplumber.open(caminho) as doc:
        for pg in doc.pages:
            for ln in (pg.extract_text() or '').split('\n'):
                if rx.search(ln) and not ln.startswith('CIDADE'):
                    bruto += 1
    assert bruto == n, '%s: texto cru tem %d linhas, o parse por x achou %d' % (
        os.path.basename(caminho), bruto, n)
    return bruto


def main():
    vigs, dados = set(), {}
    for uf, caminho in PDFS.items():
        assert os.path.exists(caminho), 'PDF ausente: %s' % caminho
        vig, linhas = parse(caminho)
        conferir(caminho, len(linhas))
        vigs.add(vig)
        # colapsa so a repeticao IDENTICA. Quando as marcas diferem as duas
        # linhas ficam: em Sao Paulo a fonte lista DELBONI duas vezes, com
        # coberturas complementares (Adv 600/700+900 Care numa, Premium 900+
        # 900 Care+Infinity na outra). Sao conjuntos de unidades distintos que
        # o PDF nao nomeia diferente — unir afirmaria um credenciamento que a
        # fonte nao da, e escolher uma esconderia metade da rede.
        vistos = {}
        for c, p, m in linhas:
            vistos[(c, p, tuple(m))] = (c, p, m)
        ordenado = sorted(vistos.values(), key=lambda e: (e[0], e[1]))
        dados[uf] = [[c, p, sum(1 << i for i in range(5) if m[i])] for c, p, m in ordenado]
        rep = [k for k, n in collections.Counter((c, p) for c, p, _ in ordenado).items() if n > 1]
        print('%s: %d linhas (texto cru confere) | %d cidades | vigencia %r'
              % (uf, len(ordenado), len({c for c, _, _ in ordenado}), vig))
        print('    por produto: %s' % {COLS[i]: sum(1 for _, _, m in ordenado if m[i]) for i in range(5)})
        print('    sem nenhum credenciamento: %d' % sum(1 for _, _, m in ordenado if not any(m)))
        if rep:
            print('    prestador repetido com cobertura diferente (as duas linhas ficam): %s'
                  % '; '.join('%s / %s' % k for k in rep))
    assert len(vigs) == 1, 'os dois PDFs tem vigencias diferentes: %s' % vigs
    vig = vigs.pop()

    # pracas que vendem NotreDame, com as cidades que cada uma atende
    cat = json.load(open(CAT))
    ppo = sorted({e['praca'] for e in cat
                  if str(e.get('label', '')).startswith(('Adv', 'Premium', 'Infinity'))})
    rf = json.load(open(RFULL))
    praca = {}
    for p in ppo:
        d = rf['pracas'].get(p)
        assert d, 'praca %r sem entrada em rede_full.json' % p
        assert d['uf'] in dados, 'praca %r e do UF %s, que nao tem PDF de laboratorio' % (p, d['uf'])
        cidades = sorted(set(d['cidades']) | {d['sede']} if d.get('sede') else set(d['cidades']))
        praca[p] = {'uf': d['uf'], 'c': cidades}
        n = sum(1 for c, _, _ in dados[d['uf']] if c in set(cidades))
        print('   %-28s %s  %3d lab na praca / %3d no estado'
              % (p, d['uf'], n, len(dados[d['uf']]) - n))

    j = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))
    bloco = ('/*LAB_INI*/const LAB_VIG=%s,LAB_COLS=%s,LAB_PRACA=%s,LAB=%s;/*LAB_FIM*/'
             % (j(vig), j(COLS), j(praca), j(dados)))

    t = open(HTML, encoding='utf-8').read()
    if '/*LAB_INI*/' in t:
        novo = re.sub(r'/\*LAB_INI\*/.*?/\*LAB_FIM\*/', lambda _: bloco, t, flags=re.S)
    else:
        anc = '/*ND_INI*/'
        assert t.count(anc) == 1, 'ancora %s nao encontrada uma vez' % anc
        novo = t.replace(anc, bloco + '\n' + anc)
    print('\nbloco LAB: %.1f KB | index.html %d -> %d bytes' % (len(bloco) / 1024, len(t), len(novo)))

    if APPLY:
        shutil.copy(HTML, HTML + '.bak_lab_' + datetime.datetime.now().strftime('%Y%m%d_%H%M'))
        open(HTML, 'w', encoding='utf-8').write(novo)
        print('GRAVADO: %s' % HTML)
    else:
        print('(simulacao — use --apply para gravar)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
