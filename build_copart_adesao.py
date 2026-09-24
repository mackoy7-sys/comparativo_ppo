#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COPARTICIPACAO DO COLETIVO POR ADESAO -> copart.json

A coparticipacao do Adesao NAO e a mesma do PME. Em Joao Pessoa a consulta
eletiva e R$ 23,53 no Adesao e R$ 25,42 no PME; em Franca, R$ 40,39 contra
R$ 43,63. Sem esta carga o folder imprimiria o numero do PME para um plano de
Adesao — que e exatamente o tipo de erro que a gente passou ontem corrigindo.

Grava sob a chave "<plano> · Adesão", separada da do PME.
Ensaio por padrao; grava so com --gravar.
"""
import collections, glob, json, os, re, shutil, sys, time
import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_todos import get_rows, row_text, deacc

BASE = "/Users/marcoscorrea/Downloads/TABELA DO FLAMENGO"
AQUI = os.path.dirname(os.path.abspath(__file__))
COP = os.path.join(AQUI, "copart.json")

PROCS = ["Consultas Eletivas", "Consultas de Urgência", "Exames Simples",
         "Exames Complexos", "Terapias Especiais", "Demais Terapias", "Internações"]
SAIDA = {"Consultas Eletivas": "Consultas eletivas", "Consultas de Urgência": "Consultas de urgência",
         "Exames Simples": "Exames simples", "Exames Complexos": "Exames complexos",
         "Terapias Especiais": "Terapias especiais", "Demais Terapias": "Demais terapias",
         "Internações": "Internações"}

# cabecalho da caixa -> planos a que a coluna se aplica (campo "plano" do catalogo)
GRUPOS = [
    (r"SMART", ["Smart 200", "Smart 200 UP", "Smart 200 SP Capital",
                                        "Smart 200 Campinas", "Smart 200 Jundiaí", "Smart 200 Sorocaba",
                                        "Smart 200 Americana", "Smart 200 ABC", "Smart 200 Rio",
                                        "Smart 150 ABC", "Smart 150 Leste Fluminense",
                                        "Smart 200 UP+RMCA", "Smart 300", "Smart 400", "Smart 500"]),
    (r"ADVANCE", ["600", "700"]),
]


def _chave(s):
    import unicodedata
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace(" ", "")


_CAT = {}
def nome_praca(p):
    """Os PDFs escrevem a praça em caixa alta; o catálogo tem a grafia oficial."""
    if not _CAT:
        for e in json.load(open(os.path.join(AQUI, "catalog.json"))):
            _CAT[_chave(e.get("praca") or "SP / RMSP")] = e.get("praca") or "SP / RMSP"
        _CAT[_chave("São Paulo - SP")] = "SP / RMSP"
    return _CAT.get(_chave(p))


def praca_de(page):
    for r in get_rows(page)[:6]:
        t = row_text(r).strip()
        if re.match(r"^[A-Za-zÀ-ÿ\.' ]+\s*-\s*[A-Z]{2}$", t):
            return re.sub(r"\s*-\s*", " - ", t).strip()
    return None


def caixa(page):
    """Le a caixa COPARTICIPAÇÃO POR PROCEDIMENTO. Devolve (cabecalhos, {proc: [valores]})."""
    rows = get_rows(page)
    hdr = None
    for r in rows:
        w = [x for x in r["words"] if deacc(x["text"]).upper() == "PROCEDIMENTO"]
        if w:
            x0 = w[0]["x0"]
            resto = [x for x in r["words"] if x["x0"] > w[0]["x1"]]
            if not resto: continue
            cols, cur = [], None
            for x in resto:
                if cur and (x["x0"] - cur[2]) <= 14: cur[0] += " " + x["text"]; cur[2] = x["x1"]
                else:
                    if cur: cols.append(tuple(cur))
                    cur = [x["text"], x["x0"], x["x1"]]
            if cur: cols.append(tuple(cur))
            hdr = (x0, cols)
            break
    if not hdr: return None, {}
    x0, cols = hdr
    vals = {}
    for r in rows:
        t = row_text(r)
        proc = next((p for p in PROCS if re.search(re.escape(p) + r"\*?\b", t)), None)
        if not proc or proc in vals: continue
        ws = [w for w in r["words"] if w["x0"] >= x0 - 2]
        # descarta as palavras do proprio rotulo do procedimento
        rot = proc.split()
        while ws and deacc(ws[0]["text"]).strip("*").upper() in [deacc(p).upper() for p in rot]:
            ws.pop(0)
        celas = [[] for _ in cols]
        for w in ws:
            i = min(range(len(cols)), key=lambda k: abs(cols[k][1] - w["x0"]) if w["x0"] >= cols[k][1] - 30 else 1e9)
            celas[i].append(w["text"])
        vals[proc] = [" ".join(c).strip() for c in celas]
    return cols, vals


def limpa(v):
    v = re.sub(r"\s+", " ", (v or "").strip())
    if v in ("", "-", "- -", "--"): return None
    v = re.sub(r"^-\s*", "", v)
    return v or None


def main():
    achados = collections.defaultdict(dict)   # praca -> plano -> {parcial/total}
    for f in sorted(glob.glob(BASE + "/HAPVIDA/*.pdf")) + sorted(glob.glob(BASE + "/NDI SP/*.pdf")):
        grupo = "parcial" if "Parcial" in f else "total"
        ndi = "/NDI SP/" in f
        with pdfplumber.open(f) as pdf:
            for page in pdf.pages:
                praca = praca_de(page)
                if not praca: continue
                praca = nome_praca(praca)
                if not praca: continue
                cols, vals = caixa(page)
                if not vals: continue
                for ci, (nome, _, _) in enumerate(cols):
                    up = deacc(nome).upper()
                    planos = None
                    if ndi:
                        # na tabela Parcial as duas familias dividem UMA coluna
                        # ("SMART 200/300/400/500 E ADVANCE 600/700"): vale para as duas.
                        planos = [x for rx, ps in GRUPOS if re.search(rx, up) for x in ps]
                    else:
                        planos = ["Nosso Plano", "Pleno"]   # produto medico da pagina Hapvida
                    if not planos: continue
                    dado = {SAIDA[p]: limpa(vals[p][ci]) for p in PROCS if p in vals}
                    if not any(dado.values()): continue
                    for pl in planos:
                        k = pl + " · Adesão"
                        achados[praca].setdefault(k, {"fonte": "Adesão OVER " + os.path.basename(f)[:17]})
                        achados[praca][k][grupo] = dado

    n = sum(len(v) for v in achados.values())
    print("praças: %d  |  entradas plano×praça: %d" % (len(achados), n))
    for pr in list(achados)[:3]:
        k = list(achados[pr])[0]
        print("  %s / %s" % (pr, k))
        print("     total  :", json.dumps(achados[pr][k].get("total"), ensure_ascii=False))
        print("     parcial:", json.dumps(achados[pr][k].get("parcial"), ensure_ascii=False))

    cop = json.load(open(COP))
    novas = sum(1 for pr, d in achados.items() for k in d if k not in cop.get(pr, {}))
    print("\nchaves novas (nenhuma existente é tocada): %d" % novas)
    colide = [(pr, k) for pr, d in achados.items() for k in d if k in cop.get(pr, {})]
    if colide: print("!! colisão com chave existente: %s" % colide[:3]); return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0
    shutil.copy2(COP, COP + ".bak-adesao-" + time.strftime("%Y%m%d-%H%M%S"))
    for pr, d in achados.items(): cop.setdefault(pr, {}).update(d)
    json.dump(cop, open(COP, "w"), ensure_ascii=False)
    print("\ngravado em copart.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
