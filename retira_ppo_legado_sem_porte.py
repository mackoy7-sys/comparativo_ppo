#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retira as 26 entradas PPO Empresariais SEM PORTE de SP / RMSP.

Par do retira_ppo_1v_parcial.py: aquele tirou as 90 entradas "1 vida ·
coparticipacao parcial" que nao saem de tabela nenhuma; este tira o que fazia a
cotacao de 1 vida CONTINUAR achando um preco parcial depois disso.

O QUE SAO: as linhas mais antigas do catalogo (ids a partir de 33), de quando
ele ainda nao tinha o campo de porte. Com vmin/vmax nulos, o vidasOk() as
aceita para QUALQUER numero de vidas, e o resolved(), ao nao encontrar nenhuma
linha com porte que sirva, cai nelas. Resultado: 1 vida + coparticipacao
parcial resolvia para R$ 440,77 (Adv 600 Enf) -- um preco que a tabela de 1
vida nao tem, porque la so existe COM COPARTICIPACAO TOTAL.

So existem em SP / RMSP, em 5 produtos (Adv 600, Adv 700, Premium 900,
Premium 900 Care, Infinity), 13 Completa e 13 Parcial, 12 MEI e 14 nao-MEI.

MEDIDO ANTES DE REMOVER, com as funcoes do proprio cotador (resolved/vidasOk/
meiOk, e nao uma reimplementacao delas -- a primeira tentativa reimplementou a
regra do MEI errado e acusou 45 quebras falsas): varrendo 200 combinacoes de
produto x acomodacao x coparticipacao x MEI x porte (1, 2, 15, 30 e 99 vidas),
sair com as 26 muda 10 e deixa 190 identicas, sem nenhuma mudanca de preco. As
10 sao exatamente:

    1 vida · Parcial · Adv 600 Enf/Apto, Adv 700 Enf/Apto, Premium 900 Care Apto
    (cada uma em MEI e nao-MEI)

Ou seja: o unico efeito e parar de cotar o que a tabela nao vende. Em 2 a 29 e
em 30 a 99 nada muda, inclusive no MEI -- ali as linhas com porte ja respondem.

NAO MEXE nas entradas sem porte de ADESAO (72), que nao tem porte por natureza
do segmento.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
ESPERADO = 26
PPO = ("Adv ", "Advance", "Premium", "Infinity", "Prata", "Ouro", "Diamante")


def alvo(e):
    return (e.get("operadora") == "Hapvida"
            and str(e.get("label", "")).startswith(PPO)
            and e.get("tipo") == "Empresarial"
            and e.get("vmin") is None and e.get("vmax") is None)


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    fora = [e for e in cat if alvo(e)]
    fica = [e for e in cat if not alvo(e)]

    print("catálogo: %d entradas  ·  a remover: %d  ·  ficam: %d"
          % (len(cat), len(fora), len(fica)))
    print("\nas %d legadas:" % len(fora))
    print("   praças:  " + ", ".join(sorted({e["praca"] for e in fora})))
    print("   produtos: " + ", ".join(sorted({e["label"] for e in fora})))
    print("   ids de %d a %d" % (min(e["id"] for e in fora), max(e["id"] for e in fora)))
    print("   " + " · ".join("%s=%d" % (k, v) for k, v in
                             sorted(collections.Counter(e["coparticipacao"] for e in fora).items())))

    erros = []
    print("\ntravas:")

    print("  1. são exatamente as %d entradas esperadas" % ESPERADO)
    if len(fora) != ESPERADO:
        erros.append("esperava %d, achei %d" % (ESPERADO, len(fora)))

    print("  2. todas PPO · Empresarial · sem porte, e só de SP / RMSP")
    if any(e.get("vmin") is not None or e.get("vmax") is not None
           or e.get("tipo") != "Empresarial"
           or e.get("praca") != "SP / RMSP" for e in fora):
        erros.append("há entrada fora do escopo")

    print("  3. a Adesão sem porte não é tocada")
    ad = [e for e in fica if e.get("operadora") == "Hapvida"
          and str(e.get("label", "")).startswith(PPO) and e.get("tipo") == "Adesão"
          and e.get("vmin") is None]
    print("     seguem no ar: %d entradas de Adesão sem porte" % len(ad))
    if len(ad) != 72:
        erros.append("a Adesão sem porte mudou de contagem: %d" % len(ad))

    print("  4. todo produto que sai continua cotável pelas linhas COM porte")
    def comb(e):
        return (e["praca"], e["label"], e["acomodacao"], e["coparticipacao"])
    comporte = {comb(e) for e in fica if e.get("operadora") == "Hapvida"
                and str(e.get("label", "")).startswith(PPO)
                and e.get("tipo") == "Empresarial" and e.get("vmin") is not None}
    orfas = [e for e in fora if comb(e) not in comporte]
    if orfas:
        erros.append("%d combinações ficariam sem nenhuma linha com porte" % len(orfas))
        for e in orfas[:5]: print("     órfã: %s" % (comb(e),))

    print("  5. em 1 vida sobra só a coparticipação Completa no PPO")
    um = [e for e in fica if e.get("operadora") == "Hapvida"
          and str(e.get("label", "")).startswith(PPO) and e.get("tipo") == "Empresarial"
          and e.get("vmin") == 1]
    cops = {e["coparticipacao"] for e in um}
    print("     %d entradas de 1 vida, coparticipação %s" % (len(um), sorted(cops)))
    if cops != {"Completa"}:
        erros.append("1 vida ficou com coparticipação %s" % sorted(cops))

    print("  6. ids seguem únicos")
    ids = [e.get("id") for e in fica]
    if None in ids or len(set(ids)) != len(ids):
        erros.append("id repetido ou ausente")

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-ppoleg-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    json.dump(fica, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas removidas, catálogo agora com %d" % (len(fora), len(fica)))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
