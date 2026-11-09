#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga HMO (linha Smart) da vigência 09/11/2026 a 30/11/2026
-> /tmp/hmo1109_parsed.json

Remessa de 09/11 em pasta própria (~/Downloads/OneDrive_2_09-11-2026), 7 PDFs:

    Super Simples 1 Vida .................. 10 praças · porte 1 vida
    Super Simples 2 a 29 - Demais Empresas . 9 praças · não-MEI
    Super Simples 2 a 29 - MEI ............. 9 praças · MEI
    Super Simples 2 a 29 - Demais Praças ... 1 praça (SJC) · Pleno Vale do Paraíba
    PME - Compulsório v2 ................... 9 praças · 30 a 99 · Compulsório
    PME - Adesão v2 ........................ 9 praças · 30 a 99 · Adesão
    PME - Demais Praças .................... 1 praça (SJC) · Pleno Vale do Paraíba

A pasta 4 da mesma remessa é a UNIÃO desta com a do PPO/Metais (pasta 3) —
conferido pelo CÓD. INTERNO: 72 = 32 + 41 - 1 (o 40832, do odonto, está nas
duas). Por isso carregar as pastas 2 e 3 cobre a 4 inteira.

⚠ COPARTICIPAÇÃO É POR COLUNA, NÃO POR BLOCO. Num mesmo bloco o cabeçalho traz
"COPARTICIPAÇÃO PARCIAL" cobrindo as primeiras colunas e "SEM COPARTICIPAÇÃO"
cobrindo a última (Basic Referência). Ler o rótulo da linha inteira põe o preço
no eixo errado — então cada caixa de rótulo é medida por x e aplicada à coluna
que ela cobre, com o nível da página ("COM COPARTICIPAÇÃO PARCIAL/TOTAL") como
padrão para as colunas que nenhuma caixa cobre.

Colunas ancoradas no CÓD. INTERNO: o rótulo PRODUTO cobre mais de uma coluna
(SMART UP tem enfermaria e apartamento) e só o código distingue.

NÃO grava no catálogo: escreve o JSON e o merge_hmo1109.py aplica.
"""
import collections, json, os, re, sys, unicodedata
import pdfplumber

D = "/Users/marcoscorrea/Downloads/OneDrive_2_09-11-2026/"
OUT = "/tmp/hmo1109_parsed.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]

PRACA_MAP = {"São Paulo - SP": "SP / RMSP",
             "São José dos Campos - SP": "São José Dos Campos - SP"}

# PRODUTO do PDF -> plano do catálogo. "Nosso Médico <cidade>" é o Nosso Médico
# daquela praça; só o da capital tem rótulo próprio (Nosso Médico RMSP).
PROD_MAP = {
    "NOSSO MÉDICO RMSP": "Nosso Médico RMSP",
    "NOSSO MÉDICO AMERICANA": "Nosso Médico",
    "NOSSO MÉDICO CAMPINAS": "Nosso Médico",
    "NOSSO MÉDICO JUNDIAÍ": "Nosso Médico",
    "NOSSO MÉDICO SOROCABA": "Nosso Médico",
    "SMART UP": "Smart UP",
    "SMART 300": "Smart 300",
    "SMART 500": "Smart 500",
    "SMART FLEX SP": "Smart Flex",
    "SMART PRIME": "Smart Prime",
    "SMART 200 RIO": "Smart 200 Rio",
    "PLENO VALE DO PARAÍBA": "Pleno Vale do Paraíba",
    # NOVO nesta remessa: não existe no catálogo. Sai marcado e o merge decide.
    "BASIC REFERÊNCIA": "__NOVO__Basic Referência",
}

ARQS = [
    ("Super Simples 1 Vida", dict(vmin=1, vmax=1, mei=False)),
    ("Super Simples 2 a 29 vidas - Demais Empresas", dict(vmin=2, vmax=29, mei=False)),
    ("Super Simples 2 a 29 vidas - MEI", dict(vmin=2, vmax=29, mei=True)),
    ("Super Simples 2 a 29 vidas - Demais Praças", dict(vmin=2, vmax=29, mei=False)),
    ("PME - Compulsório v2", dict(vmin=30, vmax=99, mei=False, contratacao="Compulsório")),
    ("PME - Adesão v2", dict(vmin=30, vmax=99, mei=False, contratacao="Adesão")),
    ("PME - Demais Praças", dict(vmin=30, vmax=99, mei=False, contratacao="Compulsório")),
]


def sq(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return s.upper().replace(" ", "")


def acha(chave):
    for f in sorted(os.listdir(D)):
        if f.lower().endswith(".pdf") and sq(chave) in sq(f):
            return f
    return None


def linhas(page, tol=3.0):
    out = []
    for w in sorted(page.extract_words(keep_blank_chars=False, x_tolerance=1.2),
                    key=lambda w: (w["top"], w["x0"])):
        for r in out:
            if abs(r["top"] - w["top"]) <= tol:
                r["w"].append(w); break
        else:
            out.append({"top": w["top"], "w": [w]})
    for r in out:
        r["w"].sort(key=lambda w: w["x0"])
        r["txt"] = " ".join(w["text"] for w in r["w"])
    return out


def junta(ws, gap=6):
    g, at = [], None
    for w in ws:
        if at and w["x0"] - at["x1"] <= gap:
            at["text"] += " " + w["text"]; at["x1"] = w["x1"]
        else:
            at = dict(text=w["text"], x0=w["x0"], x1=w["x1"]); g.append(at)
    return g


def num(s):
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


INCOMPLETAS = []

BAND_RE = re.compile(r"^(00a18|19a23|24a28|29a33|34a38|39a43|44a48|49a53|54a58|59)(ANOS|ANOSOUMAIS)?$")


def banda_de(txt):
    s = sq(txt).replace("ANOSOUMAIS", "").replace("ANOS", "")
    for b in BANDS:
        if s == sq(b) or (b == "59 ou mais" and s == "59"):
            return b
    return None


def parse():
    result = collections.defaultdict(list)
    for chave, meta in ARQS:
        fn = acha(chave)
        if not fn:
            print("  ! não achei o PDF de %s — pulado" % chave); continue
        n_arq = 0
        with pdfplumber.open(D + fn) as pdf:
            for page in pdf.pages:
                ls = linhas(page)
                txt = [l["txt"] for l in ls]
                if len(txt) < 3:
                    continue
                praca = PRACA_MAP.get(txt[1], txt[1])
                nivel = next((t for t in txt[:8] if sq(t).startswith("COMCOPARTICIPACAO")), "")
                for i, l in enumerate(ls):
                    if not sq(l["txt"]).startswith("COD.INTERNO"):
                        continue
                    cods = [w for w in l["w"] if re.fullmatch(r"\d{5}", w["text"])]
                    if not cods:
                        continue

                    def acima(pref, lim=8):
                        for j in range(i - 1, max(i - lim, -1), -1):
                            if sq(ls[j]["txt"]).startswith(pref):
                                return ls[j]
                        return None

                    lprod, lacom, lcop = acima("PRODUTO"), acima("ACOMODACAO"), acima("COPARTICIPACAO", 10)
                    lans = acima("REGISTROANS")
                    if not (lprod and lacom):
                        continue
                    prods = junta([w for w in lprod["w"] if w["text"].upper() != "PRODUTO"])
                    acoms = [w for w in lacom["w"] if sq(w["text"]) in ("ENFERM", "APART",
                             "ENFERMARIA", "APARTAMENTO")]
                    x_1a = min(c["x0"] for c in cods) - 12
                    caixas = []
                    if lcop:
                        # folga MAIOR so nesta linha: o rotulo vem com as letras
                        # espacadas ("C O M  C O P A R T I C I P A Ç Ã O  P A R C I A L")
                        # e, com folga 6, so o pedaco "PARCIAL" era reconhecido — a
                        # caixa comecava no lugar errado e a coluna TOTAL de SJC saia
                        # como parcial (144,50 no lugar de 217,33). Com 12 o rotulo
                        # inteiro vira uma caixa e os dois rotulos seguem separados.
                        for g in junta([w for w in lcop["w"] if w["x1"] > x_1a], gap=12):
                            s = sq(g["text"])
                            if "SEMCOPARTICIPACAO" in s: caixas.append((g["x0"], "Sem"))
                            elif "PARCIAL" in s: caixas.append((g["x0"], "Parcial"))
                            elif "TOTAL" in s: caixas.append((g["x0"], "Completa"))
                    caixas.sort()
                    sn = sq(nivel)
                    padrao = "Parcial" if "PARCIAL" in sn else "Completa" if "TOTAL" in sn else None

                    anss = [w for w in lans["w"]
                            if re.fullmatch(r"\d{3}\.\d{3}/\d{2}-\d", w["text"])] if lans else []
                    colunas = []
                    for c in cods:
                        x = (c["x0"] + c["x1"]) / 2
                        prod = min(prods, key=lambda p: abs((p["x0"] + p["x1"]) / 2 - x))["text"]
                        acom = min(acoms, key=lambda a: abs((a["x0"] + a["x1"]) / 2 - x))["text"] if acoms else ""
                        ans = min(anss, key=lambda a: abs((a["x0"] + a["x1"]) / 2 - x))["text"] if anss else ""
                        cop = padrao
                        for x0, rot in caixas:
                            if x0 <= x + 4: cop = rot
                        colunas.append(dict(cod=c["text"], x=x, prod=prod.strip(), ans=ans,
                                            acom="Apartamento" if sq(acom).startswith("APART") else "Enfermaria",
                                            copart=cop))

                    # Em SJC o 2o rotulo vem TRUNCADO ("C O M C O P A R T I C I P A
                    # Ç Ã O", sem "T O T A L" — o titulo do reajuste come o resto), e
                    # as 4 colunas caiam todas em Parcial: duas entradas com a MESMA
                    # chave e preco diferente. A fonte da outro sinal: o par
                    # (registro ANS, acomodacao) SE REPETE, e a repeticao marca onde
                    # comeca o grupo da outra coparticipacao.
                    grupo, vistos = [], set()
                    gi = 0
                    for c in colunas:
                        par = (c["ans"], c["acom"])
                        if par in vistos:
                            gi += 1; vistos = {par}
                        else:
                            vistos.add(par)
                        grupo.append(gi)
                    if gi > 0:
                        rotulos = []
                        for _, rot in caixas:
                            if rot not in rotulos: rotulos.append(rot)
                        if len(rotulos) <= gi:   # faltou rotulo: o que sobra e o oposto
                            base_rot = rotulos[0] if rotulos else (padrao or "Parcial")
                            rotulos = [base_rot] + [("Completa" if base_rot == "Parcial" else "Parcial")]
                        for c, k in zip(colunas, grupo):
                            if k < len(rotulos): c["copart"] = rotulos[k]

                    # as 10 faixas logo abaixo deste CÓD. INTERNO
                    precos = {c["cod"]: {} for c in colunas}
                    for j in range(i + 1, min(i + 16, len(ls))):
                        rot = junta(ls[j]["w"])[0] if ls[j]["w"] else None
                        if not rot:
                            break
                        b = banda_de(rot["text"])
                        if not b:
                            if precos[colunas[0]["cod"]]:
                                break
                            continue
                        # Cada PALAVRA vai para a coluna cuja fronteira a contém, e
                        # só depois os pedaços viram número. Agrupar por folga fixa
                        # não serve: no arquivo de 2 a 29 o valor vem quebrado
                        # ("R$ 1 07,92") e pede folga grande, e no de 1 vida ele vem
                        # inteiro ("R$ 132,20") e a mesma folga cola dois valores
                        # vizinhos — a coluna ficava sem número nenhum.
                        # Em SJC a pagina traz a tabela de REAJUSTE ao LADO da de
                        # preco, nas MESMAS linhas: sem borda direita, os "4,00%" da
                        # direita caiam na ultima coluna e a estragavam.
                        passo = 60.0
                        if len(colunas) > 1:
                            difs = sorted(colunas[t]["x"] - colunas[t - 1]["x"]
                                          for t in range(1, len(colunas)))
                            passo = difs[len(difs) // 2]
                        lim_dir = colunas[-1]["x"] + passo * 0.6
                        pedacos = {c["cod"]: [] for c in colunas}
                        for w in ls[j]["w"]:
                            if w["x0"] <= rot["x1"] + 1:
                                continue
                            if "%" in w["text"] or w["text"].startswith("De"):
                                continue
                            if (w["x0"] + w["x1"]) / 2 > lim_dir:
                                continue
                            cx = (w["x0"] + w["x1"]) / 2
                            k = 0
                            for t in range(1, len(colunas)):
                                if cx >= (colunas[t - 1]["x"] + colunas[t]["x"]) / 2:
                                    k = t
                            pedacos[colunas[k]["cod"]].append(w["text"])
                        for c in colunas:
                            n = num("".join(pedacos[c["cod"]]))
                            if n is not None:
                                precos[c["cod"]][b] = n

                    for c in colunas:
                        p = precos[c["cod"]]
                        if len(p) != 10:
                            # coluna que nao fechou as 10 faixas NAO pode sumir
                            # calada: 171 sumiram assim na 1a versao
                            INCOMPLETAS.append((fn[:30], praca, c["prod"], c["cod"], len(p), page.page_number))
                            continue
                        plano = PROD_MAP.get(c["prod"].upper())
                        if not plano:
                            print("  ! produto sem mapa: %r (%s pág)" % (c["prod"], praca)); continue
                        e = dict(operadora="Hapvida", tipo="Empresarial",
                                 praca=praca, plano=plano, label=plano,
                                 acomodacao=c["acom"], coparticipacao=c["copart"],
                                 cod=c["cod"], precos=p, **meta)
                        result[praca].append(e); n_arq += 1
        print("  %-48s %4d colunas" % (fn[:48], n_arq))
    return result


res = parse()
json.dump(res, open(OUT, "w"), ensure_ascii=False)
tot = sum(len(v) for v in res.values())
print("\nTotal: %d entradas em %d praças -> %s" % (tot, len(res), OUT))
if INCOMPLETAS:
    print("\n⚠ %d colunas NÃO fecharam as 10 faixas:" % len(INCOMPLETAS))
    import collections as _c
    for x in INCOMPLETAS[:6]:
        print("   %-30s pág %2d · %-20s %-22s %d faixas" % (x[0], x[5], x[1][:20], x[2][:22], x[4]))
    print("   ... páginas afetadas: %s" % sorted({(x[0][:18], x[5]) for x in INCOMPLETAS})[:8])
novos = [e for v in res.values() for e in v if e["plano"].startswith("__NOVO__")]
print("produtos NOVOS (não existem no catálogo): %d entradas · %s"
      % (len(novos), sorted({e["plano"].replace("__NOVO__", "") for e in novos})))
cnt = collections.Counter((e["plano"], e["acomodacao"], e["coparticipacao"]) for v in res.values() for e in v)
print("\nplano × acomodação × copart:")
for k, v in sorted(cnt.items()):
    print("   %-34s %-12s %-9s %d" % (k[0][:34], k[1], k[2], v))
