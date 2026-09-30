#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CORRIGE a coparticipação das 4 praças do RS (CCG) no copart.json.

Reportado em 30/09/2026: São Leopoldo cobrava coparticipação em consultas e
exames no nível PARCIAL. A tabela de origem diz o contrário — na caixa
"COPARTICIPAÇÃO PARCIAL" as linhas de Consultas Eletivas, Consultas de
Urgência, Exames Simples e Exames Complexos são TODAS traço; só Terapias tem
valor. Conferido nas 4 praças, nos dois PDFs (PME e Super Simples).

Por que o parser errou: no resto do país as duas faixas (parcial | total) são
colunas VIZINHAS de um mesmo quadro, e é assim que o parse_box() lê. No RS são
dois quadros EMPILHADOS, cada um com as mesmas 3 colunas de produto. O parser
leu o de baixo (total) e carimbou o mesmo conteúdo nas duas faixas.

De quebra, a leitura errada também trocou o produto: as três colunas do quadro
do RS são

    col 1  NOSSO PLANO            · AMBULATORIAL
    col 2  NOSSO PLANO / NOSSO MED · AMB+HOSP+OBST
    col 3  POP EST / VALE DOS SINOS · AMB+HOSP+OBST

e o parser colou a col 2 em todos os produtos. Com isso o Pop exibia a consulta
do Nosso Plano (30% limitado a R$ 20,00) no lugar da sua (R$ 43,63 fixos).

A chave "<plano> · Ambulatorial" é nova e existe SÓ no RS: é a única região cujo
quadro tem coluna ambulatorial própria (103 páginas varridas nos PDFs de origem;
em todas as outras "AMBULATORIAL" aparece apenas dentro de "AMBULATORIAL +
HOSPITALAR + OBSTETRÍCIA", que é a segmentação inteira, não uma coluna).

Ensaio por padrão; grava só com --gravar (backup com carimbo de hora).
"""
import json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
COP = os.path.join(AQUI, "copart.json")
FONTE = "PME RS (conferido 30/09/2026)"

PROCS = ["Consultas eletivas", "Consultas de urgência", "Exames simples",
         "Exames complexos", "Terapias especiais", "Demais terapias", "Internações"]

# As 3 colunas do quadro, lidas por posição nas 4 páginas do PME RS e nas 4 do
# Super Simples RS — os 8 quadros trazem exatamente estes valores.
COL_AMB = {  # NOSSO PLANO · AMBULATORIAL
    "parcial": [None, None, None, None, "Valor fixo R$ 78,87", "Valor fixo R$ 42,47", None],
    "total":   ["Valor fixo R$ 40,39", "Valor fixo R$ 57,24",
                "40,00% Limitado a R$ 47,70", "40,00% Limitado a R$ 250,00",
                "Valor fixo R$ 73,03", "Valor fixo R$ 39,33", None],
}
COL_HOSP = {  # NOSSO PLANO / NOSSO MED · AMB+HOSP+OBST
    "parcial": [None, None, None, None, "Valor fixo R$ 79,00", "Valor fixo R$ 42,00", None],
    "total":   ["30,00% Limitado a R$ 20,00", "30,00% Limitado a R$ 55,00",
                "30,00% Limitado a R$ 15,00", "30,00% Limitado a R$ 55,00",
                "Valor fixo R$ 79,00", "Valor fixo R$ 42,00", None],
}
COL_POP = {  # POP EST / VALE DOS SINOS · AMB+HOSP+OBST
    "parcial": [None, None, None, None, "Valor fixo R$ 78,87", "Valor fixo R$ 42,47", None],
    "total":   ["Valor fixo R$ 43,63", "Valor fixo R$ 61,82",
                "40,00% Limitado a R$ 51,52", "40,00% Limitado a R$ 125,93",
                "Valor fixo R$ 78,87", "Valor fixo R$ 42,47", None],
}

# --- INDIVIDUAL (PF) -------------------------------------------------------
# O Individual tem quadro PRÓPRIO ("COPARTICIPAÇÃO POR PROCEDIMENTO"), com
# valores diferentes dos do PME. Como a chave do Cotador é o `plano` (o "(PF)"
# vive no `label`), o PF vinha pegando a tabela do PME. Conferido na imagem das
# 4 páginas do PDF Individual do RS.
COL_PF = {  # Canoas, Novo Hamburgo, São Leopoldo — vale p/ Nosso Plano e Pop
    "parcial": [None, None, None, None, "Valor fixo R$ 78,87", "Valor fixo R$ 42,47", None],
    "total":   ["Valor fixo R$ 43,63", "Valor fixo R$ 61,82",
                "40,00% Limitado a R$ 51,52", "40,00% Limitado a R$ 125,93",
                "Valor fixo R$ 78,87", "Valor fixo R$ 42,47", None],
}
# Porto Alegre, coluna "DEMAIS PLANOS": igual à de cima, MAS o parcial cobra
# 40% em exames e a célula do teto vem em branco — é 40% sem limite mesmo.
COL_PF_POA = {
    "parcial": [None, None, "40,00%", "40,00%", "Valor fixo R$ 78,87", "Valor fixo R$ 42,47", None],
    "total":   COL_PF["total"],
}
# Porto Alegre, coluna "NOSSO MÉDICO": tabela inteiramente própria.
COL_PF_NM = {
    "parcial": [None, None, None, None, "Valor fixo R$ 78,87", "40,00% Limitado a R$ 60,00", None],
    "total":   ["40,00% Limitado a R$ 40,00", "40,00% Limitado a R$ 80,00",
                "40,00% Limitado a R$ 29,00", "40,00% Limitado a R$ 120,00",
                "Valor fixo R$ 78,87", "40,00% Limitado a R$ 60,00", None],
}

PRACAS = ["Canoas - RS", "Novo Hamburgo - RS", "Porto Alegre - RS", "São Leopoldo - RS"]

# produto -> coluna. "Nosso Médico" só existe em Porto Alegre; o cabeçalho da
# col 1 nomeia apenas NOSSO PLANO, então Nosso Médico não ganha ambulatorial.
# O sufixo " · PF" é lido pelo Cotador quando a cotação é Individual; " · Ambulatorial",
# quando a acomodação é ambulatorial. Sem sufixo = Empresarial hospitalar.
BASE = {
    "Nosso Plano":                 COL_HOSP,
    "Nosso Plano · Ambulatorial":  COL_AMB,
    "Nosso Médico":                COL_HOSP,
    "Pop Estadual":                COL_POP,
    "Pop Vale dos Sinos":          COL_POP,
    "Nosso Plano · PF":            COL_PF,
    "Pop · PF":                    COL_PF,
}
DESTINO = {pr: dict(BASE) for pr in PRACAS}
DESTINO["Porto Alegre - RS"].update({
    "Nosso Plano · PF":  COL_PF_POA,
    "Pop · PF":          COL_PF_POA,
    "Nosso Médico · PF": COL_PF_NM,
})


def bloco(col):
    return {"parcial": dict(zip(PROCS, col["parcial"])),
            "total":   dict(zip(PROCS, col["total"])),
            "fonte":   FONTE}


def main():
    cop = json.load(open(COP))
    antes = json.dumps(cop, ensure_ascii=False, sort_keys=True)
    CONS = PROCS[:4]

    print("estado atual:")
    for pr in PRACAS:
        for pl, v in sorted(cop.get(pr, {}).items()):
            par = v.get("parcial") or {}
            cobra = [c for c in CONS if par.get(c)]
            print("  %-20s %-20s parcial cobra em: %s"
                  % (pr, pl, ", ".join(cobra) if cobra else "— (correto)"))

    # quem a praça realmente vende — a chave só entra se houver produto para ela
    cat = json.load(open(os.path.join(AQUI, "catalog.json")))
    vende = set()
    for e in cat:
        if e.get("operadora") == "Hapvida" and e.get("praca"):
            vende.add((e["praca"], e["plano"], e.get("tipo") or "Empresarial"))

    mudou, criou, pulou = [], [], []
    for pr in PRACAS:
        if pr not in cop:
            print("!! praça ausente no copart.json: %s" % pr); return 1
        for pl, col in sorted(DESTINO[pr].items()):
            base = pl.split(" · ")[0]
            tipo = "Individual" if pl.endswith(" · PF") else "Empresarial"
            if (pr, base, tipo) not in vende:
                pulou.append((pr, pl)); continue   # Nosso Médico só existe em POA
            novo = bloco(col)
            if pl in cop[pr]:
                if cop[pr][pl] != novo:
                    mudou.append((pr, pl))
            else:
                criou.append((pr, pl))
            cop[pr][pl] = novo

    print("\ntravas:")

    print("  1. nenhuma praça fora do RS é tocada")
    for pr in cop:
        if pr in PRACAS: continue
        if json.dumps(cop[pr], ensure_ascii=False, sort_keys=True) != \
           json.dumps(json.loads(antes)[pr], ensure_ascii=False, sort_keys=True):
            print("!! %s mudou e não deveria" % pr); return 1

    # Única exceção do país, e está impressa: no Individual de Porto Alegre a
    # coluna "DEMAIS PLANOS · COPARTICIPAÇÃO PARCIAL" cobra 40% em exames, com a
    # célula do teto em branco. Qualquer outra cobrança no parcial é defeito.
    EXCECAO = {("Porto Alegre - RS", "Nosso Plano · PF"),
               ("Porto Alegre - RS", "Pop · PF")}
    print("  2. o nível PARCIAL não cobra consulta nem exame (fora a exceção de POA)")
    for pr, planos in cop.items():
        for pl, v in planos.items():
            par = v.get("parcial") or {}
            sujo = [c for c in CONS if par.get(c)]
            if not sujo: continue
            if (pr, pl) in EXCECAO and sujo == ["Exames simples", "Exames complexos"]:
                continue
            print("!! %s · %s cobra no parcial: %s" % (pr, pl, sujo)); return 1

    print("  3. o nível TOTAL cobra consulta ou exame em todo produto do RS")
    for pr in PRACAS:
        for pl, v in cop[pr].items():
            tot = v.get("total") or {}
            if not any(tot.get(c) for c in CONS):
                print("!! %s · %s ficou sem cobrança no total" % (pr, pl)); return 1

    print("  4. Pop deixa de repetir o Nosso Plano")
    for pr in PRACAS:
        np = (cop[pr]["Nosso Plano"]["total"] or {}).get("Consultas eletivas")
        for pl in ("Pop Estadual", "Pop Vale dos Sinos"):
            if pl in cop[pr] and (cop[pr][pl]["total"] or {}).get("Consultas eletivas") == np:
                print("!! %s · %s ainda repete o Nosso Plano" % (pr, pl)); return 1

    print("  5. os sufixos ' · Ambulatorial' e ' · PF' só existem no RS")
    for pr, planos in cop.items():
        for pl in planos:
            if (" · Ambulatorial" in pl or " · PF" in pl) and pr not in PRACAS:
                print("!! sufixo fora do RS: %s · %s" % (pr, pl)); return 1

    print("  6. o Individual não repete a tabela do PME")
    for pr in PRACAS:
        for pl in ("Nosso Plano", "Nosso Médico"):
            k = pl + " · PF"
            if k in cop[pr] and cop[pr][k]["total"] == cop[pr][pl]["total"]:
                print("!! %s · %s ainda repete o PME" % (pr, k)); return 1

    print("\nresumo: %d blocos corrigidos, %d criados, %d pulados (praça não vende)"
          % (len(mudou), len(criou), len(pulou)))
    for pr, pl in mudou: print("   corrigido  %-20s %s" % (pr, pl))
    for pr, pl in criou: print("   criado     %-20s %s" % (pr, pl))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = COP + ".bak-rs-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(COP, bak)
    json.dump(cop, open(COP, "w"), ensure_ascii=False)
    print("\ngravado. backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
