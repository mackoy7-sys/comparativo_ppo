#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga Região Sul (ago/2026): Clinipam PR/SC + CCG RS no catalog.json do cotador.
Fontes: ~/Downloads/OneDrive_3_12-08-2026 (PR/SC: Balneário Camboriú, Maringá, Londrina, Curitiba)
        ~/Downloads/OneDrive_4_12-08-2026 (RS: Canoas, Novo Hamburgo, São Leopoldo, Porto Alegre)
Layout Sul: preço + reajuste NA MESMA página (reajuste à direita — clipar pelo x do título
"REAJUSTE"); tabelas por produto (banner letras espaçadas); subcolunas Médica¹ (com desconto
por odonto → label "+ Odonto") e Médica² (cheio); copart Parcial/Completa lado a lado;
segmentação AMB (S/ACOM→Ambulatorial), AMB+HOSP (→ " s/ Obstetrícia" quando o produto também
tem variante OBST) e AMB+HOSP+OBST; colunas ancoradas na linha CÓD. INTERNO.
Pulados: Referência, Própria, colunas odontológicas.
"""
import pdfplumber, json, re, unicodedata, os

DEBUG = bool(os.environ.get('SUL_DEBUG'))

BANDS = ["00 a 18","19 a 23","24 a 28","29 a 33","34 a 38","39 a 43","44 a 48","49 a 53","54 a 58","59 ou mais"]

def deacc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def sq(s):
    return deacc(s).upper().replace(' ', '')

PRODUCTS = {  # squash -> nome
    'NOSSOMEDICO': 'Nosso Médico',
    'NOSSOPLANO': 'Nosso Plano',
    'NOSSOPLANO-AMBULATORIAL': 'Nosso Plano',
    'NOSSOPLANOAMBULATORIAL': 'Nosso Plano',
    'PLENO': 'Pleno',
    'POP': 'Pop',
    'POPVALEDOSSINOS': 'Pop Vale dos Sinos',
    'POPESTADUAL': 'Pop Estadual',
}
SKIP_SEGM = ('REFERENCIA', 'ODONTOLOGICO', 'PROPRIO')

FAIXA_SQ = re.compile(r'^(00A18|19A23|24A28|29A33|34A38|39A43|44A48|49A53|54A58|59)(ANOS)?(OUMAIS)?')

def get_rows(page, tol=3.2):
    words = page.extract_words(keep_blank_chars=False, x_tolerance=1.2)
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

def merge_values(words):
    toks = [w for w in words if w['text'] != 'R$' and re.match(r'^[\d\.,]+$', w['text'])]
    def inc(t):
        return ',' not in t or len(t.split(',')[-1]) < 2
    vals = []; i = 0
    while i < len(toks):
        t = toks[i]['text']; x = toks[i]['x0']
        while i + 1 < len(toks) and inc(t) and (toks[i+1]['x0'] - toks[i]['x1']) < 8:
            t += toks[i+1]['text']; i += 1
        if ',' in t and re.search(r'\d', t):
            vals.append((float(t.replace('.', '').replace(',', '.')), x))
        i += 1
    return vals

def spans_from_tokens(ws, kinds):
    """kinds: lista (regex_squash, nome). Varre tokens juntando letras espacadas; retorna [(nome,x0,x1)]."""
    # junta tudo em segmentos por gap
    segs = []; cur = None
    for w in ws:
        if cur and (w['x0'] - cur[2]) < 16:
            cur[0] += w['text']; cur[2] = w['x1']
        else:
            if cur: segs.append(cur)
            cur = [w['text'], w['x0'], w['x1']]
    if cur: segs.append(cur)
    out = []
    for txt, a, b in segs:
        s = sq(txt)
        for rx, nome in kinds:
            if re.search(rx, s):
                out.append((nome, a, b)); break
    return out

NUM_RE = re.compile(r"^\d{4,6}\*?$")
ANS_RE = re.compile(r"^\d{3}\.\d{3}/\d{2}-\d$")

def page_segments(rows, xlimit):
    """Todos os segmentos (texto agrupado por gap) da pagina com (sq, x0, x1, y)."""
    segs = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        cur = None
        for w in ws:
            if cur and (w['x0'] - cur[2]) < 16:
                cur[0] += w['text']; cur[2] = w['x1']
            else:
                if cur: segs.append((sq(cur[0]), cur[1], cur[2], r['top']))
                cur = [w['text'], w['x0'], w['x1']]
        if cur: segs.append((sq(cur[0]), cur[1], cur[2], r['top']))
    return segs

def classify_spans(segs, kinds):
    # finditer com x proporcional: acha TODAS as ocorrencias em segmentos colados
    out = []
    for s, a, b, y in segs:
        if not s: continue
        L = len(s)
        taken = []
        for rx, nome in kinds:
            for m in re.finditer(rx, s):
                if any(not (m.end() <= t0 or m.start() >= t1) for t0, t1 in taken):
                    continue
                taken.append((m.start(), m.end()))
                xa = a + (b - a) * m.start() / L
                xb = a + (b - a) * m.end() / L
                out.append((nome, xa, xb, y))
    return out

def span_above(spans, cx, cy, xtol, ymax=70):
    """span mais proximo ACIMA de cy cujo [a-xtol,b+xtol] contem cx."""
    best = None
    for nome, a, b, y in spans:
        if y >= cy - 1 or cy - y > ymax: continue
        if a - xtol <= cx <= b + xtol:
            if best is None or y > best[1]:
                best = (nome, y)
    return best[0] if best else None

def parse_city(page, city, is_pf):
    rows = get_rows(page)
    xlimit = 99999
    for r in rows[:12]:
        for w in r['words']:
            if sq(w['text']).startswith('REAJUSTE'):
                xlimit = min(xlimit, w['x0'] - 12)
    words = [w for r in rows for w in r['words'] if w['x0'] < xlimit]
    segs = page_segments(rows, xlimit)

    prod_spans = [(PRODUCTS[s], a, b, y) for s, a, b, y in segs if s in PRODUCTS]

    # limites de celula do banner de produto (bordas verticais do PDF) p/ tabelas lado a lado
    verts = []
    for rc in page.rects:
        if rc['x1'] - rc['x0'] < 2.5:
            verts.append(((rc['x0']+rc['x1'])/2, rc['top'], rc['bottom']))
    for ln in page.lines:
        if abs(ln['x1'] - ln['x0']) < 2.5:
            verts.append(((ln['x0']+ln['x1'])/2, ln['top'], ln['bottom']))
    prod_cells = []
    for nome, a, b, y in prod_spans:
        yc = y + 2
        cross = [vx for vx, t, bt in verts if t - 1 <= yc <= bt + 1]
        left = max([vx for vx in cross if vx <= a + 1], default=None)
        right = min([vx for vx in cross if vx >= b - 1], default=None)
        prod_cells.append((nome, a, b, y, left, right))
    cop_spans = classify_spans(segs, [
        (r'COPART(ICIPACAO)?PARCIAL', 'Parcial'),
        (r'SEMCOPART(ICIPACAO)?', 'Sem'),
        (r'COPART(ICIPACAO)?TOTAL|COMCOPART(ICIPACAO)?', 'Completa'),
        (r'PARCIAL', 'Parcial'),  # "PARCIAL" em linha propria (cabecalho quebrado em 2 linhas)
    ])
    seg_spans = classify_spans(segs, [
        (r'AMB(ULATORIAL)?\+HOSP(ITALAR)?\+OBST(ETRICIA)?', 'OBST'),
        (r'AMB(ULATORIAL)?\+HOSP(ITALAR)?', 'AH'),
        (r'REFERENCIA|ODONTOLOGIC|PROPRIO', 'SKIP'),
        (r'AMBULATORIAL|SEMACOMODACAO|AMB(?![+A-Z])', 'AMB'),
    ])
    acom_toks = classify_spans(segs, [
        (r'S/ACOM(ODACAO)?|SEMACOMODACAO', 'Ambulatorial'),
        (r'ENFERM(ARIA)?', 'Enfermaria'),
        (r'APART(AMENTO)?', 'Apartamento'),
    ])
    med_spans = classify_spans(segs, [
        (r'MEDICA[\xb91]', '1'),
        (r'MEDICA[\xb22]?', '2'),
    ])

    # linhas de faixa: (faixa, y)
    faixa_rows = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        if not ws: continue
        m = FAIXA_SQ.match(sq(' '.join(w['text'] for w in ws[:5])))
        if m:
            fx = m.group(1)
            faixa = '59 ou mais' if fx == '59' else f'{fx[:2]} a {fx[3:]}'
            faixa_rows.append((faixa, r['top'], min(w['x0'] for w in ws)))

    # colunas: numeros em linhas com INTERNO; registros ANS por linha
    def row_codes(ws, top):
        """codigos 4-6 digitos; junta runs de tokens so-digitos com gap<3 (linhas char-split)."""
        out = []
        i = 0
        while i < len(ws):
            if not re.match(r'^\d+\*?$', ws[i]['text']):
                i += 1; continue
            t = ws[i]['text']; x0 = ws[i]['x0']; x1 = ws[i]['x1']
            while (i + 1 < len(ws) and not t.endswith('*')
                   and re.match(r'^\d+\*?$', ws[i+1]['text'])
                   and (ws[i+1]['x0'] - ws[i]['x1']) < 3):
                i += 1; t += ws[i]['text']; x1 = ws[i]['x1']
            if NUM_RE.match(t):
                out.append((t.rstrip('*'), (x0+x1)/2, top))
            i += 1
        return out

    cols = []
    regs = []
    for ri, r in enumerate(rows):
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        if not ws: continue
        tsq = sq(''.join(w['text'] for w in ws))
        if 'INTERNO' in tsq:
            cc = row_codes(ws, r['top'])
            if not cc and ri + 1 < len(rows) and rows[ri+1]['top'] - r['top'] < 9:
                # codigos na linha logo abaixo do rotulo CÓD. INTERNO
                nws = [w for w in rows[ri+1]['words'] if w['x0'] < xlimit]
                if nws and not FAIXA_SQ.match(sq(' '.join(w['text'] for w in nws[:5]))):
                    cc = row_codes(nws, r['top'])
            cols.extend(cc)
        for w in ws:
            if ANS_RE.match(w['text']):
                regs.append((w['text'], (w['x0']+w['x1'])/2, w['top']))

    # valores: numeros com virgula
    vals = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        mv = merge_values(ws)
        for v, x in mv:
            vals.append((v, x, r['top']))

    # agrupar colunas em tabelas por cy
    tables = {}
    for code, cx, cy in cols:
        key = round(cy / 8)
        tables.setdefault(key, []).append((code, cx, cy))

    def nearest_span(spans, cx, cy, ymax=75, xmax=250):
        best = None
        for nome, a, b, y in spans:
            if y >= cy - 1 or cy - y > ymax: continue
            d = 0 if a <= cx <= b else min(abs(cx - a), abs(cx - b))
            if d > xmax: continue
            if best is None or d < best[1] - 1 or (abs(d - best[1]) <= 1 and y > best[2]):
                best = (nome, d, y)
        return best[0] if best else None

    out = []
    tbl_cys = sorted(min(c[2] for c in tables[k]) for k in tables)
    for key in sorted(tables):
        tcols = sorted(tables[key], key=lambda c: c[1])
        cy = tcols[0][2]
        # janela vertical da tabela: valores entre o cabecalho e a proxima tabela
        next_cy = min([c for c in tbl_cys if c > cy + 6], default=1e9)
        # registros da tabela (banda acima)
        tregs = sorted([(c, x) for c, x, y in regs if 0 < cy - y < 42], key=lambda t: t[1])
        # grupos por repeticao de codigo
        groups = []
        cur = []
        seen = set()
        for c, x in tregs:
            if c in seen:
                groups.append(cur); cur = []; seen = set()
            cur.append((c, x)); seen.add(c)
        if cur: groups.append(cur)
        # copart spans da banda, em ordem de x (sem 'Sem')
        band_cops = sorted([(n, a, b, y) for n, a, b, y in cop_spans if 0 < cy - y < 80], key=lambda t: t[1])
        main_cops = [t for t in band_cops if t[0] != 'Sem']
        group_cop = None
        if len(groups) == len(main_cops) and groups:
            group_cop = {}
            for gi, grp in enumerate(groups):
                for c, x in grp:
                    group_cop[(c, round(x))] = main_cops[gi][0]
        txmin = min(c[1] for c in tcols) - 40
        txmax = max(c[1] for c in tcols) + 40
        for code, cx, ccy in tcols:
            # produto: prioriza celula do banner que contem cx (bordas verticais)
            inc = [p for p in prod_cells if 0 < ccy - p[3] < 95
                   and p[4] is not None and p[5] is not None and p[4] - 2 <= cx <= p[5] + 2]
            if inc:
                ymax_p = max(p[3] for p in inc)
                inc = [p for p in inc if abs(p[3] - ymax_p) < 5]
            if inc and len({p[0] for p in inc}) == 1:
                produto = inc[0][0]
            else:
                produto = nearest_span(prod_spans, cx, ccy, ymax=95, xmax=260)
            segm = nearest_span(seg_spans, cx, ccy, ymax=70, xmax=60)
            # rotulo REFERENCIA/ODONTOLOGICO/PROPRIO diretamente acima da coluna -> pular sempre
            if any(n == 'SKIP' and 0 < ccy - y < 70 and a - 6 <= cx <= b + 6
                   for n, a, b, y in seg_spans):
                segm = 'SKIP'
            if segm is None:
                # fallback: rotulo de segmentacao unico centrado na tabela (tabelas estreitas)
                band = {n for n, a, b, y in seg_spans
                        if 0 < ccy - y < 70 and n != 'SKIP'
                        and a < txmax and b > txmin}
                if len(band) == 1:
                    segm = band.pop()
            if group_cop is not None and tregs:
                rc = min(tregs, key=lambda t: abs(t[1] - cx))
                cop = group_cop.get((rc[0], round(rc[1])))
            else:
                cop = nearest_span(cop_spans, cx, ccy, ymax=80, xmax=120)
            if produto is None or cop in (None, 'Sem') or segm == 'SKIP':
                continue
            if segm is None:
                print(f'  !! {city}: sem segmentacao col {code} ({produto})'); continue
            ac = [(n, (a+b)/2, y) for n, a, b, y in acom_toks if y < ccy and ccy - y < 60 and abs((a+b)/2 - cx) < 55]
            if ac:
                ymax_ac = max(t[2] for t in ac)
                ac = [t for t in ac if abs(t[2] - ymax_ac) < 5]
                # rotulo de acomodacao desambigua a segmentacao (S/ACOM <-> AMB)
                near_ac = min(ac, key=lambda t: abs(t[1]-cx))[0]
                if near_ac == 'Ambulatorial':
                    segm = 'AMB'
                elif segm == 'AMB':
                    alt = nearest_span([s for s in seg_spans if s[0] not in ('AMB', 'SKIP')],
                                       cx, ccy, ymax=70, xmax=90)
                    if alt:
                        segm = alt
            acom = 'Ambulatorial' if segm == 'AMB' else (min(ac, key=lambda t: abs(t[1]-cx))[0] if ac else None)
            if not acom:
                # fallback: rotulo unico de acomodacao centrado na tabela (tabelas estreitas)
                band_ac = {n for n, a, b, y in acom_toks
                           if y < ccy and ccy - y < 60
                           and a < txmax and b > txmin}
                if len(band_ac) == 1:
                    acom = band_ac.pop()
            if not acom:
                print(f'  !! {city}: sem acomodacao col {code} ({produto})'); continue
            md = [(n, (a+b)/2, y) for n, a, b, y in med_spans if y < ccy and ccy - y < 40 and abs((a+b)/2 - cx) < 30]
            med = min(md, key=lambda t: abs(t[1]-cx))[0] if md else '2'
            if DEBUG:
                print(f'  DBG {city}: col {code} x={cx:.0f} y={ccy:.0f} prod={produto} cop={cop} seg={segm} acom={acom} med={med}')
            pr = {}
            for faixa in BANDS:
                cand = []
                for v, vx, vy in vals:
                    if not (ccy < vy < next_cy) or abs(vx - cx) > 34:
                        continue
                    drows = [abs(vy - fy) for fn, fy, fx0 in faixa_rows
                             if fn == faixa and abs(vy - fy) <= 4 and vx > fx0]
                    if drows:
                        cand.append((min(drows), abs(vx - cx), v))
                if cand:
                    pr[faixa] = min(cand)[2]
            if len(pr) != 10:
                continue
            has_obst = any(n == 'OBST' and 0 < ccy - y < 70 for n, a, b, y in seg_spans)
            label = produto
            if segm == 'AH' and has_obst:
                label += ' s/ Obstetrícia'
            if med == '1':
                label += ' + Odonto'
            if is_pf:
                label += ' (PF)'
            out.append(dict(plano=produto, label=label, acomodacao=acom,
                            coparticipacao=cop, precos=pr, cod=code))
    # dedupe por cod (colunas duplicadas impossiveis) e por chave
    seen = {}
    ded = []
    for e in out:
        k = (e['label'], e['acomodacao'], e['coparticipacao'])
        if k in seen:
            if abs(seen[k] - e['precos']['00 a 18']) > 0.01:
                print(f'  !! {city}: chave duplicada com precos distintos {k}')
            continue
        seen[k] = e['precos']['00 a 18']
        ded.append(e)
    return ded

def pick(spans, x, default=None):
    """span cujo intervalo (a-8 .. proximo span) contem x."""
    best = default
    for nome, a, b in sorted(spans, key=lambda s: s[1]):
        if x >= a - 12:
            best = nome
    return best

def nearest(items, x, maxd=999):
    if not items: return None
    it = min(items, key=lambda t: abs(t[1] - x))
    return it[0] if abs(it[1] - x) <= maxd else None

def flush_table(ctx, city, is_pf):
    out = []
    cols = ctx.get('cols') or []
    prices = ctx.get('prices') or {}
    if not cols or len(prices) != 10: return out
    cops = ctx.get('cops') or []
    segs = ctx.get('segs') or []
    acoms = ctx.get('acoms') or []
    meds = ctx.get('meds') or []
    prods = ctx.get('prods') or []
    has_obst = any(s[0] == 'OBST' for s in segs)
    ncols = len(cols)
    for ci, (code, cx) in enumerate(cols):
        produto = pick(prods, cx)
        cop = pick(cops, cx)
        seg = pick(segs, cx)
        if not produto: continue
        if cop in (None, 'Sem') or seg in (None, 'SKIP'):
            continue
        acom = 'Ambulatorial' if seg == 'AMB' else nearest(acoms, cx, 90)
        if not acom:
            print(f'  !! {city}: sem acomodacao p/ col {code} x={int(cx)} ({produto})'); continue
        med = nearest(meds, cx, 45) if meds else '2'
        label = produto
        if seg == 'AH' and has_obst:
            label += ' s/ Obstetrícia'
        if med == '1':
            label += ' + Odonto'
        if is_pf:
            label += ' (PF)'
        pr = {}
        ok = True
        for faixa, vals in prices.items():
            if len(vals) == ncols:
                pr[faixa] = vals[ci][0]
            else:
                v = min(vals, key=lambda t: abs(t[1] - cx + 18))
                if abs(v[1] - cx) > 55: ok = False; break
                pr[faixa] = v[0]
        if not ok:
            print(f'  !! {city}: valores desalinhados {produto} col {code}'); continue
        out.append(dict(plano=produto, label=label, acomodacao=acom,
                        coparticipacao=cop, precos=pr))
    return out

def city_of(page):
    rows = get_rows(page)
    for r in rows[:6]:
        t = ' '.join(w['text'] for w in r['words'])
        m = re.match(r'^([A-Za-zÀ-ÿ\. ]+?)\s*-\s*(PR|SC|RS)\b', t.strip())
        if m:
            nome = ' '.join(p.capitalize() if p.lower() not in ('de','da','do','das','dos') else p.lower()
                            for p in m.group(1).strip().split())
            return f'{nome} - {m.group(2)}'
    return None

def load_all():
    D3 = '/Users/marcoscorrea/Downloads/OneDrive_3_12-08-2026/'
    D4 = '/Users/marcoscorrea/Downloads/OneDrive_4_12-08-2026/'
    files = [
        (D3+'20260701 a 20260930 - Individual (1).pdf', True, {}),
        (D3+'Tabela Individual - Ambulatorial - 20260701 a 20260930.pdf', True, {}),
        (D3+'20260724 a 20260930 - PME (1).pdf', False, dict(vmin=30, vmax=99)),
        (D3+'20260724 a 20260930 - Super Simples.pdf', False, dict(vmin=2, vmax=29)),
        (D4+'20260701 a 20260930 - Individual (2).pdf', True, {}),
        (D4+'Tabela Promocional Individual - Ambulatorial - 20260701 a 20260930.pdf', True, {}),
        (D4+'20260724 a 20260930 - PME.pdf', False, dict(vmin=30, vmax=99)),
        (D4+'20260724 a 20260930 - Super Simples - 1 vida.pdf', False, dict(vmin=1, vmax=1)),
        (D4+'20260724 a 20260930 - Super Simples - 2 a 29 vidas.pdf', False, dict(vmin=2, vmax=29)),
    ]
    result = {}
    for fn, is_pf, meta in files:
        pdf = pdfplumber.open(fn)
        tag = fn.split('/')[-1][:40]
        for pi, page in enumerate(pdf.pages):
            c = city_of(page)
            if not c: continue
            txt = page.extract_text() or ''
            # pagina exclusiva de reajuste (Individual): sem R$
            if 'R$' not in txt: continue
            ents = parse_city(page, c, is_pf)
            if not ents: continue
            for e in ents:
                e.update(meta)
                e['tipo'] = 'Individual' if is_pf else 'Empresarial'
                e['mei'] = False
                e['praca'] = c
                e['fonte'] = tag
            result.setdefault(c, []).extend(ents)
            print(f'{tag[:32]:<34} {c:<26} {len(ents)} entradas')
    return result

def validate(result):
    errs = []
    for praca, ents in result.items():
        seen = {}
        for e in ents:
            k = (e['fonte'], e['label'], e['acomodacao'], e['coparticipacao'])
            if k in seen:
                errs.append(f'{praca}: chave duplicada {k}')
            seen[k] = e
            if set(e['precos']) != set(BANDS):
                errs.append(f'{praca}: faixas != 10 {k}')
                continue
            if abs(max(e['precos'].values()) - e['precos']['59 ou mais']) > 0.005:
                errs.append(f'{praca}: "59 ou mais" nao e o maximo {k}')
        for k, e in seen.items():
            if e['coparticipacao'] == 'Parcial':
                ec = seen.get((k[0], k[1], k[2], 'Completa'))
                if ec and any(e['precos'][f] < ec['precos'][f] - 0.005 for f in BANDS):
                    errs.append(f'{praca}: Parcial < Completa {k}')
            if ' + Odonto' in k[1]:
                ef = seen.get((k[0], k[1].replace(' + Odonto', ''), k[2], k[3]))
                if ef and any(e['precos'][f] > ef['precos'][f] + 0.005 for f in BANDS):
                    errs.append(f'{praca}: "+ Odonto" >= versao cheia {k}')
    return errs

SPOTS = [  # (praca, trecho da fonte, label, acomodacao, copart, 00a18 esperado)
    ('Curitiba - PR', 'Individual (1)', 'Nosso Médico + Odonto (PF)', 'Enfermaria', 'Parcial', 254.33),
    ('Curitiba - PR', 'Individual (1)', 'Nosso Médico (PF)', 'Enfermaria', 'Parcial', 279.83),
    ('Curitiba - PR', 'Individual (1)', 'Nosso Médico + Odonto (PF)', 'Enfermaria', 'Completa', 203.47),
    ('Porto Alegre - RS', 'Individual (2)', 'Nosso Médico + Odonto (PF)', 'Enfermaria', 'Parcial', 211.29),
    ('Porto Alegre - RS', 'Individual (2)', 'Nosso Médico (PF)', 'Enfermaria', 'Parcial', 236.79),
    ('Porto Alegre - RS', 'Individual (2)', 'Pop + Odonto (PF)', 'Enfermaria', 'Parcial', 357.76),
    ('Porto Alegre - RS', 'Individual (2)', 'Pop (PF)', 'Enfermaria', 'Parcial', 383.26),
    ('Porto Alegre - RS', 'Individual (2)', 'Pop + Odonto (PF)', 'Enfermaria', 'Completa', 286.22),
    ('Porto Alegre - RS', 'Individual (2)', 'Pop (PF)', 'Enfermaria', 'Completa', 311.72),
    ('Curitiba - PR', 'PME (1)', 'Nosso Médico + Odonto', 'Enfermaria', 'Parcial', 127.11),
    ('Curitiba - PR', 'PME (1)', 'Nosso Médico', 'Enfermaria', 'Parcial', 174.78),
    ('Porto Alegre - RS', 'Simples - 2', 'Nosso Médico', 'Enfermaria', 'Parcial', 137.42),
    ('Porto Alegre - RS', 'Simples - 2', 'Nosso Médico', 'Apartamento', 'Parcial', 191.97),
    ('Porto Alegre - RS', 'Simples - 2', 'Nosso Médico', 'Enfermaria', 'Completa', 102.35),
    ('Porto Alegre - RS', 'Simples - 2', 'Nosso Médico', 'Apartamento', 'Completa', 142.88),
    ('Porto Alegre - RS', 'Simples - 2', 'Nosso Plano', 'Ambulatorial', 'Parcial', 71.28),
    ('Porto Alegre - RS', 'Simples - 2', 'Pop Vale dos Sinos', 'Enfermaria', 'Completa', 167.81),
    ('Porto Alegre - RS', 'Simples - 2', 'Pop Estadual', 'Enfermaria', 'Parcial', 237.32),
    ('Porto Alegre - RS', 'Simples - 2', 'Pop Estadual', 'Enfermaria', 'Completa', 176.59),
]

def spot_checks(result):
    ok = True
    for praca, fsub, label, acom, cop, exp in SPOTS:
        hits = [e for e in result.get(praca, [])
                if fsub in e['fonte'] and e['label'] == label
                and e['acomodacao'] == acom and e['coparticipacao'] == cop]
        if len(hits) != 1:
            print(f'SPOT FALHOU ({len(hits)} hits): {praca} {fsub} {label} {acom} {cop}')
            ok = False
        elif abs(hits[0]['precos']['00 a 18'] - exp) > 0.005:
            print(f'SPOT FALHOU: {praca} {fsub} {label} {acom} {cop}: '
                  f"esperado {exp} obtido {hits[0]['precos']['00 a 18']}")
            ok = False
    # Pleno presente e Referência ausente no Individual de Curitiba
    cwb = [e for e in result.get('Curitiba - PR', []) if 'Individual (1)' in e['fonte']]
    if not any(e['plano'] == 'Pleno' for e in cwb):
        print('SPOT FALHOU: Pleno ausente no Individual de Curitiba'); ok = False
    return ok

if __name__ == '__main__':
    result = load_all()
    json.dump(result, open('/tmp/sul_parsed.json', 'w'), ensure_ascii=False, indent=1)
    print('\nPraças:', {k: len(v) for k, v in result.items()})
    errs = validate(result)
    for e in errs:
        print('VALIDACAO:', e)
    spots_ok = spot_checks(result)
    print(f'\nValidação: {"OK" if not errs else str(len(errs)) + " erros"};'
          f' spot-checks: {"OK" if spots_ok else "FALHAS"}')
