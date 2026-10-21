#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APLICA a tabela PME Compulsório 30-99 (HMO) da vigência 01/10 a 31/12/2026.

Origem: "20261001 a 20261231 - PME - Compulsório v2 [HMO].pdf", lido pelo
build_comp_out.py. Reportado pelo time em 06/10: Smart Prime com valor errado —
e estavam certos: o Cotador seguia na tabela de 08/09 a 30/09.

O que muda (24 entradas, todas para BAIXO):
    Rio de Janeiro ....... Smart Prime e Smart 500, as 4 combinações, -11% a -14%
    Sorocaba ............. Smart Prime e Smart 500, as 4 combinações, -6%
    Americana, Campinas .. Smart Prime e Smart 500, só Parcial, -6,2%

O que é CRIADO (2 entradas): SP / RMSP · Smart Prime · Compulsório · Completa,
em enfermaria e apartamento. Não é produto novo — a tabela ANTERIOR já trazia
esses mesmos valores (148,58 e 157,33) e o parser da carga de setembro perdeu o
par de colunas: naquela página o bloco "COM COPARTICIPAÇÃO TOTAL" fica ao lado
da caixa "DESCONTO PROMOCIONAL" e a linha ACOMODAÇÃO não é emitida. Resultado: o
vendedor de SP só conseguia cotar Smart Prime Compulsório na coparticipação
parcial. A criação repete a entrada Parcial da mesma praça, trocando só
coparticipação e preços.

⚠️ NÃO entra aqui, e segue na vigência anterior:
  - a tabela de ADESÃO 30-99 (não veio nesta remessa);
  - os produtos PPO (Adv 600/700, Premium 900, Infinity e o Smart Flex de
    Americana/Campinas/Jundiaí/Sorocaba), que vêm no arquivo sem o sufixo [HMO].
    Conferido: a cobertura de produtos do arquivo [HMO] é idêntica à de 08/09,
    então nenhum produto saiu de linha.

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import collections, copy, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
NOVO = "/tmp/comp_out_parsed.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
LIMITE = 0.40

# conferidas a mão no texto cru do PDF, ancoradas no CÓD. INTERNO
AMOSTRAS = [
    ("Rio de Janeiro - RJ", "Smart Prime", "Enfermaria",  "Parcial",  168.46),   # cód. 41455
    ("Rio de Janeiro - RJ", "Smart Prime", "Apartamento", "Parcial",  187.00),   # cód. 41459
    ("Rio de Janeiro - RJ", "Smart Prime", "Enfermaria",  "Completa", 126.34),   # cód. 41463
    ("Rio de Janeiro - RJ", "Smart Prime", "Apartamento", "Completa", 140.25),   # cód. 41467
    ("Sorocaba - SP",       "Smart Prime", "Enfermaria",  "Parcial",  189.65),
    ("Sorocaba - SP",       "Smart Prime", "Apartamento", "Completa", 157.89),
    ("SP / RMSP",           "Smart Prime", "Enfermaria",  "Parcial",  198.11),   # inalterada
    ("SP / RMSP",           "Smart Prime", "Enfermaria",  "Completa", 148.58),   # criada
    ("SP / RMSP",           "Smart Prime", "Apartamento", "Completa", 157.33),   # criada
]
CRIAR = {("SP / RMSP", "Smart Prime", "Enfermaria", "Completa"),
         ("SP / RMSP", "Smart Prime", "Apartamento", "Completa")}


def main():
    cat = json.load(open(CAT))
    bruto = json.load(open(NOVO))
    novos = {}
    for praca, ents in bruto.items():
        for n in ents:
            novos[(praca, n["label"], n["acomodacao"], n["coparticipacao"])] = n
    pracas = set(bruto)

    idx = {}
    for e in cat:
        if e.get("vmin") == 30 and e.get("contratacao") == "Compulsório":
            idx[(e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"])] = e

    muda, iguais, criar = [], 0, []
    for k, n in novos.items():
        e = idx.get(k)
        if e is None:
            criar.append((k, n)); continue
        if all(abs(n["precos"][b] - e["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((e, n))

    erros = []
    print("tabela nova: %d entradas em %d praças\n" % (len(novos), len(pracas)))
    print("travas:")

    print("  1. só 30-99 Compulsório das praças do arquivo entra na conta")
    if any(e.get("vmin") != 30 or e.get("contratacao") != "Compulsório"
           or e.get("praca") not in pracas for e, _ in muda):
        erros.append("entrada fora do escopo seria alterada")

    print("  2. Individual, Adesão, 1 vida e 2-29 ficam intocados")
    ids = {id(e) for e, _ in muda}
    if any(id(e) in ids for e in cat
           if e.get("vmin") != 30 or e.get("contratacao") != "Compulsório"):
        erros.append("entrada fora do 30-99 Compulsório seria alterada")

    print("  3. toda variação cabe em ±%d%%" % (LIMITE * 100))
    fora = [(e, n, b) for e, n in muda for b in BANDS
            if e["precos"][b] and abs((n["precos"][b] - e["precos"][b]) / e["precos"][b]) > LIMITE]
    if fora:
        erros.append("%d valores variam mais de %d%%" % (len(fora), LIMITE * 100))

    print("  4. curva de faixa etária não decresce (regra ANS)")
    for _, n in muda + [(None, x) for _, x in criar]:
        if any(n["precos"][BANDS[i + 1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9)):
            erros.append("curva decrescente em %s %s" % (n.get("praca"), n["label"]))

    print("  5. Parcial nunca fica abaixo da Completa do mesmo plano")
    por = {}
    for k, n in novos.items():
        por.setdefault(k[:3], {})[k[3]] = n["precos"]
    for k, v in por.items():
        if "Parcial" in v and "Completa" in v:
            if any(v["Parcial"][b] < v["Completa"][b] - 0.005 for b in BANDS):
                erros.append("Parcial < Completa em %s" % str(k))

    print("  6. %d amostras conferidas à mão contra o PDF" % len(AMOSTRAS))
    for praca, label, acom, cop, p0 in AMOSTRAS:
        n = novos.get((praca, label, acom, cop))
        if not n:
            erros.append("amostra ausente na leitura: %s %s %s %s" % (praca, label, acom, cop)); continue
        if abs(n["precos"]["00 a 18"] - p0) > 0.005:
            erros.append("amostra diverge: %s %s %s %s -> %.2f (esperado %.2f)"
                         % (praca, label, acom, cop, n["precos"]["00 a 18"], p0))

    print("  7. só o que a tabela manda criar é criado")
    if {k for k, _ in criar} != CRIAR:
        erros.append("criações inesperadas: %s" % sorted({k for k, _ in criar} - CRIAR))
    for k, _ in criar:
        base = idx.get((k[0], k[1], k[2], "Parcial"))
        if base is None:
            erros.append("sem entrada Parcial para espelhar em %s" % str(k))

    print("  8. o campo pr2 (reembolso parcial NotreDame) não é tocado")
    if any("pr2" in e for e, _ in muda):
        erros.append("uma entrada com pr2 seria alterada")

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    print("\nresumo: %d mudam, %d já iguais, %d criadas" % (len(muda), iguais, len(criar)))
    if muda:
        d = [(n["precos"][b] - e["precos"][b]) / e["precos"][b] for e, n in muda for b in BANDS]
        print("        variação média %+.2f%% (de %+.2f%% a %+.2f%%)"
              % (sum(d) / len(d) * 100, min(d) * 100, max(d) * 100))
        for p, q in collections.Counter(e["praca"] for e, _ in muda).most_common():
            print("        %-26s %d" % (p, q))
    for k, _ in sorted(criar, key=str):
        print("        CRIADA  %-26s %-14s %-12s %s" % k)

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-comp-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    for e, n in muda:
        e["precos"] = {b: n["precos"][b] for b in BANDS}
    # a copia nao pode herdar o id da base (dois planos com o mesmo id), mas
    # tambem nao pode ficar SEM id: o selectedPlans() deduplica por id, e as
    # entradas sem id colidem entre si e somem da cotacao. Numera na sequencia.
    pid = max(e["id"] for e in cat)
    for k, n in criar:
        base = idx[(k[0], k[1], k[2], "Parcial")]
        nova = copy.deepcopy(base)
        nova["coparticipacao"] = k[3]
        nova["precos"] = {b: n["precos"][b] for b in BANDS}
        pid += 1
        nova["id"] = pid
        cat.append(nova)
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d atualizadas, %d criadas\nbackup: %s" % (len(muda), len(criar), bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
