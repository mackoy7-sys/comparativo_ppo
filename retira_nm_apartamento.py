#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retira do catalogo o NOSSO MEDICO em APARTAMENTO (352 entradas, 36 pracas).

POR QUE: a vigencia de 21/10/2026 tirou esse produto das tabelas de venda das
QUATRO redes, e em cada uma o numero de registro da ANS do apartamento sai
junto -- que e o que separa "retirada de produto" de "falha de leitura":

    rede            registro que sumiu   conferido em
    Hapvida sede    505.451/25-6         Goiania, Super Simples: 28/09 trazia
                                         "ACOMODACAO ENFERM APART" com cod.
                                         39880/39879; 21/10 so ENFERM
    Clinipam        507.354/26-5         Curitiba, PME: 01/10 com cod.
                                         42306/42304; 21/10 so ENFERM
    CCG             504.955/25-5         Porto Alegre, Individual: 01/10 com
                                         cod. 38861/38859; 21/10 so ENFERM
    NDI (SP/RMSP)   507.188/25-7         Sao Paulo, Super Simples: 08/09 com
                                         cod. 41718; 21/10 so ENFERM

Em todos os casos o preco da ENFERMARIA ficou igual -- nao foi reajuste nem
rediagramacao: a coluna do apartamento deixou de existir.

Decisao do usuario em 21/10/2026: tirar as 352 do ar. Ate aqui elas seguiam no
cotador com o preco da vigencia anterior, pela regra de que o que nao veio na
remessa se mantem -- mas essa regra existe para tabela que nao foi reafirmada,
nao para produto que saiu de linha.

O QUE NAO MUDA:
  - a ENFERMARIA do Nosso Medico, que continua vendida em todas as pracas
    (nenhuma combinacao fica sem acomodacao -- isso e trava, nao promessa);
  - os ids das entradas que ficam (cotacao salva no historico continua
    resolvendo);
  - copart.json e odonto.json, que nao tem a acomodacao na chave (o odonto
    agrupa apartamento e enfermaria no mesmo 'Hospitalar');
  - o historico de cotacoes, que guarda o folder ja renderizado em
    `folder_html` -- cotacao antiga com apartamento continua abrindo igual.

DEPOIS DE RODAR, regerar o rede_full.json: o mapa `planos` dele sai do
catalogo, entao as chaves "<praca>|Nosso Medico...|Apartamento|CO" viram
orfas ate o build_rede_full.py rodar de novo.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
ESPERADO = 352


def alvo(e):
    return (e.get("operadora") == "Hapvida"
            and str(e.get("label", "")).startswith("Nosso Médico")
            and e.get("acomodacao") == "Apartamento")


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    fora = [e for e in cat if alvo(e)]
    fica = [e for e in cat if not alvo(e)]

    print("catálogo: %d entradas  ·  a remover: %d  ·  ficam: %d"
          % (len(cat), len(fora), len(fica)))

    erros = []
    print("\ntravas:")

    print("  1. são exatamente as %d entradas esperadas" % ESPERADO)
    if len(fora) != ESPERADO:
        erros.append("esperava %d entradas, achei %d" % (ESPERADO, len(fora)))

    print("  2. só Hapvida, só Apartamento, só rótulos Nosso Médico")
    ops = {e.get("operadora") for e in fora}
    acs = {e.get("acomodacao") for e in fora}
    labs = {e.get("label") for e in fora}
    if ops != {"Hapvida"} or acs != {"Apartamento"}:
        erros.append("escopo errado: operadoras=%s acomodações=%s" % (ops, acs))
    if not all(l.startswith("Nosso Médico") for l in labs):
        erros.append("rótulo fora do Nosso Médico: %s" % labs)
    print("     rótulos: %s" % ", ".join(sorted(labs)))

    print("  3. nenhuma combinação fica SEM acomodação")
    def comb(e):
        return (e.get("praca"), e.get("label"), e.get("tipo"),
                e.get("coparticipacao"), e.get("vmin"), e.get("vmax"),
                bool(e.get("mei")), e.get("contratacao"))
    restam = {comb(e) for e in fica}
    orfas = [c for c in {comb(e) for e in fora} if c not in restam]
    if orfas:
        erros.append("%d combinações ficariam sem nenhuma acomodação" % len(orfas))
        for c in orfas[:6]:
            print("     órfã: %s" % (c,))

    print("  4. quem fica não é tocado — nem preço, nem id, nem rótulo")
    ids_fora = {id(e) for e in fora}
    if any(id(e) in ids_fora for e in fica):
        erros.append("uma entrada aparece nos dois lados")
    ids = [e.get("id") for e in fica]
    if None in ids or len(set(ids)) != len(ids):
        erros.append("as entradas que ficam têm id repetido ou ausente")

    print("  5. a enfermaria do Nosso Médico continua em todas as praças")
    pr_fora = {e["praca"] for e in fora}
    pr_enf = {e["praca"] for e in fica
              if e.get("operadora") == "Hapvida"
              and str(e.get("label", "")).startswith("Nosso Médico")
              and e.get("acomodacao") == "Enfermaria"}
    sem = sorted(pr_fora - pr_enf)
    if sem:
        erros.append("praças que ficariam sem Nosso Médico nenhum: %s" % sem)

    print("\npor praça:")
    for p, q in sorted(collections.Counter(e["praca"] for e in fora).items()):
        print("   %-30s %2d" % (p, q))

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-nmapart-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    json.dump(fica, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas removidas, catálogo agora com %d"
          % (len(fora), len(fica)))
    print("backup: " + bak)
    print("\n⚠️ rode agora o build_rede_full.py — o mapa de planos da rede sai "
          "do catálogo e ficou com chaves órfãs de Apartamento.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
