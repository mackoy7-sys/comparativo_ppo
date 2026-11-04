#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retira a COPARTICIPACAO PARCIAL dos produtos PPO de 1 VIDA (90 entradas).

PEDIDO (04/11/2026): "ele esta deixando cotar 1v PPO com coparticipacao
parcial. Nao temos mais essa opcao, so coparticipacao completa."

CONFERIDO NA FONTE, nas 9 pracas que vendem PPO. A pagina de 1 vida
("20261021 a 20261231 - Super Simples 1 Vida v2.pdf") tem tres blocos de PPO, e
os TRES dizem COM COPARTICIPACAO TOTAL:

    bloco                      reembolso   coparticipacao   cods. (SP)
    Linha Metais               parcial     TOTAL            48190/47865/47833/47943
    Linha Tradicional          parcial     TOTAL            45318/45320/40685/40687/40696
    Linha Tradicional          total       TOTAL            45314/45316/40615/40617/40622

Ou seja: em 1 vida o eixo que varia e o REEMBOLSO (parcial/total), nao a
coparticipacao. E e exatamente assim que o catalogo ja guarda -- `precos` e o
reembolso total (236,61 no Adv 600 Enf de SP) e `pr2` e o parcial (227,14), os
dois batendo com os codigos internos acima.

As 90 entradas marcadas "Parcial" nao saem de tabela nenhuma: o preco delas e a
Completa multiplicada por 4/3 (236,61 x 1,3333 = 315,47), convencao de uma
carga antiga. Nao ha coluna na fonte que produza esses valores.

ESCOPO, conferido para nao tirar demais: em 2 a 29 e em 30 a 99 os PDFs do PPO
TEM bloco "COM COPARTICIPACAO PARCIAL" de verdade, com codigos proprios. So o
porte de 1 vida nao tem. Esta carga mexe unicamente em vmin=vmax=1.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
ESPERADO = 90
# prefixos dos produtos NotreDame (PPO) — os mesmos do isPPO() do index.html
PPO = ("Adv ", "Advance", "Premium", "Infinity", "Prata", "Ouro", "Diamante")


def alvo(e):
    return (e.get("operadora") == "Hapvida"
            and str(e.get("label", "")).startswith(PPO)
            and e.get("vmin") == 1 and e.get("vmax") == 1
            and e.get("coparticipacao") == "Parcial")


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    fora = [e for e in cat if alvo(e)]
    fica = [e for e in cat if not alvo(e)]

    print("catálogo: %d entradas  ·  a remover: %d  ·  ficam: %d"
          % (len(cat), len(fora), len(fica)))
    print("\npor produto:")
    for (l, a), q in sorted(collections.Counter((e["label"], e["acomodacao"])
                                                for e in fora).items()):
        print("   %-26s %-12s %d praças" % (l, a, q))
    print("\npraças: " + ", ".join(sorted({e["praca"].split(" - ")[0] for e in fora})))

    erros = []
    print("\ntravas:")

    print("  1. são exatamente as %d entradas esperadas" % ESPERADO)
    if len(fora) != ESPERADO:
        erros.append("esperava %d, achei %d" % (ESPERADO, len(fora)))

    print("  2. todas PPO, 1 vida, coparticipação Parcial")
    if any(e.get("vmin") != 1 or e.get("vmax") != 1
           or e.get("coparticipacao") != "Parcial"
           or not str(e.get("label", "")).startswith(PPO) for e in fora):
        erros.append("há entrada fora do escopo")

    print("  3. cada uma deixa a versão Completa no lugar")
    def comb(e):
        return (e.get("praca"), e.get("label"), e.get("acomodacao"), e.get("vmin"),
                e.get("vmax"), bool(e.get("mei")), e.get("contratacao"),
                e.get("tipo"), e.get("categoria"))
    completas = {comb(e) for e in fica if e.get("coparticipacao") == "Completa"}
    orfas = [e for e in fora if comb(e) not in completas]
    if orfas:
        erros.append("%d combinações ficariam sem nenhuma coparticipação" % len(orfas))
        for e in orfas[:5]: print("     órfã: %s" % (comb(e),))

    print("  4. a coparticipação Parcial de 2 a 29 e 30 a 99 não é tocada")
    outras = [e for e in fica if str(e.get("label", "")).startswith(PPO)
              and e.get("operadora") == "Hapvida" and e.get("coparticipacao") == "Parcial"]
    por_porte = collections.Counter((e.get("vmin"), e.get("vmax")) for e in outras)
    print("     seguem no ar: " + " · ".join("%s=%d" % (k, v) for k, v in sorted(
        por_porte.items(), key=lambda x: str(x[0]))))
    if (1, 1) in por_porte:
        erros.append("sobrou Parcial de 1 vida")
    if por_porte.get((2, 29), 0) != 486 or por_porte.get((30, 99), 0) != 270:
        erros.append("os outros portes mudaram de contagem: %s" % dict(por_porte))

    print("  5. nenhuma entrada que fica é alterada, e os ids seguem únicos")
    ids = [e.get("id") for e in fica]
    if None in ids or len(set(ids)) != len(ids):
        erros.append("as entradas que ficam têm id repetido ou ausente")

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-ppo1v-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    json.dump(fica, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas removidas, catálogo agora com %d" % (len(fora), len(fica)))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
