#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corrige 10 entradas do catalogo que guardam o preco do quadro ERRADO.

Achado em 23/09. Em Mogi das Cruzes e Sao Bernardo do Campo, PME Adesao,
coparticipacao Completa, o catalogo guarda o preco do quadro de REEMBOLSO
PARCIAL (5 colunas) como se fosse o preco unico do produto. Esta de 4%
(Adv 600) a 22% (Premium 900 Care) abaixo do correto. As outras 70 das 72
combinacoes praca x fonte x coparticipacao conferem com o quadro de reembolso
total, entao o erro e pontual — provavelmente o cabecalho dessas duas paginas
enganou o filtro por texto da carga anterior, que e exatamente o modo de falha
que levou este projeto a abandonar heuristica de cabecalho.

O valor certo nao e calculado: e lido do quadro de 7 colunas da MESMA pagina
do mesmo PDF. E so grava sob quatro travas, por entrada:
  1. o valor atual tem de bater, nas 10 faixas, com o quadro de 5 colunas
     (confirma o diagnostico — se nao bater, a entrada nao e o caso);
  2. o valor novo tem de vir do quadro de 7 colunas, alinhado por codigo ANS;
  3. o novo tem de ser MAIOR que o atual em todas as faixas;
  4. a curva de faixa etaria do valor novo tem de ser nao-decrescente.
Qualquer entrada que falhe em uma delas fica como esta e e reportada.

Uso:  python3 corrige_mogi_sbc.py            (so relata, nao grava)
      python3 corrige_mogi_sbc.py --gravar   (grava, com backup)
"""
import json, shutil, sys, datetime
import pdfplumber
from build_todos import city_of, parse_price_tables, ANS_EMP, D, PRACA_MAP

H = "/Users/marcoscorrea/comparativo-ppo/"
PDF = "20260908 a 20260930 - PME - Adesão v2.pdf"
ALVO = {"Mogi das Cruzes - SP", "São Bernardo do Campo - SP"}
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
A600 = "474.439/15-0"


def le_quadros():
    """praca -> {ncolunas: {(label, acomodacao): {faixa: preco}}}, coparticipacao Completa."""
    out = {}
    with pdfplumber.open(D + PDF) as pdf:
        for pg in pdf.pages:
            c = city_of(pg)
            if not c:
                continue
            c = PRACA_MAP.get(c, c)
            if c not in ALVO:
                continue
            if "REAJUSTE POR MUDANÇA" in (pg.extract_text() or "")[:600]:
                continue
            for tb in parse_price_tables(pg, xlimit=780):
                codes = [x for x, _ in (tb.get("codes") or [])]
                if A600 not in codes:
                    continue
                if "COPARTICIPACAOTOTAL" not in (tb.get("cop") or ""):
                    continue                       # so coparticipacao Completa
                n = len(codes)
                # alinhamento posicional obrigatorio: a linha REGISTRO ANS, a
                # linha ACOMODACAO e cada linha de faixa tem de ter o mesmo
                # numero de colunas, senao a coluna lida pode nao ser a do produto
                if len(tb.get("acoms") or []) != n:
                    continue
                if any(len(v) != n for v in tb["prices"].values()):
                    continue
                if len(tb["prices"]) != 10:
                    continue
                quadro = {}
                for i, code in enumerate(codes):
                    info = ANS_EMP.get(code)
                    if not info:
                        continue
                    _, label, acom = info
                    if tb["acoms"][i] != acom:
                        acom = tb["acoms"][i]      # a coluna manda
                    quadro[(label, acom)] = {
                        f: sorted(tb["prices"][f], key=lambda v: v[1])[i][0]
                        for f in BANDS}
                out.setdefault(c, {})[n] = quadro
    return out


def main():
    gravar = "--gravar" in sys.argv
    q = le_quadros()
    for praca in ALVO:
        if praca not in q or 7 not in q[praca] or 5 not in q[praca]:
            print(f"!! {praca}: não achei os dois quadros na fonte — abortado")
            return 1

    cat = json.load(open(H + "catalog.json", encoding="utf-8"))
    mudar, recusadas = [], []
    for c in cat:
        if (c.get("praca") not in ALVO or c.get("operadora") != "Hapvida"
                or c.get("tipo") != "Empresarial" or c.get("vmin") != 30
                or c.get("vmax") != 99 or c.get("contratacao") != "Adesão"
                or c.get("coparticipacao") != "Completa"):
            continue
        k = (c.get("label"), c.get("acomodacao"))
        tot = q[c["praca"]][7].get(k)
        par = q[c["praca"]][5].get(k)
        if not tot:
            continue
        atual = c.get("precos") or {}
        if all(abs(atual.get(f, -1) - tot[f]) < 0.005 for f in BANDS):
            continue                                   # ja esta certo
        # trava 1: o atual tem de ser exatamente o quadro parcial
        if not (par and all(abs(atual.get(f, -1) - par[f]) < 0.005 for f in BANDS)):
            recusadas.append((c, "valor atual não é o do quadro parcial"))
            continue
        # trava 3: novo maior em todas
        if not all(tot[f] > atual[f] for f in BANDS):
            recusadas.append((c, "valor novo não é maior em todas as faixas"))
            continue
        # trava 4: curva nao-decrescente
        v = [tot[f] for f in BANDS]
        if any(v[i + 1] < v[i] - 0.005 for i in range(9)):
            recusadas.append((c, "curva de faixa etária do valor novo decresce"))
            continue
        mudar.append((c, tot))

    print(f'{"praça":28} {"produto":18} {"acom":12} {"00 a 18":>18} {"59 ou mais":>20}')
    for c, tot in mudar:
        a, b = c["precos"]["00 a 18"], tot["00 a 18"]
        a9, b9 = c["precos"]["59 ou mais"], tot["59 ou mais"]
        print(f'{c["praca"]:28} {c["label"]:18} {c["acomodacao"]:12} '
              f'{a:>8} → {b:<7} {a9:>10} → {b9:<9}  (+{(b/a-1)*100:.1f}%)')
    print(f"\nentradas a corrigir: {len(mudar)}   recusadas pelas travas: {len(recusadas)}")
    for c, por in recusadas:
        print(f'   !! {c["praca"]} {c["label"]} {c["acomodacao"]}: {por}')

    if not gravar:
        print("\n(ensaio — nada gravado. Rode com --gravar para aplicar.)")
        return 0
    if not mudar:
        print("\nnada a fazer.")
        return 0

    bkp = H + "catalog.json.bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(H + "catalog.json", bkp)
    for c, tot in mudar:
        c["precos"] = {f: tot[f] for f in BANDS}
    json.dump(cat, open(H + "catalog.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"\ngravado. backup em {bkp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
