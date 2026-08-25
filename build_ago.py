#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga ago/2026 (vigência 01/07-30/09 e 01/08-30/09): 7 PDFs Hapvida de
~/Downloads/OneDrive_1_12-08-2026 -> /tmp/ago_parsed.json
Base: build_sul.py (algoritmo por coluna ancorado na linha CÓD. INTERNO).
Diferenças vs build_sul:
  - city_of aceita qualquer UF, "CAMAÇARI -BA" (sem espaço) e página só com
    "JOINVILLE" (mapa CITY_NOUF); nomes normalizados pelos do catalog.json.
  - SEM COPARTICIPAÇÃO -> 'Completa' (catálogo trata "sem copart mensal" como
    Completa; conferido em Fortaleza: 214,04/239,54 = Completa no catálogo).
  - produtos por regex (banners tipo "NOSSO MÉDICO COM COPARTICIPAÇÃO" no PME
    trazem produto+copart no mesmo segmento).
  - dimensão FRANQUIA (Joinville Individual: SEM/COM FRANQUIA; banners
    "NOSSO PLANO - FRANQUIA" e "MIX - FRANQUIA" em BA/DF) -> label "... Franquia".
  - clip do REAJUSTE por palavra 'REAJUSTE' maiúscula na metade direita
    (nas tabelas SS/PME/Ambulatorial o reajuste fica ao lado, em qualquer linha).
Validação: interna + diff vs catalog.json (não altera o catálogo).
AGO_DEBUG=1 para debug por coluna.
"""
import pdfplumber, json, re, unicodedata, os

DEBUG = bool(os.environ.get('AGO_DEBUG'))

DIR = '/Users/marcoscorrea/Downloads/OneDrive_1_12-08-2026/'
CATALOG = '/Users/marcoscorrea/comparativo-ppo/catalog.json'
OUT = '/tmp/ago_parsed.json'

BANDS = ["00 a 18","19 a 23","24 a 28","29 a 33","34 a 38","39 a 43","44 a 48","49 a 53","54 a 58","59 ou mais"]

def deacc(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def sq(s):
    return deacc(s).upper().replace(' ', '')

# produto por regex no squash do segmento (ordem importa: mais específico antes)
# obs: sufixo "- FRANQUIA" do banner é IGNORADO (catálogo rotula 'Nosso Plano'/'Mix';
# conferido: Salvador/Camaçari/Feira — preços do catálogo = tabela "- FRANQUIA").
PROD_KINDS = [
    (r'NOSSOPLANO-?SEMFRANQUIA', 'Nosso Plano'),
    (r'NOSSOPLANO-?FRANQUIA', 'Nosso Plano'),
    (r'NOSSOPLANO-?AMB(ULATORIAL)?', 'Nosso Plano'),
    (r'NOSSOPLANO-?MUNICIPAL', 'Nosso Plano Municipal'),
    (r'NOSSOPLANO-?GRUPODEMUNICIPIOS', 'Nosso Plano Grupo Municípios'),
    (r'NOSSOPLANO', 'Nosso Plano'),
    (r'NOSSOMEDICO', 'Nosso Médico'),
    (r'MIX-?FRANQUIA', 'Mix'),
    (r'(?<![A-Z])MIX(?![A-Z])', 'Mix'),
    (r'(?<![A-Z])PLENO(?![A-Z])', 'Pleno'),
    (r'(?<![A-Z])INTEGRADO(?![A-Z])', 'Integrado'),
    (r'(?<![A-Z])POPESTADUAL', 'Pop Estadual'),
    (r'(?<![A-Z])POP(?![A-Z])', 'Pop'),
    (r'SMARTUP', 'Smart UP'),
]

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
    # aceita '-'/'!' iniciais espúrios: SS Joinville tem '59+' impresso dobrado
    # ("RR$$ 1 . 6 8 -3,00" = R$ 1.683,00) e Teresina SS 24/08 tem "#REF!714,59"
    # sobre o valor — preços nunca são negativos nem começam com pontuação
    toks = [w for w in words if w['text'] != 'R$' and re.match(r'^[-!]?[\d\.,]+$', w['text'])]
    def inc(t):
        return ',' not in t or len(t.split(',')[-1]) < 2
    vals = []; i = 0
    while i < len(toks):
        t = toks[i]['text'].lstrip('-!'); x = toks[i]['x0']
        while i + 1 < len(toks) and inc(t) and (toks[i+1]['x0'] - toks[i]['x1']) < 8:
            t += toks[i+1]['text'].lstrip('-!'); i += 1
        if ',' in t and re.search(r'\d', t):
            vals.append((float(t.replace('.', '').replace(',', '.')), x))
        i += 1
    return vals

NUM_RE = re.compile(r"^\d{4,6}\*?$")
ANS_RE = re.compile(r"^\d{3}\.\d{3}[/.]\d{2}-\d$")

def page_segments(rows, xlimit):
    """Segmentos (texto agrupado por gap) com mapa x POR CARACTERE do squash —
    evita o desvio do x proporcional em segmentos longos com gaps irregulares."""
    segs = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        cur = None  # [texto_sq, xmap, x0, x1]
        for w in ws:
            t = sq(w['text'])
            n = len(t)
            if n:
                cw = (w['x1'] - w['x0']) / n
                xm = [(w['x0'] + i*cw, w['x0'] + (i+1)*cw) for i in range(n)]
            else:
                xm = []
            if cur and (w['x0'] - cur[3]) < 16:
                cur[0] += t; cur[1].extend(xm); cur[3] = w['x1']
            else:
                if cur: segs.append((cur[0], cur[2], cur[3], r['top'], cur[1]))
                cur = [t, xm, w['x0'], w['x1']]
        if cur: segs.append((cur[0], cur[2], cur[3], r['top'], cur[1]))
    return segs

def classify_spans(segs, kinds):
    out = []
    for s, a, b, y, xmap in segs:
        if not s: continue
        taken = []
        for rx, nome in kinds:
            for m in re.finditer(rx, s):
                if any(not (m.end() <= t0 or m.start() >= t1) for t0, t1 in taken):
                    continue
                taken.append((m.start(), m.end()))
                xa = xmap[m.start()][0]
                xb = xmap[m.end()-1][1]
                out.append((nome, xa, xb, y))
    return out

def parse_city(page, city, is_pf):
    rows = get_rows(page)
    # clip da tabela de reajuste lateral: palavra 'REAJUSTE' (maiúscula) na metade direita
    xlimit = 99999
    W = page.width
    for r in rows:
        for w in r['words']:
            if w['text'].startswith('REAJUSTE') and w['x0'] > 0.40 * W:
                xlimit = min(xlimit, w['x0'] - 12)
    segs = page_segments(rows, xlimit)

    prod_spans = classify_spans(segs, PROD_KINDS)

    # limites de célula do banner (bordas verticais) p/ tabelas lado a lado
    verts = []
    for rc in page.rects:
        if rc['x1'] - rc['x0'] < 2.5:
            verts.append(((rc['x0']+rc['x1'])/2, rc['top'], rc['bottom']))
    for ln in page.lines:
        if abs(ln['x1'] - ln['x0']) < 2.5:
            verts.append(((ln['x0']+ln['x1'])/2, ln['top'], ln['bottom']))
    def cellify(spans):
        cells = []
        for nome, a, b, y in spans:
            yc = y + 2
            cross = [vx for vx, t, bt in verts if t - 1 <= yc <= bt + 1]
            left = max([vx for vx in cross if vx <= a + 1], default=None)
            right = min([vx for vx in cross if vx >= b - 1], default=None)
            cells.append((nome, a, b, y, left, right))
        return cells

    prod_cells = cellify(prod_spans)

    cop_spans = classify_spans(segs, [
        (r'COPART(ICIPACAO)?PARCIAL', 'Parcial'),
        (r'SEMCOPART(ICIPACAO)?', 'Completa'),   # "sem copart mensal" = Completa no catálogo
        (r'COPART(ICIPACAO)?TOTAL|COMCOPART(ICIPACAO)?', 'Completa'),
        (r'PARCIAL', 'Parcial'),
    ])
    cop_cells = cellify(cop_spans)
    seg_spans = classify_spans(segs, [
        (r'AMB(ULATORIAL)?\+HOSP(ITALAR)?\+OBST(ETRICIA)?', 'OBST'),
        (r'AMB(ULATORIAL)?\+HOSP(ITALAR)?', 'AH'),
        (r'REFERENCIA|ODONTOLOGIC|PROPRIO|PLANOSODONTO', 'SKIP'),
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
    fr_spans = classify_spans(segs, [
        (r'SEMFRANQUIA', 'Sem'),
        (r'COMFRANQUIA', 'Com'),
        (r'SEM(?=COMFRANQUIA)|^SEM$', 'Sem'),  # linha "FRANQUIA* | SEM | COM FRANQUIA*" (Brasília SS 24/08)
    ])
    # franquia só vale como dimensão quando é linha de cabeçalho (fora de banner de produto)
    prod_ys = {round(y) for n, a, b, y in prod_spans}
    fr_spans = [t for t in fr_spans if round(t[3]) not in prod_ys]

    # linhas de faixa
    faixa_rows = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        if not ws: continue
        m = FAIXA_SQ.match(sq(' '.join(w['text'] for w in ws[:8])))
        if m:
            fx = m.group(1)
            faixa = '59 ou mais' if fx == '59' else f'{fx[:2]} a {fx[3:]}'
            faixa_rows.append((faixa, r['top'], min(w['x0'] for w in ws)))

    def row_codes(ws, top):
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
                nws = [w for w in rows[ri+1]['words'] if w['x0'] < xlimit]
                # nao usar a proxima linha se for faixa etaria ou linha de precos
                # (caixa "ODONTOLOGIA ... CÓD. INTERNO VALOR": codigo fica na linha
                #  do produto odonto junto com R$ — nao e coluna de tabela medica)
                if (nws and not FAIXA_SQ.match(sq(' '.join(w['text'] for w in nws[:8])))
                        and not any(w['text'] == 'R$' for w in nws)):
                    cc = row_codes(nws, r['top'])
            cols.extend(cc)
        for w in ws:
            if ANS_RE.match(w['text']):
                regs.append((w['text'], (w['x0']+w['x1'])/2, w['top']))

    vals = []
    for r in rows:
        ws = [w for w in r['words'] if w['x0'] < xlimit]
        for v, x in merge_values(ws):
            vals.append((v, x, r['top']))

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

    def merge_cops(spans):
        # cabeçalho quebrado em 2 linhas ("COM COPARTICIPAÇÃO" + "PARCIAL"): merge
        if not spans: return []
        sp = sorted(spans, key=lambda t: (t[1] + t[2]) / 2)
        merged = []
        for t in sp:
            if merged:
                p = merged[-1]
                ov = min(p[2], t[2]) - max(p[1], t[1])
                if ov > 0.5 * min(p[2] - p[1], t[2] - t[1]):
                    nome = 'Parcial' if 'Parcial' in (p[0], t[0]) else p[0]
                    merged[-1] = (nome, min(p[1], t[1]), max(p[2], t[2]), p[3])
                    continue
            merged.append(t)
        return merged

    def pick_band(spans, cx):
        """Span do intervalo horizontal que contém cx; divisórias = ponto médio
        entre spans consecutivos (títulos centralizados não cobrem toda a área)."""
        sp = merge_cops(spans)
        for i, (nome, a, b, y) in enumerate(sp):
            lo = -1e9 if i == 0 else (sp[i-1][2] + a) / 2
            hi = 1e9 if i == len(sp) - 1 else (b + sp[i+1][1]) / 2
            if lo <= cx <= hi:
                return nome
        return None

    out = []
    tbl_cys = sorted(min(c[2] for c in tables[k]) for k in tables)
    for key in sorted(tables):
        tcols = sorted(tables[key], key=lambda c: c[1])
        cy = tcols[0][2]
        next_cy = min([c for c in tbl_cys if c > cy + 6], default=1e9)
        # cabeçalhos desta tabela ficam entre o cabeçalho da tabela anterior e cy
        prev_cy = max([c for c in tbl_cys if c < cy - 6], default=-1e9)
        def in_band(y, ymax):
            return y < cy - 1 and cy - y < ymax and y > prev_cy
        txmin = min(c[1] for c in tcols) - 40
        txmax = max(c[1] for c in tcols) + 40
        def in_x(t):
            return t[1] < txmax and t[2] > txmin
        def near_prod(t):
            # cabeçalho "PRODUTO COM COPARTICIPAÇÃO" pode ficar à direita das
            # colunas do grupo (PME 24/08 Campina Grande: 2 colunas, banner largo);
            # é legítimo quando emenda com um span de produto na mesma linha
            return any(abs(p[3] - t[3]) < 3 and -25 <= t[1] - p[2] <= 25
                       for p in prod_spans)
        band_cops = sorted([t for t in cop_spans if in_band(t[3], 80) and (in_x(t) or near_prod(t))],
                           key=lambda t: t[1])
        band_copc = [t for t in cop_cells if in_band(t[3], 80) and (in_x(t) or near_prod(t))]
        band_seg = [t for t in seg_spans if in_band(t[3], 70)]
        band_ac_all = [t for t in acom_toks if in_band(t[3], 60)]
        band_med = [t for t in med_spans if in_band(t[3], 40)]
        band_fr = [t for t in fr_spans if in_band(t[3], 85) and in_x(t)]
        band_prod = [t for t in prod_spans if in_band(t[3], 95)]
        band_prodc = [t for t in prod_cells if in_band(t[3], 95)]
        # banner de produto fica ACIMA da linha de coparticipação da tabela
        # (evita capturar "PLANO | NOSSO PLANO | MIX" da caixinha TX. ADESÃO ao lado)
        # (o banner fica logo acima dela; caixas laterais tipo "TX. ADESÃO" e
        # "COPARTICIPAÇÃO POR PROCEDIMENTO" citam produtos em outros y)
        if band_cops:
            ycop = min(t[3] for t in band_cops)
            band_prod = [t for t in band_prod if ycop - 18 <= t[3] <= ycop + 3]
            band_prodc = [t for t in band_prodc if ycop - 18 <= t[3] <= ycop + 3]
        # copart alinhada a uma coluna SKIP (ex.: "SEM COPARTICIPAÇÃO" sobre a
        # REFERÊNCIA) não é divisória de grupo de preço — descartar
        skips = [t for t in band_seg if t[0] == 'SKIP']
        def over_skip(t):
            c = (t[1] + t[2]) / 2
            for n, a, b, y in skips:
                sc = (a + b) / 2
                if a - 2 <= c <= b + 2 and t[1] - 2 <= sc <= t[2] + 2:
                    return True
            return False
        band_cops = [t for t in band_cops if not over_skip(t)]
        band_fr = [t for t in band_fr if not over_skip(t)]
        # idem p/ produto: "INTEGRADO" rotulando só a coluna REFERÊNCIA (SP interior)
        band_prod = [t for t in band_prod if not over_skip((t[0], t[1], t[2], t[3]))]
        band_prodc = [t for t in band_prodc if not over_skip((t[0], t[1], t[2], t[3]))]
        if DEBUG:
            print(f'  DBG {city}: tabela cy={cy:.0f} band_cops=' +
                  ' | '.join(f'{n}[{a:.0f}-{b:.0f}]y{y:.0f}' for n, a, b, y in band_cops))
        # grupos por repetição do REGISTRO ANS: quando o nº de runs bate com o nº
        # de grupos de copart, as divisórias entre runs são exatas (cabeçalhos de
        # copart centralizados/alinhados à esquerda não cobrem o grupo inteiro)
        merged_cops = merge_cops(band_cops)
        tregs = sorted([(c, x) for c, x, y in regs
                        if 0 < cy - y < 42 and y > prev_cy], key=lambda t: t[1])
        runs = []
        cur = []; seen = set()
        for c, x in tregs:
            if c in seen:
                runs.append(cur); cur = []; seen = set()
            cur.append((c, x)); seen.add(c)
        if cur: runs.append(cur)
        run_bounds = None
        if len(runs) == len(merged_cops) > 1:
            run_bounds = [(runs[i][-1][1] + runs[i+1][0][1]) / 2 for i in range(len(runs) - 1)]
        tout = []
        for code, cx, ccy in tcols:
            inc = [p for p in band_prodc
                   if p[4] is not None and p[5] is not None and p[4] - 2 <= cx <= p[5] + 2]
            if inc:
                ymax_p = max(p[3] for p in inc)
                inc = [p for p in inc if abs(p[3] - ymax_p) < 5]
            if inc and len({p[0] for p in inc}) == 1:
                produto = inc[0][0]
            else:
                # banner deve cobrir a faixa x das colunas da tabela (caixas
                # laterais citam produtos fora dela, ex.: copart por procedimento)
                over = [t for t in band_prod if t[1] < txmax and t[2] > txmin]
                produto = nearest_span(over or band_prod, cx, ccy, ymax=95, xmax=260)
            # SKIP (REFERÊNCIA/ODONTOLÓGICO) só por contenção horizontal — por
            # proximidade ele roubava colunas médicas vizinhas (ex.: Joinville)
            segm = nearest_span([s for s in band_seg if s[0] != 'SKIP'], cx, ccy, ymax=70, xmax=60)
            if any(n == 'SKIP' and a - 6 <= cx <= b + 6 for n, a, b, y in band_seg):
                segm = 'SKIP'
            if segm is None:
                # fallback: segmentação única na tabela (ignora rótulos sobre
                # colunas SKIP, ex.: "SEM ACOMODAÇÃO" da coluna odontológica)
                band = {n for n, a, b, y in band_seg
                        if n != 'SKIP' and a < txmax and b > txmin
                        and not any(a < sb + 6 and b > sa - 6
                                    for sn, sa, sb, sy in band_seg if sn == 'SKIP')}
                if len(band) == 1:
                    segm = band.pop()
            # copart: divisórias dos runs de ANS; senão célula do cabeçalho; senão
            # divisórias por x entre os spans
            if run_bounds is not None:
                gi = sum(1 for b in run_bounds if cx > b)
                cop = merged_cops[gi][0]
            else:
                cc = {n for n, a, b, y, l, r in band_copc
                      if l is not None and r is not None and l - 2 <= cx <= r + 2}
                cop = cc.pop() if len(cc) == 1 else pick_band(band_cops, cx)
            if produto is None or cop is None or segm == 'SKIP':
                if DEBUG:
                    print(f'  DBG {city}: drop col {code} x={cx:.0f} prod={produto} cop={cop} segm={segm}')
                continue
            ac = [(n, (a+b)/2, y) for n, a, b, y in band_ac_all if abs((a+b)/2 - cx) < 55]
            if ac:
                ymax_ac = max(t[2] for t in ac)
                ac = [t for t in ac if abs(t[2] - ymax_ac) < 5]
                near_ac = min(ac, key=lambda t: abs(t[1]-cx))[0]
                if near_ac == 'Ambulatorial':
                    segm = 'AMB'
                elif segm == 'AMB':
                    alt = nearest_span([s for s in band_seg if s[0] not in ('AMB', 'SKIP')],
                                       cx, ccy, ymax=70, xmax=90)
                    if alt:
                        segm = alt
            acom = 'Ambulatorial' if segm == 'AMB' else (min(ac, key=lambda t: abs(t[1]-cx))[0] if ac else None)
            if not acom:
                bac = {n for n, a, b, y in band_ac_all if a < txmax and b > txmin}
                if len(bac) == 1:
                    acom = bac.pop()
            # segm/acom None seguem para o backfill por ANS após o loop
            md = [(n, (a+b)/2, y) for n, a, b, y in band_med if abs((a+b)/2 - cx) < 30]
            med = min(md, key=lambda t: abs(t[1]-cx))[0] if md else None
            # franquia (linha de cabeçalho SEM/COM FRANQUIA)
            fr = nearest_span(band_fr, cx, ccy, ymax=85, xmax=60) if band_fr else None
            if DEBUG:
                print(f'  DBG {city}: col {code} x={cx:.0f} y={ccy:.0f} prod={produto} cop={cop} seg={segm} acom={acom} med={med} fr={fr}')
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
                if DEBUG:
                    print(f'  DBG {city}: drop col {code} x={cx:.0f} faixas={len(pr)}')
                continue
            has_obst = any(n == 'OBST' for n, a, b, y in band_seg)
            ans = min(tregs, key=lambda t: abs(t[1] - cx))[0] \
                if tregs and min(abs(t[1] - cx) for t in tregs) < 45 else None
            tout.append(dict(produto=produto, cop=cop, segm=segm, acom=acom,
                             med=med, fr=fr, precos=pr, cod=code,
                             has_obst=has_obst, ans=ans))
        # backfill por REGISTRO ANS: segmentação/acomodação são propriedades do
        # registro — recupera célula corrompida na fonte (Fortaleza PME 24/08 tem
        # '\\' no lugar de ENFERM) e rótulos fora do alcance horizontal
        segmap = {}; acmap = {}
        for t in tout:
            if t['ans']:
                if t['segm']: segmap.setdefault(t['ans'], set()).add(t['segm'])
                if t['acom']: acmap.setdefault(t['ans'], set()).add(t['acom'])
        kept = []
        for t in tout:
            if t['segm'] is None and t['ans'] and len(segmap.get(t['ans'], ())) == 1:
                t['segm'] = next(iter(segmap[t['ans']]))
            if t['acom'] is None and t['ans'] and len(acmap.get(t['ans'], ())) == 1:
                t['acom'] = next(iter(acmap[t['ans']]))
            if t['segm'] == 'AMB' and not t['acom']:
                t['acom'] = 'Ambulatorial'
            if t['segm'] is None:
                print(f"  !! {city}: sem segmentacao col {t['cod']} ({t['produto']})"); continue
            if t['acom'] is None:
                print(f"  !! {city}: sem acomodacao col {t['cod']} ({t['produto']})"); continue
            kept.append(t)
        tout = kept
        # Médica¹/² sem linha ASSISTÊNCIA (ex.: João Pessoa): pares de colunas
        # idênticas na chave -> a mais barata é a variante "+ Odonto"
        pares = {}
        for t in tout:
            if t['med'] is None:
                pares.setdefault((t['produto'], t['cop'], t['segm'], t['acom'], t['fr']), []).append(t)
        for grp in pares.values():
            if len(grp) == 2:
                grp.sort(key=lambda t: t['precos']['00 a 18'])
                if grp[0]['precos']['00 a 18'] < grp[1]['precos']['00 a 18'] - 0.01:
                    grp[0]['med'] = '1'; grp[1]['med'] = '2'
        for t in tout:
            label = t['produto']
            if t['fr'] == 'Com' and 'Franquia' not in label:
                label += ' Franquia'
            if t['segm'] == 'AH' and t['has_obst']:
                label += ' s/ Obstetrícia'
            if t['med'] == '1':
                label += ' + Odonto'
            if is_pf:
                label += ' (PF)'
            out.append(dict(plano=t['produto'], label=label, acomodacao=t['acom'],
                            coparticipacao=t['cop'], precos=t['precos'], cod=t['cod']))
    # dedupe: colunas repetidas (mesmo preço) caem; tabelas gêmeas com preços
    # distintos (ex.: Feira de Santana tem 2 tabelas "NOSSO PLANO - FRANQUIA";
    # o catálogo atual também guarda as duas) são mantidas, com aviso.
    seen = {}
    ded = []
    for e in out:
        k = (e['label'], e['acomodacao'], e['coparticipacao'])
        if k in seen:
            if abs(seen[k] - e['precos']['00 a 18']) > 0.01:
                print(f'  !! {city}: chave duplicada com precos distintos {k} '
                      f"({seen[k]} vs {e['precos']['00 a 18']}) — mantidas ambas")
                ded.append(e)
            continue
        seen[k] = e['precos']['00 a 18']
        ded.append(e)
    return ded

# ---------------- cidades ----------------
UFS = ('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO').split()
CITY_NOUF = {'JOINVILLE': 'Joinville - SC', 'JUAZEIRODONORTE': 'Juazeiro Do Norte - CE'}

def load_catalog():
    return json.load(open(CATALOG))

def catalog_praca_map(cat):
    m = {}
    for e in cat:
        p = e.get('praca')
        if p:
            m[sq(p)] = p
    return m

PRACA_MAP = {}

def titlecase_city(nome, uf):
    parts = []
    for p in nome.strip().split():
        pl = p.lower()
        parts.append(pl if pl in ('de', 'da', 'do', 'das', 'dos', 'e') else pl.capitalize())
    full = f"{' '.join(parts)} - {uf}"
    return PRACA_MAP.get(sq(full), full)

def city_of(page):
    rows = get_rows(page)
    for r in rows[:8]:
        t = ' '.join(w['text'] for w in r['words']).strip()
        if len(t) > 40: continue
        m = re.match(r'^([A-ZÀ-Ý][A-ZÀ-Ý\.\' ]+?)\s*-\s*([A-Z]{2})$', t)
        if m and m.group(2) in UFS:
            return titlecase_city(m.group(1), m.group(2))
        ts = sq(t)
        if ts in CITY_NOUF:
            return PRACA_MAP.get(sq(CITY_NOUF[ts]), CITY_NOUF[ts])
    return None

# ---------------- carga ----------------
FILES = [
    ('20260701 a 20260930 - Individual.pdf', True, {}),
    ('20260701 a 20260930 - Tabela Promocional Individual - Ambulatorial.pdf', True, {}),
    ('20260701 a 20260930 - Super Simples 1 vida (1).pdf', False, dict(vmin=1, vmax=1)),
    ('20260801 a 20260930 - Super Simples 2 a 29 vidas (2).pdf', False, dict(vmin=2, vmax=29)),
    ('20260701 a 20260930 - Super Simples 2 a 29 vidas - Joinville.pdf', False, dict(vmin=2, vmax=29)),
    ('20260801 a 20260930 - PME (2).pdf', False, dict(vmin=30, vmax=99)),
]
ACIRP = '20260701 a 20260930 - Super Simples - Ribeirão Preto - Associação Comercial & Industrial v2.pdf'

def load_all():
    result = {}
    for fn, is_pf, meta in FILES:
        pdf = pdfplumber.open(DIR + fn)
        tag = fn[:60]
        for pi, page in enumerate(pdf.pages):
            c = city_of(page)
            if not c:
                txt = page.extract_text() or ''
                if 'R$' in txt and 'CÓD' in txt:
                    print(f'  !! {tag[:40]} p{pi}: cidade nao detectada (pagina com precos)')
                continue
            txt = page.extract_text() or ''
            if 'R$' not in txt:
                continue  # página só de reajuste
            ents = parse_city(page, c, is_pf)
            if not ents:
                print(f'  !! {tag[:40]} p{pi} {c}: 0 entradas')
                continue
            for e in ents:
                e.pop('cod', None)
                e.update(meta)
                e['tipo'] = 'Individual' if is_pf else 'Empresarial'
                e['mei'] = False
                e['praca'] = c
                e['fonte'] = tag
            result.setdefault(c, []).extend(ents)
            print(f'{tag[:44]:<46} {c:<26} {len(ents)} entradas')
    return result

def report_acirp():
    print('\n===== ACIRP (Ribeirão Preto - Associação Comercial) — NÃO carregado no JSON =====')
    pdf = pdfplumber.open(DIR + ACIRP)
    page = pdf.pages[0]
    c = city_of(page) or 'Ribeirão Preto - SP'
    ents = parse_city(page, c, False)
    for e in ents:
        p = e['precos']
        print(f"  {e['label']:<26} {e['acomodacao']:<12} {e['coparticipacao']:<9} "
              f"00a18={p['00 a 18']:>8.2f}  59+={p['59 ou mais']:>9.2f}")
    return ents

# ---------------- validações ----------------
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

def diff_catalog(result, cat):
    """Diff vs catálogo (ouro): Individual Hapvida por praça."""
    print('\n===== DIFF vs catalog.json (Hapvida) =====')
    print(f'{"praça":<28} {"tipo":<11} {"iguais":>6} {"mudou":>6} {"novas":>6} {"ausentes":>8}')
    changed_examples = []
    tot = dict(ig=0, mu=0, no=0, au=0)
    for praca in sorted(result):
        for tipo in ('Individual', 'Empresarial'):
            news = {}
            for e in result[praca]:
                if e['tipo'] != tipo: continue
                k = (e['label'], e['acomodacao'], e['coparticipacao'],
                     e.get('vmin'), e.get('vmax'))
                news.setdefault(k, e)
            if not news: continue
            olds = {}
            for e in cat:
                if e.get('operadora') != 'Hapvida' or e.get('praca') != praca: continue
                if e.get('tipo') != tipo: continue
                k = (e['label'], e['acomodacao'], e['coparticipacao'],
                     e.get('vmin'), e.get('vmax'))
                olds.setdefault(k, e)
            ig = mu = no = 0
            for k, e in news.items():
                if k in olds:
                    if all(abs(e['precos'][f] - olds[k]['precos'].get(f, -1)) <= 0.005 for f in BANDS):
                        ig += 1
                    else:
                        mu += 1
                        changed_examples.append((praca, k, olds[k]['precos']['00 a 18'], e['precos']['00 a 18']))
                else:
                    no += 1
            # ausentes: só entre portes (vmin,vmax) cobertos pelos arquivos novos
            portes = {k[3:] for k in news}
            olds = {k: v for k, v in olds.items() if k[3:] in portes}
            au = len([k for k in olds if k not in news])
            if olds or news:
                print(f'{praca:<28} {tipo:<11} {ig:>6} {mu:>6} {no:>6} {au:>8}')
            tot['ig'] += ig; tot['mu'] += mu; tot['no'] += no; tot['au'] += au
            if olds and (mu + ig) < 0.5 * len(olds) and len(olds) >= 4:
                print(f'   ^^ ATENÇÃO {praca} ({tipo}): >50% das chaves do catálogo sem par — conferir labels')
                miss = [k for k in olds if k not in news][:6]
                for k in miss:
                    print(f'      catálogo sem par: {k}')
                extra = [k for k in news if k not in olds][:6]
                for k in extra:
                    print(f'      novo sem par:     {k}')
    print(f'{"TOTAL":<28} {"":<11} {tot["ig"]:>6} {tot["mu"]:>6} {tot["no"]:>6} {tot["au"]:>8}')
    if changed_examples:
        print('\nExemplos de mudança de preço (00 a 18):')
        for praca, k, old, new in changed_examples[:5]:
            print(f'  {praca}: {k[0]} | {k[1]} | {k[2]}: {old} -> {new}')
    return tot

def spot_print(result):
    print('\n===== SPOT-CHECK (00 a 18) =====')
    for praca in ('Fortaleza - CE', 'Belo Horizonte - MG', 'Joinville - SC'):
        print(f'--- {praca}')
        for e in result.get(praca, []):
            extra = f" vmin={e.get('vmin')}" if e.get('vmin') else ''
            print(f"  [{e['fonte'][:28]}] {e['label']:<34} {e['acomodacao']:<12} "
                  f"{e['coparticipacao']:<9}{extra}  00a18={e['precos']['00 a 18']:>9.2f}")

if __name__ == '__main__':
    cat = load_catalog()
    PRACA_MAP.update(catalog_praca_map(cat))
    result = load_all()
    json.dump(result, open(OUT, 'w'), ensure_ascii=False, indent=1)
    n = sum(len(v) for v in result.values())
    print(f'\nTotal: {n} entradas em {len(result)} praças -> {OUT}')
    errs = validate(result)
    for e in errs:
        print('VALIDACAO:', e)
    print(f'Validação interna: {"OK" if not errs else str(len(errs)) + " erros"}')
    diff_catalog(result, cat)
    spot_print(result)
    report_acirp()
