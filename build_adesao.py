#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LE AS TABELAS DE COLETIVO POR ADESAO (Projeto Flamengo / administradora OVER).

Terceiro segmento do cotador, ao lado de Individual e PME. Nao grava no
catalog.json: joga o material bruto num JSON do scratchpad para conferencia.
Quem grava e o merge_adesao.py, depois das travas.

Cada coluna sai identificada pelo CÓD. INTERNO e pelo REGISTRO ANS — sao os
identificadores que a propria fonte emite. O rotulo impresso pode estar
trocado (foi o que aconteceu em Mogi/SBC em 23/09); o codigo nao.

Uso: python3 build_adesao.py [--json <saida>]
"""
import glob, json, os, re, sys, unicodedata
import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_todos import get_rows, row_text, merge_values, faixa_of, deacc, BANDS

BASE = "/Users/marcoscorrea/Downloads/TABELA DO FLAMENGO"
SAIDA = "/private/tmp/claude-502/-Users-marcoscorrea/c9a5af99-295e-4076-8dfd-4750e4f0a0a9/scratchpad/adesao_bruto.json"

ANS_RE = re.compile(r"^\d{3}\.\d{3}/\d{2}-\d$")
COD_RE = re.compile(r"^\d{4,6}$")


def pastas():
    """HAPVIDA 2 e copia byte a byte de HAPVIDA — conferido por md5. Fica de fora."""
    return sorted(glob.glob(BASE + "/HAPVIDA/*.pdf")) + sorted(glob.glob(BASE + "/NDI SP/*.pdf"))


def cabecalho(page):
    """(praca, vigencia) das tres primeiras linhas."""
    rows = get_rows(page)
    praca, vig = None, None
    for r in rows[:6]:
        t = row_text(r).strip()
        if "Para contratos assinados" in t or t.startswith("Vigência:"):
            # "Para contratos assinados de X a Y" e "Vigência: X a Y" — o "de" é opcional
            m = re.search(r"(?:de )?(\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})", t)
            if m: vig = m.group(1) + " a " + m.group(2)
        elif praca is None and re.match(r"^[A-Za-zÀ-ÿ\.' ]+\s*-\s*[A-Z]{2}$", t):
            praca = re.sub(r"\s*-\s*", " - ", t).strip()
    return praca, vig


def blocos(page):
    """Quadros de preco da pagina. Cada bloco traz as colunas ancoradas na linha
    ACOMODAÇÃO, com o codigo interno e o registro ANS de cada uma."""
    rows = get_rows(page)
    out, cur, recentes, cop = [], None, [], None

    for r in rows:
        ws = r["words"]
        if not ws: continue
        first = ws[0]["text"]
        t = row_text(r)
        u = deacc(t).upper()

        if deacc(first).upper().startswith("COPARTICIPACAO"):
            cop = u.replace(" ", "")
        if first != "PRODUTO":
            recentes.append(t)
            recentes[:] = recentes[-4:]

        if first == "PRODUTO":
            # a caixa lateral de regras ("PROCEDIMENTO ...") mora na mesma faixa
            # de linhas do quadro; corta-se nela em vez de num x fixo.
            corte = next((w["x0"] for w in ws[1:]
                          if deacc(w["text"]).upper().startswith("PROCEDIMENTO")), 99999)
            cur = {"prod": [w for w in ws[1:] if w["x0"] < corte], "xlimit": corte,
                   "acoms": None, "cols": [], "cods": [], "ans": [], "assist": [],
                   "precos": {}, "cop_bloco": cop, "acima": " | ".join(recentes[-3:])}
            out.append(cur)
            continue
        if cur is None: continue

        ws = [w for w in ws if w["x0"] < cur["xlimit"]]
        if not ws: continue

        if first.startswith("ACOMODAÇ") and cur["acoms"] is None:
            acoms, xs, pulo = [], [], False
            for i, w in enumerate(ws[1:]):
                if pulo: pulo = False; continue
                x = deacc(w["text"]).upper()
                if x.startswith("ENFERM"): acoms.append("Enfermaria")
                elif x.startswith("APART"): acoms.append("Apartamento")
                elif x.startswith("AMBULAT"): acoms.append("Ambulatorial")
                elif x.startswith("SEM"):
                    acoms.append("Sem Acomodação")
                    pulo = i + 2 < len(ws) and deacc(ws[i+2]["text"]).upper().startswith("ACOMODAC")
                else: continue
                xs.append(w["x0"])
            cur["acoms"], cur["cols"] = acoms, xs
        elif first.startswith("ASSIST"):
            cur["assist"] = [(w["text"], w["x0"]) for w in ws[1:]]
        elif first == "REGISTRO" and not cur["ans"]:
            cur["ans"] = [(w["text"], w["x0"]) for w in ws if ANS_RE.match(w["text"])]
        elif first.startswith("CÓD") and not cur["cods"]:
            cur["cods"] = [(w["text"], w["x0"]) for w in ws if COD_RE.match(w["text"])]
        elif cur["acoms"] and faixa_of(t):
            fx = faixa_of(t)
            vals = merge_values(ws)
            if vals and fx not in cur["precos"]:
                cur["precos"][fx] = vals

    return [b for b in out if b["acoms"] and len(b["precos"]) == 10]


def perto(lista, x, tol=40):
    """Item de (texto, x) cujo x fica mais proximo da ancora — None se longe demais."""
    if not lista: return None
    t, dx = min(((t, abs(px - x)) for t, px in lista), key=lambda p: p[1])
    return t if dx <= tol else None


def spans_produto(prod):
    """Agrupa as palavras do cabecalho PRODUTO em nomes, por distancia."""
    spans, cur = [], None
    for w in prod:
        if cur and (w["x0"] - cur[2]) < 18:
            cur[0] += " " + w["text"]; cur[2] = w["x1"]
        else:
            if cur: spans.append(tuple(cur))
            cur = [w["text"], w["x0"], w["x1"]]
    if cur: spans.append(tuple(cur))
    return [(re.sub(r"\s+", " ", n).strip(), a, b) for n, a, b in spans]


def colunas(b):
    """Uma entrada por coluna do quadro."""
    sp = spans_produto(b["prod"])
    if not sp: return []
    lim = [(sp[i][2] + sp[i+1][1]) / 2 for i in range(len(sp) - 1)]
    saida = []
    for ci, x in enumerate(b["cols"]):
        pi = sum(1 for L in lim if x + 12 > L)
        nome = sp[min(pi, len(sp) - 1)][0]
        pr = {}
        for fx, vals in b["precos"].items():
            vs = sorted(vals, key=lambda v: v[1])
            pr[fx] = (vs[ci][0] if len(vs) == len(b["cols"])
                      else min(vs, key=lambda v: abs(v[1] - x - 15))[0])
        saida.append({"produto": nome, "acomodacao": b["acoms"][ci], "col": ci,
                      "cod": perto(b["cods"], x), "ans": perto(b["ans"], x),
                      "assist": perto(b["assist"], x, 30), "precos": pr})
    return saida


# ------------------------------------------------------------------ layout Hapvida
# As paginas da Hapvida nao tem linha PRODUTO: o nome do plano vem no titulo com
# as letras espacadas ("N O S S O  P L A N O"). As colunas se ancoram no
# CÓD. INTERNO, e cada uma carrega ainda a linha ASSISTÊNCIA (Médica ¹ / ²).

ACOM_MAP = {"ENFERMARIA": "Enfermaria", "APARTAMENTO": "Apartamento",
            "SEMACOMODACAO": "Sem Acomodação", "AMBULATORIAL": "Ambulatorial"}


def _acom(t):
    return ACOM_MAP.get(deacc(t).upper().replace(" ", ""), t)


def _junta(itens, gap, sep=""):
    """Agrupa (texto,x0,x1) vizinhos quando a folga entre eles cabe em gap."""
    out, cur = [], None
    for t, a, b in sorted(itens, key=lambda i: i[1]):
        if cur and (a - cur[2]) <= gap:
            cur[0] += sep + t; cur[2] = b
        else:
            if cur: out.append(tuple(cur))
            cur = [t, a, b]
    if cur: out.append(tuple(cur))
    return out


def _palavras(ws, gap_letra=2.5, gap_palavra=12):
    """Letras espacadas -> palavras -> nomes de produto, com o x de cada um."""
    itens = [(w["text"], w["x0"], w["x1"]) for w in ws]
    return _junta(_junta(itens, gap_letra), gap_palavra, sep=" ")


def _linha_titulo(rows):
    """O titulo vem SEMPRE na linha imediatamente acima da linha COPARTICIPAÇÃO
    (a que tem o rotulo na coluna da esquerda). Regra estrutural — nao depende
    de contar letras soltas, que falhava em titulos curtos como "P L E N O"."""
    for i, r in enumerate(rows):
        ws = r["words"]
        if ws and ws[0]["x0"] < 60 and deacc(ws[0]["text"]).upper().startswith("COPARTICIPAC"):
            return rows[i - 1] if i else None
    return None


def _nome_esquerda(linha, xlim):
    """Nome do produto das colunas medicas: tudo que esta a esquerda de xlim no
    titulo. As letras vem espacadas, entao junta-se tudo e reconhece-se o nome
    por dicionario — o PDF e a fonte, e estes sao os produtos que ele traz."""
    if not linha: return None
    t = "".join(w["text"] for w in sorted(linha["words"], key=lambda w: w["x0"])
                if w["x0"] < xlim)
    return deacc(t).upper().replace(" ", "") or None


def blocos_hapvida(page):
    rows = get_rows(page)
    linha_tit = _linha_titulo(rows)
    acoms = assist = cods = seg = None
    precos = {}
    for r in rows:
        ws = r["words"]
        if not ws: continue
        first = deacc(ws[0]["text"]).upper()
        if first.startswith("ACOMODAC") and acoms is None:
            acoms = _palavras(ws[1:])
        elif first.startswith("ASSISTENCIA") and assist is None:
            assist = _palavras(ws[1:])
        elif first.startswith("COD") and cods is None:
            cods = [(w["text"], w["x0"], w["x1"]) for w in ws if COD_RE.match(w["text"])]
        elif first.startswith("SEGMENTAC") and seg is None:
            seg = deacc(row_text(r)).upper()
        elif faixa_of(row_text(r)) and len(precos) < 10:
            fx = faixa_of(row_text(r))
            vals = merge_values(ws)
            if vals and fx not in precos: precos[fx] = vals
    if not (cods and acoms and len(precos) == 10):
        return []

    meio = lambda t: (t[1] + t[2]) / 2
    cods = sorted(cods, key=lambda c: c[1])
    # a coluna medica e a que tem "Médica" na linha ASSISTÊNCIA; o produto delas
    # e o nome que esta a esquerda da primeira coluna nao-medica (Referencia).
    def eh_med(c):
        if not assist: return False
        return "MEDICA" in deacc(min(assist, key=lambda a: abs(meio(a) - meio(c)))[0]).upper()
    med = [c for c in cods if eh_med(c)]
    naomed = [c for c in cods if not eh_med(c)]
    # corta no meio do caminho entre a ultima coluna medica e a primeira que nao
    # e: o nome do plano-referencia fica centrado sobre a coluna dele e pode
    # comecar a esquerda do proprio codigo.
    xlim = ((med[-1][2] + naomed[0][1]) / 2) if (med and naomed) else 99999
    prod = _nome_esquerda(linha_tit, xlim)
    saida = []
    for ci, c in enumerate(cods):
        cx = meio(c)
        ac = min(acoms, key=lambda a: abs(meio(a) - cx))[0].upper()
        # nas tabelas Ambulatoriais a linha ACOMODAÇÃO diz "SEM ACOMODAÇÃO";
        # quem define e a SEGMENTAÇÃO.
        if deacc(ac).replace(" ", "").startswith("SEMACOMODAC") and seg and "AMBULATORIAL" in seg:
            ac = "AMBULATORIAL"
        asx = min(assist, key=lambda a: abs(meio(a) - cx))[0] if assist else None
        pr = {}
        for fx, vals in precos.items():
            vs = sorted(vals, key=lambda v: v[1])
            pr[fx] = vs[ci][0] if len(vs) == len(cods) else min(
                vs, key=lambda v: abs(v[1] - cx + 20))[0]
        saida.append({"produto": prod, "acomodacao": _acom(ac), "col": ci,
                      "cod": c[0], "ans": None, "assist": asx,
                      "medica": eh_med(c), "precos": pr})
    return saida


def main():
    tudo, avisos = [], []
    for f in pastas():
        arq = os.path.relpath(f, BASE)
        with pdfplumber.open(f) as pdf:
            for pgi, page in enumerate(pdf.pages, 1):
                praca, vig = cabecalho(page)
                if praca is None:
                    avisos.append("%s pg%d: praça não reconhecida no cabeçalho" % (arq, pgi))
                cols = [c for b in blocos(page) for c in colunas(b)]
                if not cols:
                    cols = blocos_hapvida(page)   # paginas Hapvida, sem linha PRODUTO
                if not cols:
                    avisos.append("%s pg%d: nenhum quadro lido" % (arq, pgi))
                for c in cols:
                    c.setdefault("cop_bloco", None); c.setdefault("acima", "")
                    c.update(arquivo=arq, pg=pgi, praca=praca, vigencia=vig)
                    tudo.append(c)

    json.dump(tudo, open(SAIDA, "w"), ensure_ascii=False, indent=1)
    print("colunas lidas: %d  ->  %s" % (len(tudo), SAIDA))
    sem = [c for c in tudo if not c["cod"]]
    print("sem CÓD. INTERNO: %d" % len(sem))
    for a in avisos[:12]: print("  aviso:", a)
    return tudo


if __name__ == "__main__":
    main()
