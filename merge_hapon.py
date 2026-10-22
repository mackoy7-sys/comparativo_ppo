#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APLICA A TABELA HAPVIDA 21/10/2026 a 31/12/2026 no catalog.json.

Le o que o build_hapon_out.py produziu em /tmp/hapon_out_parsed.json e atualiza
SO o campo `precos` das entradas Hapvida (Empresarial e Individual) das pracas
cobertas pelos 5 PDFs da remessa.

Esta remessa quase nao mexe em preco: de 1.499 entradas conferidas, 1.495 estao
identicas as que ja estao no ar e 4 mudam -- Nosso Plano Individual Ambulatorial
de Aracaju, que desceu exatos 5% em todas as faixas. A versao "+ Odonto" manteve
a mesma razao sobre o preco medico em todas as faixas (0,97769), que e a prova
de que a leitura das colunas nao escorregou.

O que NAO e tocado:
  - Coletivo por Adesao, as concorrentes e toda a linha NDI (Smart, Advance,
    Premium, Infinity, Metais), que veio na carga de 20-21/10 e nao faz parte
    desta remessa;
  - o campo pr2 (reembolso parcial dos produtos NotreDame);
  - as entradas que o catalogo tem e esta tabela nao traz -- ficam com o preco
    da vigencia anterior, pela regra de sempre. Sao 287, e duas merecem o olho
    do usuario (relatadas na trava 7):

      * NOSSO MEDICO EM APARTAMENTO (263 entradas, 22 pracas no Super Simples e
        12 no PME). NAO e falha de leitura: em 28/09 o bloco trazia
        "ACOMODACAO ENFERM APART" com registro ANS 505.451/25-6 e cod. interno
        39880/39879; em 21/10 as colunas de apartamento sumiram da tabela. Ou o
        produto saiu de linha, ou a tabela deixou de reafirma-lo.

      * NOSSO PLANO SEM FRANQUIA EM BRASILIA, enfermaria e apartamento (4). Em
        Brasilia o bloco tem seis colunas: SEM franquia so em S/ACOM (cod.
        21298) e COM FRANQUIA em S/ACOM, ENFERM e APART (11615/11022/11034).
        Ou seja, enfermaria e apartamento ali so existem COM franquia -- e o
        catalogo carrega as duas versoes com o MESMO preco, o que faz o
        vendedor cotar "sem franquia" por um valor que e o da franquia. Ja
        estava assim antes desta carga (o merge_dez.py de 28/09 registra o
        mesmo caso); nao e consertado aqui porque tirar produto do ar e decisao
        comercial, nao de carga.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
NOVO = "/tmp/hapon_out_parsed.json"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
VIGENCIA = "21/10/2026 a 31/12/2026"

# lidas a mao no texto cru dos PDFs (pelo CÓD. INTERNO, nao pelo rotulo):
#   Goiânia SS pág 19 .... 39870 / 39936          Campo Grande 1 vida pág 1 .. 39932
#   Brasília SS pág 23 ... 21298                  Aracaju Ambulatorial pág 21  21028 / 11331
AMOSTRAS = [
    ("Goiânia - GO", "Nosso Médico", "Enfermaria", "Parcial", 2, 191.15, 1122.65),
    ("Goiânia - GO", "Nosso Plano", "Enfermaria", "Parcial", 2, 224.61, 1319.15),
    ("Campo Grande - MS", "Integrado", "Enfermaria", "Parcial", 1, 313.68, 1880.53),
    ("Brasília - DF", "Nosso Plano", "Ambulatorial", "Parcial", 2, 148.42, 871.71),
    ("Aracaju - SE", "Nosso Plano + Odonto (PF)", "Ambulatorial", "Parcial", None, 212.52, 1153.16),
    ("Aracaju - SE", "Nosso Plano (PF)", "Ambulatorial", "Completa", None, 139.85, 758.88),
]


def chave(e):
    return (e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"],
            e.get("vmin"), e.get("vmax"), bool(e.get("mei")))


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    bruto = json.load(open(NOVO, encoding="utf-8"))
    novos = {}
    for praca, ents in bruto.items():
        for n in ents:
            n["praca"] = praca
            novos.setdefault(chave(n), []).append(n)
    cobertas = set(bruto)

    alvo = [e for e in cat if e["operadora"] == "Hapvida"
            and e.get("tipo") in ("Empresarial", "Individual")
            and not e.get("contratacao")          # Adesão/Compulsório ficam fora
            and e.get("praca") in cobertas]
    print("praças na tabela nova: %d · entradas do catálogo nessas praças: %d\n"
          % (len(cobertas), len(alvo)))

    muda, iguais, sem_par = [], 0, []
    for e in alvo:
        k = chave(e)
        if k not in novos:
            sem_par.append(e); continue
        n = novos[k][0]
        if all(abs(n["precos"][b] - e["precos"][b]) < 0.005 for b in BANDS):
            iguais += 1
        else:
            muda.append((e, n))

    erros = []
    print("travas:")

    print("  1. só Hapvida (Empresarial/Individual, sem Adesão) das praças cobertas")
    fora = [e for e, _ in muda if e["operadora"] != "Hapvida"
            or e.get("tipo") not in ("Empresarial", "Individual") or e.get("contratacao")]
    if fora: erros.append("%d entradas fora do escopo" % len(fora))

    print("  2. Adesão, concorrentes e toda a linha NDI ficam intocados")
    RE_NDI = ("Smart", "Adv ", "Advance", "Premium", "Infinity",
              "Prata", "Ouro", "Diamante")
    ids_muda = {id(e) for e, _ in muda}
    intocaveis = [e for e in cat
                  if e["operadora"] != "Hapvida" or e.get("contratacao")
                  or any(str(e.get("label", "")).startswith(p) for p in RE_NDI)]
    if any(id(e) in ids_muda for e in intocaveis):
        erros.append("uma entrada fora do escopo seria alterada")

    print("  3. nenhum preço SOBE (esta tabela é promocional — desceu em 100%)")
    subiu = [(e, n, b) for e, n in muda for b in BANDS
             if n["precos"][b] > e["precos"][b] + 0.005]
    if subiu:
        erros.append("%d valores SUBIRIAM — conferir antes de gravar" % len(subiu))
        for e, n, b in subiu[:8]:
            print("     %-22s %-26s %-12s %-9s [%s] %.2f -> %.2f"
                  % (e["praca"], e["label"], e["acomodacao"], e["coparticipacao"],
                     b, e["precos"][b], n["precos"][b]))

    print("  4. curva de faixa etária não decresce (regra ANS)")
    mau = [n for _, n in muda
           if any(n["precos"][BANDS[i + 1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9))]
    if mau: erros.append("%d entradas novas com curva decrescente" % len(mau))

    print("  5. só o campo `precos` muda; nada de label, porte, praça ou tipo")
    for e, n in muda:
        if chave(e) != chave(n): erros.append("chave divergente em %s" % str(chave(e)))

    # O "+ Odonto" nao e um abatimento fixo em reais: e um PERCENTUAL sobre o
    # preco medico, constante em todas as faixas (em Aracaju, 0,97769). Em
    # reais a diferenca cresce com a idade -- 4,85 na primeira faixa e 26,34 na
    # ultima --, o que parece erro e nao e. A razao e que tem de ser estavel: se
    # ela variar, a leitura escorregou de coluna.
    print("  6. o desconto do \"+ Odonto\" é o mesmo percentual em todas as faixas")
    for e, n in muda:
        if " + Odonto" not in n["label"]: continue
        par = novos.get((n["praca"], n["label"].replace(" + Odonto", ""), n["acomodacao"],
                         n["coparticipacao"], n.get("vmin"), n.get("vmax"), bool(n.get("mei"))))
        if not par: continue
        r = [n["precos"][b] / par[0]["precos"][b] for b in BANDS]
        if max(r) - min(r) > 0.0005:
            erros.append("razão do odonto varia em %s %s: %.5f a %.5f"
                         % (n["praca"], n["label"], min(r), max(r)))

    print("  7. %d amostras lidas à mão no texto cru do PDF" % len(AMOSTRAS))
    for praca, label, acom, cop, vmin, p0, p59 in AMOSTRAS:
        k = [n for kk, v in novos.items() for n in v
             if kk[0] == praca and kk[1] == label and kk[2] == acom
             and kk[3] == cop and kk[4] == vmin]
        if not k:
            erros.append("amostra ausente: %s %s" % (praca, label)); continue
        if abs(k[0]["precos"]["00 a 18"] - p0) > 0.005 or abs(k[0]["precos"]["59 ou mais"] - p59) > 0.005:
            erros.append("amostra diverge: %s %s %.2f/%.2f" %
                         (praca, label, k[0]["precos"]["00 a 18"], k[0]["precos"]["59 ou mais"]))

    print("  8. o que a tabela nova não traz fica com o preço anterior")
    print("     %d entradas mantidas:" % len(sem_par))
    for lb, q in collections.Counter(e["label"] for e in sem_par).most_common():
        print("        %-44s %d" % (lb, q))

    print("  9. o campo pr2 (reembolso parcial NotreDame) não é tocado")
    if any(("pr2" in e) for e, _ in muda):
        erros.append("uma entrada com pr2 seria alterada — não deveria")

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    d = [(n["precos"][b] - e["precos"][b]) / e["precos"][b] for e, n in muda for b in BANDS]
    print("\nresumo: %d entradas mudam, %d já estavam iguais" % (len(muda), iguais))
    if d:
        print("        variação média %.2f%% (de %.2f%% a %.2f%%)"
              % (sum(d) / len(d) * 100, min(d) * 100, max(d) * 100))
    for e, _ in muda:
        print("        %-20s %-28s %-12s %s" % (e["praca"], e["label"], e["acomodacao"],
                                                e["coparticipacao"]))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-hapon-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    for e, n in muda:
        e["precos"] = {b: n["precos"][b] for b in BANDS}
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas atualizadas" % len(muda))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
