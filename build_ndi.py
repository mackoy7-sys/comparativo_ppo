#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga NDI Sede (ago/2026): novas praças SP-interior/litoral + Rio de Janeiro no catalog.json do cotador.
Fontes (PDFs ~/Downloads/OneDrive_1_11-08-2026):
  - SS 2-29 Demais Empresas  -> Empresarial nao-MEI, vmin2/vmax29, copart Completa
  - SS 2-29 MEI              -> Empresarial MEI,     vmin2/vmax29, copart Completa
  - PME Compulsorio (30-99)  -> Empresarial nao-MEI, vmin30/vmax99, copart Completa
  - Individual NDI Sede      -> Individual (PF), copart Parcial+Completa, Enf/Apart
  - Individual Ambulatorial  -> Individual (PF), acomodacao Ambulatorial, Parcial+Completa
Regras: PPO usa só o grupo reembolso TOTAL (mesmo padrão do SP já carregado); produtos
SMART UP 50+ e REFERÊNCIA são pulados (mesmo padrão da carga de julho).
Valida os preços parseados de São Paulo contra o catálogo existente antes de gravar.
"""
import pdfplumber, json, re, sys, unicodedata

D = '/Users/marcoscorrea/Downloads/OneDrive_1_11-08-2026/'
CATALOG = '/Users/marcoscorrea/comparativo-ppo/catalog.json'
BANDS = ["00 a 18","19 a 23","24 a 28","29 a 33","34 a 38","39 a 43","44 a 48","49 a 53","54 a 58","59 ou mais"]

SKIP_PRODUCTS = {'SMART UP 50+', 'SMART RIO 50+', 'REFERENCIA', 'REFERÊNCIA', 'BASIC', 'BASIC REFERENCIA'}
NAME_MAP = {
    'NOSSO MEDICO RMSP': ('Nosso Médico RMSP','Nosso Médico'),
    'NOSSO MEDICO RIO': ('Nosso Médico Rio','Nosso Médico'),
    'NOSSO MEDICO': ('Nosso Médico','Nosso Médico'),
    'SMART UP': ('Smart UP','Smart UP'),
    'SMART RIO': ('Smart Rio','Smart Rio'),
    'SMART FLEX SP': ('Smart Flex','Smart Flex'),
    'SMART FLEX': ('Smart Flex','Smart Flex'),
    'SMART PRIME': ('Smart Prime','Smart Prime'),
    'SMART 200 RIO': ('Smart 200 Rio','Smart 200 Rio'),
    'SMART 300': ('Smart 300','Smart 300'),
    'SMART 500': ('Smart 500','Smart 500'),
    'ADVANCE 600': ('600','Adv 600'),
    'ADVANCE 700': ('700','Adv 700'),
    'PREMIUM 900 (CARE)': ('900 Care','Premium 900 Care'),
    'PREMIUM 900': ('900','Premium 900'),
    'INFINITY 1000.11': ('Infinity','Infinity'),
    'INFINITY': ('Infinity','Infinity'),
}


ANS_EMP = {
    '507.184/25-4': ('Nosso Médico RMSP','Nosso Médico','Enfermaria'),
    '507.188/25-7': ('Nosso Médico RMSP','Nosso Médico','Apartamento'),
    '498.797/24-7': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '498.800/24-1': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '498.806/24-0': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '498.808/24-6': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '508.572/26-1': ('Smart UP','Smart UP','Enfermaria'),
    '508.571/26-3': ('Smart UP','Smart UP','Apartamento'),
    '508.598/26-5': ('Smart Flex','Smart Flex','Enfermaria'),
    '508.599/26-3': ('Smart Flex','Smart Flex','Apartamento'),
    '484.966/20-3': ('Smart Prime','Smart Prime','Enfermaria'),
    '484.964/20-7': ('Smart Prime','Smart Prime','Apartamento'),
    '497.299/23-6': ('Smart 200 Rio','Smart 200 Rio','Enfermaria'),
    '486.577/20-4': ('Smart 300','Smart 300','Enfermaria'),
    '474.448/15-9': ('Smart 500','Smart 500','Enfermaria'),
    '474.445/15-4': ('Smart 500','Smart 500','Apartamento'),
    '474.439/15-0': ('600','Adv 600','Enfermaria'),
    '474.438/15-1': ('600','Adv 600','Apartamento'),
    '474.341/15-5': ('700','Adv 700','Enfermaria'),
    '474.340/15-7': ('700','Adv 700','Apartamento'),
    '476.795/16-1': ('900 Care','Premium 900 Care','Apartamento'),
    '474.424/15-1': ('900','Premium 900','Apartamento'),
    '482.848/19-8': ('Infinity','Infinity','Apartamento'),
    '408.035/99-1': None,  # Basic / Referencia — nao carregado
}

def deacc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def get_rows(page, tol=3.2):
    words = page.extract_words(keep_blank_chars=False)
    rows = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        for r in rows:
            if abs(r['top'] - w['top']) <= tol:
                r['words'].append(w); break
        else:
            rows.append({'top': w['top'], 'words': [w]})
    for r in rows:
        r['words'].sort(key=lambda w: w['x0'])
    rows.sort(key=lambda r: r['top'])
    return rows

def row_text(r):
    return ' '.join(w['text'] for w in r['words'])

def city_of(page):
    rows = get_rows(page)
    for r in rows[:6]:
        t = row_text(r)
        m = re.match(r'^([A-Za-zÀ-ÿ\. ]+?)\s*-\s*([A-Z]{2})$', t.strip())
        if m:
            return f'{m.group(1).strip()} - {m.group(2)}'
    return None

def merge_values(words):
    """Junta tokens numericos quebrados ('2' + '27,82' -> 227,82). Retorna [(valor, x0)]."""
    toks = [w for w in words if w['text'] not in ('R$',) and re.match(r'^[\d\.,]+$', w['text'])]
    vals = []
    i = 0
    def incomplete(t):
        if ',' not in t: return True
        return len(t.split(',')[-1]) < 2
    while i < len(toks):
        t = toks[i]['text']; x = toks[i]['x0']
        while i + 1 < len(toks) and incomplete(t) and (toks[i+1]['x0'] - toks[i]['x1']) < 8:
            t += toks[i+1]['text']; i += 1
        if ',' in t and re.search(r'\d', t):
            vals.append((float(t.replace('.','').replace(',','.')), x))
        i += 1
    return vals

SQ_FAIXA_RE = re.compile(r'^(00a18|19a23|24a28|29a33|34a38|39a43|44a48|49a53|54a58|59)(anos)?(oumais)?', re.I)
def faixa_of(t):
    m = FAIXA_RE.match(t)
    if m:
        fx = m.group(1)
        return '59 ou mais' if fx == '59' else fx
    sq = t.replace(' ', '')[:20]
    m = SQ_FAIXA_RE.match(sq)
    if m:
        fx = m.group(1)
        return '59 ou mais' if fx == '59' else fx[:2] + ' a ' + fx[3:]
    return None
FAIXA_RE = re.compile(r'^(00 a 18|19 a 23|24 a 28|29 a 33|34 a 38|39 a 43|44 a 48|49 a 53|54 a 58|59)( anos| ANOS)?( ou mais| OU MAIS)?', re.I)

def parse_price_tables(page, xlimit=99999):
    """Extrai tabelas da pagina: cada tabela = dict(products=[(nome,x0,x1)], cols=[x...], acoms=[...], prices={faixa:[...]}).
    Colunas ancoradas na linha ACOMODAÇÃO. So considera words com x0<xlimit (corta caixas laterais)."""
    rows = get_rows(page)
    tables = []
    cur = None
    recent = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        if not ws: continue
        first = ws[0]['text']
        t = ' '.join(w['text'] for w in ws)
        if first != 'PRODUTO':
            recent.append(t)
        if first == 'PRODUTO':
            hdr = deacc(''.join(recent[-3:])).upper().replace(' ', '')
            cur = {'prod_words': ws[1:], 'acoms': None, 'cols': None, 'prices': {}, 'hdr': hdr}
            tables.append(cur)
        elif cur is not None and first.startswith('ACOMODAÇ') and cur['acoms'] is None:
            cols = [w for w in ws[1:] if re.match(r'^(ENFERM|APART|AMBULAT|SEM)', w['text'])]
            # 'SEM ACOMODAÇÃO' vem como 'SEM'+'ACOMODAÇÃO' ou embolado
            acoms = []
            merged = []
            skip = False
            for i, w in enumerate(cols):
                if skip: skip = False; continue
                txt = w['text']
                if txt == 'SEM' or txt.startswith('SE'):
                    acoms.append('Ambulatorial'); merged.append(w); skip = (i+1 < len(cols) and cols[i+1]['text'].startswith('ACOMODAÇ'))
                elif txt.startswith('ENFERM'):
                    acoms.append('Enfermaria'); merged.append(w)
                elif txt.startswith('APART'):
                    acoms.append('Apartamento'); merged.append(w)
                elif txt.startswith('AMBULAT'):
                    acoms.append('Ambulatorial'); merged.append(w)
            cur['acoms'] = acoms
            cur['cols'] = [w['x0'] for w in merged]
        elif cur is not None and first == 'REGISTRO' and cur.get('codes') is None:
            cur['codes'] = [(w['text'], w['x0']) for w in ws if re.match(r'^\d{3}\.\d{3}/\d{2}-\d$', w['text'])]
        elif cur is not None and cur['acoms'] and faixa_of(t):
            faixa = faixa_of(t)
            vals = merge_values(ws)
            if vals and faixa not in cur['prices']:
                cur['prices'][faixa] = vals
    return [t for t in tables if t['acoms'] and len(t['prices']) == 10]

def product_spans(prod_words):
    """Agrupa words do cabecalho PRODUTO em nomes por gap>28px. Retorna [(nome, x0, x1)]."""
    spans = []
    cur = None
    for w in prod_words:
        if cur and (w['x0'] - cur[2]) < 18:
            cur[0] += ' ' + w['text']; cur[2] = w['x1']
        else:
            if cur: spans.append(tuple(cur))
            cur = [w['text'], w['x0'], w['x1']]
    if cur: spans.append(tuple(cur))
    # des-espacar (S M A R T U P -> SMART UP nao ocorre aqui; nomes ja vem por palavra)
    out = []
    for name, a, b in spans:
        n = re.sub(r'\s+', ' ', name).strip()
        out.append((n, a, b))
    return out

def assign_columns(table):
    """Atribui cada coluna (x) a um produto pelos limites entre spans. Retorna lista de (produto, acom, idx_col)."""
    spans = product_spans(table['prod_words'])
    bounds = []
    for i in range(len(spans) - 1):
        bounds.append((spans[i][2] + spans[i+1][1]) / 2)
    cols = table['cols']
    out = []
    for ci, x in enumerate(cols):
        pi = 0
        for b in bounds:
            if x + 12 > b: pi += 1
        pi = min(pi, len(spans) - 1)
        out.append((spans[pi][0], table['acoms'][ci], ci))
    return out

def col_prices(table, ci):
    """Preços da coluna ci por faixa (valores ordenados por x)."""
    out = {}
    ncols = len(table['cols'])
    for faixa, vals in table['prices'].items():
        vs = sorted(vals, key=lambda v: v[1])
        if len(vs) != ncols:
            # associar por proximidade da ancora da coluna
            anchor = table['cols'][ci]
            best = min(vs, key=lambda v: abs(v[1] - anchor - 15))
            out[faixa] = best[0]
        else:
            out[faixa] = vs[ci][0]
    return out

def norm_product(name):
    n = deacc(name.upper()).strip()
    n = re.sub(r'\s+', ' ', n)
    return n


ANS_DICT = {
    '507.439/26-8': ('Nosso Médico RMSP','Nosso Médico','Enfermaria'),
    '507.442/26-8': ('Nosso Médico RMSP','Nosso Médico','Apartamento'),
    '498.746/24-2': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '498.749/24-7': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '498.752/24-7': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '498.745/24-4': ('Nosso Médico','Nosso Médico','Enfermaria'),
    '507.049/25-0': ('Smart UP','Smart UP','Enfermaria'),
    '507.048/25-1': ('Smart Rio','Smart Rio','Enfermaria'),
    '507.583/26-1': ('Smart UP','Smart UP','Ambulatorial'),
    '507.585/26-8': ('Smart Rio','Smart Rio','Ambulatorial'),
    '507.586/26-6': None,  # Smart UP 50+ (nao carregado)
    '507.584/26-0': None,  # Smart Rio 50+ (nao carregado)
    '432.753/00-5': None,  # Referencia (nao carregado)
}
ANS_RE = re.compile(r'^\d{3}\.\d{3}/\d{2}-\d$')

def parse_ind_page(page, praca, is_amb):
    XL = 370 if is_amb else 99999
    """Tabelas do Individual: ancora por REGISTRO ANS; copart por grupos (repeticao de codigo)."""
    rows = get_rows(page)
    out = []
    last_cop_spans = None
    i = 0
    while i < len(rows):
        ws = [w for w in rows[i]['words'] if w['x0'] < XL]
        if not ws:
            i += 1; continue
        first = ws[0]['text']
        t_sq = deacc(' '.join(w['text'] for w in ws)).upper()
        if first.startswith('COPARTICIPAÇ') and ('PARCIAL' in t_sq or 'COM COPARTICIPACAO' in t_sq or 'REFER' in t_sq):
            # spans de copart: sequencia de rotulos
            spans = []
            toks = ws[1:]
            j = 0
            while j < len(toks):
                up = deacc(toks[j]['text']).upper()
                if up in ('COPART','COPARTICIPACAO') and j+1 < len(toks) and deacc(toks[j+1]['text']).upper() == 'PARCIAL':
                    spans.append('Parcial'); j += 2; continue
                if up == 'COM':
                    spans.append('Completa'); j += 2; continue
                if up in ('SEM','REFERENCIA'):
                    spans.append('Sem'); j += 2 if up=='SEM' else 1; continue
                j += 1
            if spans: last_cop_spans = spans
            i += 1; continue
        if first == 'REGISTRO' and len(ws) > 2 and any(ANS_RE.match(w['text']) for w in ws):
            codes = [(w['text'], w['x0']) for w in ws if ANS_RE.match(w['text'])]
            # grupos: novo grupo quando codigo repete ou codigo=Referencia
            groups = []
            cur = []
            seen = set()
            for c, x in codes:
                is_ref = ANS_DICT.get(c, 'MISS') is None and c.startswith('432.')
                if (c in seen) or (is_ref and cur):
                    groups.append(cur); cur = []; seen = set()
                cur.append((c, x)); seen.add(c)
                if is_ref:
                    groups.append(cur); cur = []; seen = set()
            if cur: groups.append(cur)
            # precos: proximas linhas de faixa
            prices = {}
            k = i + 1
            while k < len(rows) and len(prices) < 10:
                wsk = [w for w in rows[k]['words'] if w['x0'] < XL]
                tk = ' '.join(w['text'] for w in wsk)
                faixa = faixa_of(tk)
                if faixa:
                    vals = merge_values(wsk)
                    if vals and faixa not in prices:
                        prices[faixa] = sorted(vals, key=lambda v: v[1])
                k += 1
                if k - i > 40: break
            ncols = len(codes)
            if len(prices) == 10 and last_cop_spans:
                spans = list(last_cop_spans)
                if len(groups) != len(spans):
                    print(f'  !! {praca}: grupos({len(groups)}) != spans({len(spans)}) {spans} — pagina pulada')
                else:
                    flat = []
                    for gi, grp in enumerate(groups):
                        for c, x in grp:
                            flat.append((c, spans[gi]))
                    for ci, (code, cop) in enumerate(flat):
                        info = ANS_DICT.get(code, 'MISS')
                        if info == 'MISS':
                            print(f'  !! codigo ANS desconhecido {code} em {praca}'); continue
                        if info is None or cop == 'Sem':
                            continue
                        plano, label, acom = info
                        pr = {}
                        ok = True
                        for faixa, vals in prices.items():
                            if len(vals) == ncols:
                                pr[faixa] = vals[ci][0]
                            else:
                                ok = False
                        if not ok:
                            print(f'  !! {praca}: contagem de valores != colunas ({code})'); continue
                        out.append(dict(plano=plano, label=label + ' (PF)',
                                        acomodacao=acom, coparticipacao=cop, precos=pr))
            i = k; continue
        i += 1
    return out

def entries_from_page(page, kind, praca, page_copart='Completa'):
    """kind: 'emp' (SS/PME: tudo Completa; PPO dedupe 1a ocorrencia) | 'ind' | 'amb'"""
    out = []
    xlimit = 780 if kind == 'emp' else 640
    tables = parse_price_tables(page, xlimit=xlimit)
    if kind == 'emp':
        seen = set()
        for tb in tables:
            hdr = tb.get('hdr','')
            if 'REEMBOLSOPARCIAL' in hdr and 'REEMBOLSOTOTAL' not in hdr:
                continue  # quadro so de reembolso parcial
            codes = tb.get('codes') or []
            if not codes:
                # fallback: identificar produtos pelo cabecalho (SS 1 Vida nao imprime registros)
                for prod, acom, ci in assign_columns(tb):
                    pn = norm_product(prod)
                    if pn in SKIP_PRODUCTS: continue
                    if pn not in NAME_MAP:
                        print(f'  !! produto desconhecido: "{pn}" em {praca} — pulado'); continue
                    plano, label = NAME_MAP[pn]
                    key = (label, acom)
                    if key in seen: continue
                    seen.add(key)
                    out.append(dict(plano=plano, label=label, acomodacao=acom,
                                    coparticipacao=page_copart, precos=col_prices(tb, ci)))
                continue
            for code, cx in codes:
                info = ANS_EMP.get(code, 'MISS')
                if info == 'MISS':
                    print(f'  !! codigo ANS emp desconhecido {code} em {praca}'); continue
                if info is None: continue
                plano, label, acom = info
                key = (label, acom)
                if key in seen:
                    # codigo repetido: ou grupo reembolso parcial (pular) ou typo no PDF
                    # (mesmo codigo em coluna de outra acomodacao — ex.: Santos SS1 NM)
                    ai = min(range(len(tb['cols'])), key=lambda i: abs(tb['cols'][i] - cx))
                    row_acom = tb['acoms'][ai] if abs(tb['cols'][ai] - cx) < 55 else acom
                    if row_acom == acom: continue
                    acom = row_acom
                    key = (label, acom)
                    if key in seen: continue
                    print(f'  ⚠ {praca}: codigo {code} repetido em coluna {acom} (typo no PDF — usando acomodacao da coluna)')
                seen.add(key)
                # precos por proximidade do x do codigo
                pr = {}
                bad = False
                for faixa, vals in tb['prices'].items():
                    best = min(vals, key=lambda v: abs(v[1] - cx))
                    if abs(best[1] - cx) > 60: bad = True
                    pr[faixa] = best[0]
                if bad:
                    print(f'  !! {praca}: valores distantes p/ {label} {acom} — pulado'); continue
                out.append(dict(plano=plano, label=label, acomodacao=acom,
                                coparticipacao=page_copart, precos=pr))
    else:
        out = parse_ind_page(page, praca, kind == 'amb')
    return out

def load_all():
    files = {
        'ss_demais': ('20260801 a 20260831 - Super Simples 2 a 29 vidas - Demais Empresas.pdf', 'emp', dict(mei=False, vmin=2, vmax=29, tipo='Empresarial')),
        'ss_mei':    ('20260801 a 20260930 - Super Simples 2 a 29 vidas - MEI.pdf', 'emp', dict(mei=True, vmin=2, vmax=29, tipo='Empresarial')),
        'pme_comp':  ('20260801 a 20260831 - PME - Compulsório.pdf', 'emp', dict(mei=False, vmin=30, vmax=99, tipo='Empresarial', contratacao='Compulsório')),
        'pme_adesao':('20260801 a 20260831 - PME - Adesão.pdf', 'emp', dict(mei=False, vmin=30, vmax=99, tipo='Empresarial', contratacao='Adesão')),
        'ss_1vida':  ('20260801 a 20260831 - Super Simples 1 Vida.pdf', 'emp', dict(mei=False, vmin=1, vmax=1, tipo='Empresarial')),
        'ind':       ('20260701 a 20260930 - Individual - NDI Sede - Sem Desconto.pdf', 'ind', dict(mei=False, tipo='Individual')),
        'amb':       ('20260701 a 20260930 - Individual Ambulatorial - NDI Sede - Sem Desconto.pdf', 'amb', dict(mei=False, tipo='Individual')),
    }
    result = {}  # praca -> list of entries
    for tag, (fn, kind, meta) in files.items():
        pdf = pdfplumber.open(D + fn)
        seen_pages = {}
        for page in pdf.pages:
            c = city_of(page)
            if not c: continue
            txt = page.extract_text() or ''
            if 'REAJUSTE POR MUDANÇA' in txt[:600]: continue
            top = deacc(txt[:400]).upper().replace(' ', '')
            hdr_copart = 'Parcial' if 'COMCOPARTICIPACAOPARCIAL' in top else 'Completa'
            if kind == 'emp':
                # ordem fixa por cidade: 1a pagina de preco = Parcial, 2a = Total
                n = seen_pages.get(c, 0); seen_pages[c] = n + 1
                page_copart = 'Parcial' if n == 0 else 'Completa'
                if page_copart != hdr_copart:
                    print(f'  ⚠ {tag} {c}: cabecalho diz {hdr_copart} mas ordem indica {page_copart} (typo no PDF — usando ordem)')
            else:
                page_copart = hdr_copart
            ents = entries_from_page(page, kind, c, page_copart)
            if not ents: continue
            for e in ents:
                e.update(meta)
                e['praca'] = c
                e['fonte'] = tag
            result.setdefault(c, []).extend(ents)
            print(f'{tag}: {c}: {len(ents)} entradas')
    return result

if __name__ == '__main__':
    result = load_all()
    json.dump(result, open('/tmp/ndi_parsed.json', 'w'), ensure_ascii=False, indent=1)
    print('\nPraças:', {k: len(v) for k, v in result.items()})
