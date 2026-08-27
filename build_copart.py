#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrai o quadro "COPARTICIPAÇÃO POR PROCEDIMENTO" das tabelas de venda Hapvida.
Saída: /tmp/copart_parsed.json  {praça: {produto: {parcial:{proc:val|None}, total:{...}, fonte:str}}}
Layout: colunas do quadro = grupos (COPARTICIPAÇÃO PARCIAL | COPARTICIPAÇÃO/TOTAL), cada grupo com
subcolunas [percentual][valor] e, em algumas praças, um nível a mais por PRODUTO."""
import pdfplumber, json, re, unicodedata, sys, glob, os

def deacc(s): return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c)!='Mn')
def sq(s): return re.sub(r'\s+',' ',deacc(s)).upper().strip()

PROCS=['Consultas eletivas','Consultas de urgência','Exames simples','Exames complexos',
       'Terapias especiais','Demais terapias','Internações']
def proc_of(t):
    n=sq(t)
    if n.startswith('CONSULTAS ELETIVAS'): return PROCS[0]
    if n.startswith('CONSULTAS DE URG'):   return PROCS[1]
    if n.startswith('EXAMES SIMPLES'):     return PROCS[2]
    if n.startswith('EXAMES COMPLEXOS'):   return PROCS[3]
    if n.startswith('TERAPIAS ESPECIAIS'): return PROCS[4]
    if n.startswith('DEMAIS TERAPIAS'):    return PROCS[5]
    if n.startswith('INTERNAC'):           return PROCS[6]
    return None

VAL_RE=re.compile(r'^(valor fixo de|valor fixo)?\s*(r\$\s*[\d.,]+|[\d.,]+\s*%\s*(limitado a\s*r\$\s*[\d.,]+)?|isento)$',re.I)
def val_ok(v):
    if not v: return None
    v=re.sub(r'\s+',' ',v).strip(' .;:')
    if len(v)>46: return None
    n=v.lower()
    if VAL_RE.match(n): return v
    m=re.match(r'^([\d.,]+\s*%)\s*limitad[oa]\s*a\s*(r\$\s*[\d.,]+)$',n)
    if m: return v
    if re.match(r'^valor fixo r\$ [\d.,]+$',n): return v
    if re.match(r'^[\d.,]+% limitado a r\$ [\d.,]+$',n): return v
    return None

def rows_of(words, tol=3.0):
    rs=[]
    for w in sorted(words,key=lambda w:(w['top'],w['x0'])):
        for r in rs:
            if abs(r['y']-w['top'])<=tol: r['w'].append(w); break
        else: rs.append({'y':w['top'],'w':[w]})
    for r in rs: r['w'].sort(key=lambda w:w['x0'])
    return sorted(rs,key=lambda r:r['y'])

def find_boxes(page):
    """Todos os quadros de coparticipação da página: (x0,x1,y_head,y_ini,y_fim)."""
    ws=page.extract_words(x_tolerance=1.2)
    rs=rows_of(ws)
    boxes=[]
    for i,r in enumerate(rs):
        for w in r['w']:
            if sq(w['text'])!='PROCEDIMENTO': continue
            px=w['x0']
            itens=[]
            for r2 in rs[i+1:]:
                rot=' '.join(x['text'] for x in r2['w'] if px-12<=x['x0']<px+150)
                if proc_of(rot): itens.append(r2)
                elif itens and r2['y']-itens[-1]['y']>26: break
            if len(itens)<2: continue
            y_ini=itens[0]['y']-1; y_fim=itens[-1]['y']+9
            dir_=[x['x1'] for x in r['w'] if x['x0']>=px]
            boxes.append((px-4, max(dir_)+110, r['y'], y_ini, y_fim))
    return boxes

def col_edges(page, box):
    """Bordas verticais reais do quadro -> limites das colunas."""
    x0,x1,yh,yi,yf=box
    cr=page.crop((max(0,x0),yh-2,min(page.width,x1),yf+2))
    ed=sorted({round(e['x0'],1) for e in cr.vertical_edges})
    out=[]
    for e in ed:
        if not out or e-out[-1]>3: out.append(e)
    return out

def produtos_da_pagina(page, produtos_praca):
    """Produtos do catálogo citados na página (banners/rodapé), do mais específico ao genérico."""
    txt=sq(page.extract_text() or '')
    achados=[p for p in sorted(produtos_praca,key=lambda x:-len(x)) if sq(p) in txt]
    out=[]
    for p in achados:
        if not any(sq(p) in sq(o) and o!=p for o in out): out.append(p)
    return out or list(produtos_praca)

def parse_box(page, box, praca, fonte, produtos_praca):
    x0,x1,yh,yi,yf=box
    ed=col_edges(page,box)
    if len(ed)<3: return {}
    x1=ed[-1]
    lims=list(zip(ed[:-1],ed[1:]))
    ws=[w for w in page.extract_words(x_tolerance=1.2) if ed[0]-2<=w['x0']<=x1 and yh-16<=w['top']<=yf]
    pg_prods=produtos_da_pagina(page,produtos_praca)
    grupos={}; prod_lbls=[]
    for r in rows_of([w for w in ws if w['top']<yi-1]):
        txt=sq(' '.join(w['text'] for w in r['w']))
        if 'COPARTIC' in txt and ('PARCIAL' in txt or txt.count('COPARTIC')>=1):
            for gi,(a,bb) in enumerate(lims):
                cel=sq(' '.join(w['text'] for w in r['w'] if a-3<=w['x0']<bb))
                if 'PARCIAL' in cel: grupos[gi]='parcial'
                elif 'COPARTIC' in cel and 'PROCEDIMENTO' not in cel: grupos[gi]='total'
        # rótulos de produto: detectar POR CÉLULA (a linha pode conter 'COPARTICIPAÇÃO' na 1ª coluna)
        cands=[(p,sq(p)) for p in sorted(produtos_praca,key=lambda x:-len(x))]+[('__DEMAIS__','DEMAIS PRODUTOS')]
        for gi,(a,bb) in enumerate(lims):
            cel=sq(' '.join(w['text'] for w in r['w'] if a-3<=w['x0']<bb))
            if not cel or 'COPARTIC' in cel or 'PROCEDIMENTO' in cel: continue
            for nome,chave in cands:
                if cel==chave or (chave in cel and len(chave)>6):
                    prod_lbls.append((nome,gi)); break
    if not grupos:  # quadro sem nível parcial/total (ex.: NDI Minas) -> coluna por produto = total
        for gi,(a,bb) in enumerate(lims):
            if gi==0: continue
            if any(nome!='__DEMAIS__' for nome,ci in prod_lbls if ci==gi): grupos[gi]='total'
    if not grupos: return {}
    dcols=sorted(grupos)                       # colunas de dados
    prod_lbls=sorted(set(prod_lbls),key=lambda t:t[1])
    col_prod={}
    if prod_lbls:
        for gi in dcols:
            atual=None
            for nome,ci in prod_lbls:
                if ci<=gi: atual=nome
            col_prod[gi]=atual or prod_lbls[0][0]
    dados={}
    for r in rows_of([w for w in ws if w['top']>=yi-1]):
        rot=' '.join(w['text'] for w in r['w'] if w['x0']<lims[0][1])
        p=proc_of(rot)
        if not p: continue
        for gi,(a,bb) in enumerate(lims):
            if gi not in grupos: continue
            cel=[w['text'] for w in r['w'] if a-3<=w['x0']<bb]
            val=re.sub(r'\s+',' ',' '.join(cel)).strip()
            val=re.sub(r'^[-–]\s*','',val).strip()
            dados.setdefault((col_prod.get(gi),grupos[gi]),{})[p]= val_ok(val)
    if not dados: return {}
    rotulados=[p for p,_ in prod_lbls if p!='__DEMAIS__']
    demais=[p for p in pg_prods if p not in rotulados]
    out={}
    def bloco(key_prod):
        return (dados.get((key_prod,'parcial')) or {}, dados.get((key_prod,'total')) or {})
    if prod_lbls:
        for nome,_ in prod_lbls:
            par,tot=bloco(nome)
            if not (par or tot): continue
            alvos=[nome] if nome!='__DEMAIS__' else demais
            for a in alvos: out[a]={'parcial':par,'total':tot,'fonte':fonte}
    else:
        par,tot=bloco(None)
        for a in pg_prods: out[a]={'parcial':par,'total':tot,'fonte':fonte}
    return out


def parse_page(page, praca, fonte, produtos_praca):
    agg={}
    for bi,box in enumerate(find_boxes(page)):
        try: r=parse_box(page,box,praca,f'{fonte}',produtos_praca)
        except Exception: continue
        for prod,v in r.items():
            cur=agg.setdefault(prod,{'parcial':{},'total':{},'fonte':v['fonte']})
            for g in ('parcial','total'):
                for k,val in (v.get(g) or {}).items():
                    if val and not cur[g].get(k): cur[g][k]=val
                    elif k not in cur[g]: cur[g][k]=cur[g].get(k)
    return agg

FONTES=[
 ('/Users/marcoscorrea/Downloads/OneDrive_1_24-08-2026/20260824 a 20260930 - PME.pdf','PME 24/08',1),
 ('/Users/marcoscorrea/Downloads/OneDrive_1_24-08-2026/20260824 a 20260930 - Super Simples 2 a 29 vidas.pdf','SS 24/08',2),
 ('/Users/marcoscorrea/Downloads/OneDrive_1_12-08-2026/20260801 a 20260930 - PME (2).pdf','PME 01/08',3),
 ('/Users/marcoscorrea/Downloads/OneDrive_1_12-08-2026/20260801 a 20260930 - Super Simples 2 a 29 vidas (2).pdf','SS 01/08',4),
 ('/Users/marcoscorrea/Downloads/OneDrive_1_12-08-2026/20260701 a 20260930 - Individual.pdf','Individual',9),
 ('/Users/marcoscorrea/Downloads/OneDrive_2_12-08-2026/20260801 a 20260930 - PME NDI Minas (2).pdf','PME Minas',1),
 ('/Users/marcoscorrea/Downloads/OneDrive_2_12-08-2026/20260801 a 20260930 - Super Simples (2).pdf','SS Minas',2),
 ('/Users/marcoscorrea/Downloads/OneDrive_3_12-08-2026/20260724 a 20260930 - PME (1).pdf','PME Sul',1),
 ('/Users/marcoscorrea/Downloads/OneDrive_3_12-08-2026/20260724 a 20260930 - Super Simples.pdf','SS Sul',2),
 ('/Users/marcoscorrea/Downloads/OneDrive_4_12-08-2026/20260724 a 20260930 - PME.pdf','PME RS',1),
 ('/Users/marcoscorrea/Downloads/OneDrive_4_12-08-2026/20260724 a 20260930 - Super Simples - 2 a 29 vidas.pdf','SS RS',2),
]
CIDADE_RE=re.compile(r'\n([A-Za-zÀ-ÿ\.\' ]+ ?-? ?[A-Z]{2})\n')
def praca_of(page, pracas):
    t=page.extract_text() or ''
    top=sq(t[:300])
    for p in pracas:
        ci=sq(p.rsplit(' - ',1)[0])
        if ci in top: return p
    return None

def main():
    mapa=json.load(open('/tmp/pracas_sem_copart.json'))
    pracas=list(mapa)
    out={}
    for path,tag,prio in FONTES:
        if not os.path.exists(path): print('faltando:',path); continue
        pdf=pdfplumber.open(path)
        n=0
        for pi,page in enumerate(pdf.pages):
            pr=praca_of(page,pracas)
            if not pr: continue
            try: r=parse_page(page,pr,f'{tag} p{pi+1}',mapa[pr])
            except Exception as e: print(f'  !! {pr} {tag} p{pi+1}: {e}'); continue
            if not r: continue
            for prod,v in r.items():
                if prod not in mapa[pr]: continue
                cur=out.setdefault(pr,{})
                nnovo=sum(1 for g in ('parcial','total') for x in (v.get(g) or {}).values() if x)
                if not nnovo: continue
                if prod not in cur or prio<cur[prod].get('_prio',9) or (prio==cur[prod].get('_prio',9) and nnovo>cur[prod].get('_n',0)):
                    v['_prio']=prio; v['_n']=nnovo; cur[prod]=v
            n+=1
        print(f'{tag:<12} páginas com quadro: {n}')
    # herança: produto sem dados herda de produto cujo nome é prefixo (Nosso Plano Municipal <- Nosso Plano)
    herd=0
    for pr,prods in out.items():
        for alvo in mapa[pr]:
            if alvo in prods: continue
            base=[p for p in prods if alvo.startswith(p) and p!=alvo]
            if base:
                v=dict(prods[max(base,key=len)]); v['fonte']+=' (herdado)'
                prods[alvo]=v; herd+=1
    for pr in out:
        for p in out[pr]:
            out[pr][p].pop('_prio',None); out[pr][p].pop('_n',None)
    json.dump(out,open('/tmp/copart_parsed.json','w'),ensure_ascii=False,indent=1)
    cob=sum(len(v) for v in out.values()); alvo=sum(len(v) for v in mapa.values())
    print(f'\npraças: {len(out)}/{len(mapa)} | produtos: {cob}/{alvo} (herdados: {herd})')
    falta={p:[x for x in mapa[p] if x not in out.get(p,{})] for p in mapa}
    falta={k:v for k,v in falta.items() if v}
    print('sem dados:',len(falta),'praças')
    for k,v in list(falta.items())[:12]: print('  ',k,v)

if __name__=='__main__':
    main()
