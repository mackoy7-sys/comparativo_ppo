#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retira do catalogo o plano SEM FRANQUIA que so existe como duplicata do COM
FRANQUIA -- hoje, 4 entradas do Nosso Plano de Brasilia (2 a 29 vidas).

O QUE ESTAVA ERRADO: em Brasilia, o bloco do Nosso Plano no Super Simples tem
seis colunas e DUAS linhas de cabecalho que decidem o que cada uma e:

    CÓD. INTERNO   21298    21299    21300    11615    11022    11034
    ACOMODAÇÃO     S/ACOM   ENFERM   APART    S/ACOM   ENFERM   APART
    SEGMENTAÇÃO    AMB      AMB+HOSP+OBST     AMB      AMB+HOSP+OBST
    FRANQUIA*      SEM      COM FRANQUIA*     SEM      COM FRANQUIA*

Medido pela posicao x das palavras na propria pagina (nao pelo texto corrido,
que junta tudo numa linha so): o "SEM" cobre apenas a coluna do S/ACOM, e o
"COM FRANQUIA*" se estende sobre ENFERM e APART. Ou seja, em Brasilia a
enfermaria e o apartamento do Nosso Plano SO existem com franquia -- o que a
nota de rodape ja dizia, que a franquia e nas internacoes e vale para a
segmentacao "AMBULATORIAL + HOSPITALAR + OBSTETRICIA".

O catalogo tinha as duas versoes com o MESMO preco: "Nosso Plano" e "Nosso
Plano Franquia", enfermaria e apartamento, 163,26 e 244,93. O vendedor podia
cotar "sem franquia" por um valor que e o da franquia -- e o cliente so
descobria a franquia na internacao.

COMO AS 4 FORAM ACHADAS: varrendo o catalogo inteiro atras de pares
<X> / <X Franquia> na mesma praca, acomodacao, coparticipacao e porte. Sao 12
pares no total; 8 sao de Joinville e tem preco DIFERENTE (la a franquia e mais
barata mesmo: 303,25 contra 315,85), entao os dois existem e ficam. Os 4 de
preco identico sao estes.

O QUE NAO SAI:
  - "Nosso Plano Franquia" enfermaria/apartamento, que e a versao correta;
  - "Nosso Plano" AMBULATORIAL, que e genuinamente sem franquia (plano
    ambulatorial nao interna, entao franquia de internacao nao se aplica);
  - o PME de Brasilia (30 a 99), que e outro bloco, com outros registros
    (492.146/22-1, 491.902/22-5, 491.898/22-3) e SEM linha de franquia -- la o
    sem-franquia existe de verdade e nao ha duplicata.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
ESPERADO = 4


def contexto(e):
    return (e.get("praca"), e["acomodacao"], e["coparticipacao"],
            e.get("vmin"), e.get("vmax"), bool(e.get("mei")),
            e.get("contratacao"), e.get("tipo"))


def gemeo(label):
    """o rotulo COM franquia correspondente a este rotulo sem franquia"""
    if " + Odonto" in label:
        return label.replace(" + Odonto", " Franquia + Odonto")
    if "(PF)" in label:
        return label.replace(" (PF)", " Franquia (PF)")
    if "(Adesão)" in label:
        return label.replace(" (Adesão)", " Franquia (Adesão)")
    return label + " Franquia"


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    idx = {}
    for e in cat:
        if e.get("operadora") != "Hapvida":
            continue
        idx.setdefault(contexto(e), {})[e["label"]] = e

    fora, mantidos = [], []
    for ctx, m in idx.items():
        for lab, e in m.items():
            if " Franquia" in lab:
                continue
            f = m.get(gemeo(lab))
            if not f:
                continue
            if all(abs(e["precos"][b] - f["precos"][b]) < 0.005 for b in BANDS):
                fora.append((e, f))
            else:
                mantidos.append((e, f))

    print("pares <X> / <X Franquia> no catálogo: %d" % (len(fora) + len(mantidos)))
    print("   preço idêntico (duplicata, sai): %d" % len(fora))
    print("   preço diferente (os dois existem, ficam): %d" % len(mantidos))
    print()
    for e, f in fora:
        print("   SAI   %-16s %-12s %-9s %-9s %-22s  %.2f  (fica: %s)"
              % (e["praca"].split(" - ")[0], e["acomodacao"], e["coparticipacao"],
                 str((e.get("vmin"), e.get("vmax"))) if e.get("vmin") else "PF",
                 e["label"], e["precos"]["00 a 18"], f["label"]))
    print()
    for e, f in mantidos[:4]:
        print("   fica  %-16s %-12s %-9s %-22s  %.2f  vs  %.2f (%s)"
              % (e["praca"].split(" - ")[0], e["acomodacao"], e["coparticipacao"],
                 e["label"], e["precos"]["00 a 18"], f["precos"]["00 a 18"], f["label"]))
    if len(mantidos) > 4:
        print("   ... e mais %d" % (len(mantidos) - 4))

    erros = []
    print("\ntravas:")

    print("  1. são exatamente as %d entradas esperadas" % ESPERADO)
    if len(fora) != ESPERADO:
        erros.append("esperava %d, achei %d" % (ESPERADO, len(fora)))

    print("  2. todas em Brasília, porte 2 a 29")
    if any(e["praca"] != "Brasília - DF" or (e.get("vmin"), e.get("vmax")) != (2, 29)
           for e, _ in fora):
        erros.append("há entrada fora de Brasília 2–29")

    print("  3. nenhuma é Ambulatorial (essa é genuinamente sem franquia)")
    if any(e["acomodacao"] == "Ambulatorial" for e, _ in fora):
        erros.append("o ambulatorial sem franquia seria removido — não deve")

    print("  4. o gêmeo COM franquia sobrevive, com o mesmo preço")
    ids_fora = {id(e) for e, _ in fora}
    if any(id(f) in ids_fora for _, f in fora):
        erros.append("um gêmeo seria removido junto")

    print("  5. Brasília fica com Nosso Plano vendável em 2 a 29")
    resta = [e for e in cat if id(e) not in ids_fora
             and e.get("praca") == "Brasília - DF" and e.get("operadora") == "Hapvida"
             and (e.get("vmin"), e.get("vmax")) == (2, 29)
             and "Nosso Plano" in e["label"]]
    acs = {e["acomodacao"] for e in resta}
    if acs != {"Ambulatorial", "Enfermaria", "Apartamento"}:
        erros.append("Brasília 2–29 ficaria com acomodações %s" % sorted(acs))
    print("     sobram %d entradas, acomodações %s" % (len(resta), sorted(acs)))

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-franquia-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    novo = [e for e in cat if id(e) not in ids_fora]
    json.dump(novo, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas removidas, catálogo agora com %d" % (len(fora), len(novo)))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
