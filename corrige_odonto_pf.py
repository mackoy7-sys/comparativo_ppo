#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMPLETA o odonto.json: família HOSPITALAR do Individual em 4 praças (07/10/2026).

Reportado: cotação de Timon-PI (cota por Teresina), 2 vidas, Nosso Plano + Odonto,
enfermaria, coparticipação parcial — Cotador R$ 475,90, Conecta R$ 483,60.

O Cotador NÃO errava o preço médico: 196,54 + 279,36 = 475,90 é exatamente o que
a tabela traz na coluna Médica¹ (a com desconto por contratar o odonto junto). O
que faltava era SOMAR o plano odontológico, porque `odonto.json` só tinha a
família "Ambulatorial" de Teresina — e a cotação é enfermaria, que cai em
"Hospitalar" (odontoFam() no index.html). Sem valor, `odontoVal()` devolve 0.
A diferença de R$ 7,70 é 2 vidas x R$ 3,85.

Varrendo o catálogo, o buraco existe em 4 praças (38 entradas "+ Odonto"):

    Teresina - PI    VALOR PROMO 3,85 · VALOR 19,25   (cód. 9982, reg. 471.474/14-1)
    Salvador - BA    VALOR PROMO 3,85 · VALOR 19,25   (cód. 9982, reg. 471.474/14-1)
    Joinville - SC   VALOR PROMO 3,85 · VALOR 19,25   (cód. 9982, reg. 471.474/14-1)
    Anápolis - GO    VALOR PROMO 24,50 · VALOR 75,84  (cód. 2737, reg. 487.836/21-1)

⚠️ Anápolis é outro produto odontológico — 6x o valor das outras. Conferido na
IMAGEM da página de cada praça (o texto achatado mistura as colunas), no bloco
PLANOS ODONTOLÓGICOS que fica ao lado da tabela NOSSO PLANO (enfermaria/
apartamento), não ao lado da ambulatorial.

Fonte: "20260701 a 20260930 - Individual.pdf" (OneDrive_1_12-08-2026), páginas
15 (Teresina), 29 (Salvador), 31 (Anápolis) e 37 (Joinville).

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
ODO = os.path.join(AQUI, "odonto.json")
CAT = os.path.join(AQUI, "catalog.json")

NOVO = {
    "Teresina - PI":  {"cheio": 19.25, "promo": 3.85},
    "Salvador - BA":  {"cheio": 19.25, "promo": 3.85},
    "Joinville - SC": {"cheio": 19.25, "promo": 3.85},
    "Anápolis - GO":  {"cheio": 75.84, "promo": 24.50},
}
FAM, TIPO = "Hospitalar", "Individual"

# a cotação que originou o chamado
CASO = ("Teresina - PI", "Nosso Plano + Odonto (PF)", "Enfermaria", "Parcial",
        {"00 a 18": 1, "24 a 28": 1}, 483.60)


def main():
    od = json.load(open(ODO))
    cat = json.load(open(CAT))
    antes = json.dumps(od, ensure_ascii=False, sort_keys=True)

    print("estado atual:")
    for pr in NOVO:
        fams = sorted((od.get(pr, {}).get(TIPO) or {}))
        print("  %-18s Individual: %s" % (pr, fams or "—"))

    erros = []
    print("\ntravas:")

    print("  1. a praça já existe no odonto.json e tem a família Ambulatorial")
    for pr in NOVO:
        if FAM in (od.get(pr, {}).get(TIPO) or {}):
            erros.append("%s já tem %s — não sobrescrever" % (pr, FAM))
        if "Ambulatorial" not in (od.get(pr, {}).get(TIPO) or {}):
            erros.append("%s não tem Ambulatorial — página inesperada" % pr)

    print("  2. a praça vende '+ Odonto' em enfermaria ou apartamento no Individual")
    for pr in NOVO:
        n = [e for e in cat if e.get("praca") == pr and e.get("tipo") == TIPO
             and "+ Odonto" in e["label"] and e["acomodacao"] != "Ambulatorial"]
        if not n:
            erros.append("%s não vende '+ Odonto' hospitalar no Individual" % pr)
        else:
            print("     %-18s %d entradas" % (pr, len(n)))

    print("  3. o promo nunca é maior que o cheio")
    for pr, v in NOVO.items():
        if v["promo"] > v["cheio"]:
            erros.append("%s: promo %.2f > cheio %.2f" % (pr, v["promo"], v["cheio"]))

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    for pr, v in NOVO.items():
        od.setdefault(pr, {}).setdefault(TIPO, {})[FAM] = dict(v)

    print("  4. nenhuma praça fora das 4 é tocada")
    a, b = json.loads(antes), od
    mud = [p for p in set(a) | set(b) if a.get(p) != b.get(p)]
    if sorted(mud) != sorted(NOVO):
        print("!! praças alteradas: %s" % sorted(mud)); return 1

    # a cotação do chamado tem de fechar com o Conecta
    praca, label, acom, cop, vidas, esperado = CASO
    e = next((x for x in cat if x.get("praca") == praca and x["label"] == label
              and x["acomodacao"] == acom and x["coparticipacao"] == cop
              and x.get("tipo") == TIPO), None)
    if not e:
        print("!! não achei a entrada do chamado"); return 1
    med = sum(q * e["precos"][f] for f, q in vidas.items())
    odo = sum(vidas.values()) * od[praca][TIPO][FAM]["promo"]
    print("  5. a cotação do chamado fecha: médico %.2f + odonto %.2f = %.2f" % (med, odo, med + odo))
    if abs(med + odo - esperado) > 0.005:
        print("!! esperado %.2f, obtido %.2f" % (esperado, med + odo)); return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = ODO + ".bak-pf-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(ODO, bak)
    json.dump(od, open(ODO, "w"), ensure_ascii=False, indent=1)
    print("\ngravado: %d praças ganharam a família %s\nbackup: %s" % (len(NOVO), FAM, bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
