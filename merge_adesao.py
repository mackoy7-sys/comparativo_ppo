#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GRAVA O SEGMENTO COLETIVO POR ADESAO no catalog.json.

Le o bruto do build_adesao.py e insere entradas novas com tipo="Adesão".
Nao altera nenhuma entrada existente — Individual e PME ficam intactos.

Ensaio por padrao; grava so com --gravar (faz backup com carimbo de hora).

Decisoes registradas:
  - Coluna "Médica ¹" nas tabelas Hapvida (escolha do usuario em 24/09/2026;
    o documento nao explica a diferenca para "Médica ²", que e sempre o valor
    promocional do odonto mais um fixo de R$ 1 a R$ 10 conforme a praca).
  - Plano Referencia e o odontologico das tabelas Hapvida nao entram, mesmo
    criterio ja usado no PME.
  - Vigencia COMERCIAL ate 31/12/2026, informada pelo usuario em 24/09/2026.
    Os PDFs trazem impresso 01/07 a 30/09/2025 (e 05/11 a 31/12/2025 em
    Fortaleza), mas as tabelas seguem valendo. A data impressa fica guardada em
    "vigenciaImpressa" para nao se perder a procedencia; quem vai para a tela e
    a comercial.
"""
import collections, json, os, re, shutil, sys, time, unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
BRUTO = ("/private/tmp/claude-502/-Users-marcoscorrea/"
         "c9a5af99-295e-4076-8dfd-4750e4f0a0a9/scratchpad/adesao_bruto.json")
VIGENCIA = "até 31/12/2026"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]

# produto impresso -> (plano, label).
#   plano = chave que liga reembolso, rede e coparticipacao ao resto do cotador;
#           reaproveita-se onde o produto e o mesmo do PME.
#   label = IDENTIDADE do plano na tela. Tem de ser unica entre segmentos: o
#           cotador guarda a escolha do vendedor pelo label, entao um "Adv 600"
#           em dois segmentos faria a cotacao misturar preco de PME com o de
#           Adesao. O Individual ja resolve assim, com o sufixo "(PF)".
PROD = {
    "ADVANCE 600": ("600", "Adv 600 (Adesão)"),
    "ADVANCE 700": ("700", "Adv 700 (Adesão)"),
    "SMART 300": ("Smart 300", "Smart 300 (Adesão)"),
    "SMART 400": ("Smart 400", "Smart 400 (Adesão)"),
    "SMART 500": ("Smart 500", "Smart 500 (Adesão)"),
    "SMART 200 RIO": ("Smart 200 Rio", "Smart 200 Rio (Adesão)"),
    "SMART 200 UP": ("Smart 200 UP", "Smart 200 UP (Adesão)"),
    "SMART 200": ("Smart 200", "Smart 200 (Adesão)"),
    "SMART 200 SP CAPITAL": ("Smart 200 SP Capital", "Smart 200 SP Capital (Adesão)"),
    "SMART 200 CAMPINAS": ("Smart 200 Campinas", "Smart 200 Campinas (Adesão)"),
    "SMART 200 JUNDIAÍ": ("Smart 200 Jundiaí", "Smart 200 Jundiaí (Adesão)"),
    "SMART 200 SOROCABA": ("Smart 200 Sorocaba", "Smart 200 Sorocaba (Adesão)"),
    "SMART 200 AMERICANA": ("Smart 200 Americana", "Smart 200 Americana (Adesão)"),
    "SMART 200 ABC": ("Smart 200 ABC", "Smart 200 ABC (Adesão)"),
    "SMART 150 ABC": ("Smart 150 ABC", "Smart 150 ABC (Adesão)"),
    "SMART 150 LESTE FLUMINENSE": ("Smart 150 Leste Fluminense", "Smart 150 Leste Fluminense (Adesão)"),
    "SMART 200 UP+RMCA": ("Smart 200 UP+RMCA", "Smart 200 UP+RMCA (Adesão · Estudante)"),
    "NOSSOPLANO": ("Nosso Plano", "Nosso Plano (Adesão)"),
    "PLENO": ("Pleno", "Pleno (Adesão)"),
    "NOSSOPLANO-COMFRANQUIA*": ("Nosso Plano", "Nosso Plano Franquia (Adesão)"),
}
FORA = {"BASIC REFERÊNCIA"}   # plano referencia nao e comercializado pelo time

# amostras conferidas a mao contra o PDF nesta sessao — se a leitura mudar de
# comportamento, elas quebram antes de qualquer gravacao.
AMOSTRAS = [
    ("SP / RMSP", "Smart 200 SP Capital (Adesão)", "Enfermaria", "Completa", "00 a 18", 218.37),
    ("SP / RMSP", "Smart 200 SP Capital (Adesão)", "Enfermaria", "Completa", "59 ou mais", 877.26),
    ("SP / RMSP", "Adv 600 (Adesão)", "Enfermaria", "Completa", "00 a 18", 452.96),
    ("SP / RMSP", "Adv 600 (Adesão)", "Apartamento", "Parcial", "29 a 33", 985.25),
    ("Campinas - SP", "Smart 500 (Adesão)", "Apartamento", "Completa", "00 a 18", 461.90),
    ("João Pessoa - PB", "Nosso Plano (Adesão)", "Enfermaria", "Completa", "00 a 18", 215.92),
    ("Franca - SP", "Nosso Plano (Adesão)", "Enfermaria", "Completa", "00 a 18", 157.28),
]


def chave(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace(" ", "")


def monta():
    bruto = json.load(open(BRUTO))
    cat = json.load(open(CAT))
    pracas = {chave(e.get("praca") or "SP / RMSP"): (e.get("praca") or "SP / RMSP")
              for e in cat}
    pracas[chave("São Paulo - SP")] = "SP / RMSP"   # a praca de SP se chama assim aqui

    novas, descartes = [], collections.Counter()
    for c in bruto:
        if c["arquivo"].startswith("HAPVIDA"):
            if not c.get("medica"): descartes["hapvida: coluna não-médica"] += 1; continue
            if "¹" not in (c.get("assist") or ""):
                descartes["hapvida: coluna Médica ²"] += 1; continue
        prod = c["produto"]
        if prod in FORA: descartes["plano referência"] += 1; continue
        if prod not in PROD: descartes["produto sem mapa: " + str(prod)] += 1; continue
        praca = pracas.get(chave(c["praca"]))
        if not praca: descartes["praça fora do catálogo: " + str(c["praca"])] += 1; continue
        if sorted(c["precos"]) != sorted(BANDS):
            descartes["faixas incompletas"] += 1; continue

        cop = "Parcial" if "Parcial" in c["arquivo"] else "Completa"
        plano, label = PROD[prod]
        novas.append({
            "operadora": "Hapvida", "plano": plano, "label": label,
            "acomodacao": c["acomodacao"], "coparticipacao": cop,
            "mei": False, "categoria": "Geral",
            "precos": {b: c["precos"][b] for b in BANDS},
            "tipo": "Adesão", "praca": praca,
            "vmin": None, "vmax": None,
            "administradora": "OVER", "vigencia": VIGENCIA,
            "vigenciaImpressa": c.get("vigencia"),
            "codint": c["cod"], "_fonte": c["arquivo"], "_pg": c["pg"],
        })
    return cat, novas, descartes


def travas(cat, novas):
    """Cada trava imprime uma linha. Qualquer falha aborta antes de gravar."""
    erros = []

    print("1) nenhuma entrada de Adesão já existe no catálogo")
    ja = [e for e in cat if e.get("tipo") == "Adesão"]
    if ja: erros.append("já existem %d entradas tipo Adesão" % len(ja))

    print("2) curva de faixa etária não decresce (regra ANS)")
    mau = [n for n in novas
           if any(n["precos"][BANDS[i + 1]] < n["precos"][BANDS[i]] - 0.004 for i in range(9))]
    if mau:
        erros.append("%d entradas com curva decrescente (ex.: %s %s %s)"
                     % (len(mau), mau[0]["praca"], mau[0]["label"], mau[0]["acomodacao"]))

    # Tolerancia de 0,2%: os precos ja vem arredondados ao centavo, entao a
    # razao entre faixas nunca bate no ultimo digito. O erro que esta trava
    # existe para pegar (digito trocado na origem) desloca a razao em 2% ou
    # mais — folga de sobra.
    # Tolerancia de 0,2%: os precos ja vem arredondados ao centavo, entao a razao
    # entre faixas nunca bate no ultimo digito. O erro que esta trava existe para
    # pegar (digito trocado na origem) desloca a razao em 2% ou mais.
    #
    # Uma pagina pode ter MAIS DE UMA curva legitima: no Rio, os produtos
    # cariocas (Smart 200 Rio, Smart 150 Leste Fluminense) reajustam por uma
    # curva e os nacionais por outra, cada uma com varias colunas. So e suspeita
    # a coluna que fica SOZINHA na sua curva.
    TOL = 0.002
    print("3) cada coluna acompanha uma curva de reajuste que outra coluna do quadro também segue")
    grupos = collections.defaultdict(list)
    for n in novas: grupos[(n["_fonte"], n["_pg"])].append(n)
    fora = []
    for g in grupos.values():
        if len(g) < 3: continue
        curvas = [[n["precos"][BANDS[i + 1]] / n["precos"][BANDS[i]] for i in range(9)]
                  for n in g]
        for i, (n, c) in enumerate(zip(g, curvas)):
            irmas = sum(1 for j, o in enumerate(curvas) if j != i
                        and all(abs(c[k] - o[k]) <= TOL * o[k] for k in range(9)))
            if irmas: continue
            # sozinha: aponta as faixas que a separam da curva mais comum
            ref = [sorted(o[k] for o in curvas)[len(curvas) // 2] for k in range(9)]
            fora.append((n, [BANDS[k + 1] for k in range(9)
                             if abs(c[k] - ref[k]) > TOL * ref[k]]))
    if fora:
        print("   %d coluna(s) sem par no quadro — conferir na origem:" % len(fora))
        for n, fx in fora[:10]:
            print("     %-22s %-26s %-12s %-9s faixa %s (cód %s)"
                  % (n["praca"], n["label"], n["acomodacao"], n["coparticipacao"],
                     ", ".join(fx), n["codint"]))

    print("4) Parcial é mais caro que Completa na mesma combinação")
    por = collections.defaultdict(dict)
    for n in novas:
        por[(n["praca"], n["label"], n["acomodacao"])][n["coparticipacao"]] = n["precos"]
    inv = [k for k, v in por.items() if "Parcial" in v and "Completa" in v
           and any(v["Parcial"][b] <= v["Completa"][b] for b in BANDS)]
    if inv: erros.append("%d combinações com Parcial <= Completa (ex.: %s)" % (len(inv), inv[0]))

    print("5) amostras conferidas à mão contra o PDF")
    for praca, label, acom, cop, faixa, esperado in AMOSTRAS:
        achou = [n for n in novas if n["praca"] == praca and n["label"] == label
                 and n["acomodacao"] == acom and n["coparticipacao"] == cop]
        if not achou: erros.append("amostra ausente: %s %s %s %s" % (praca, label, acom, cop)); continue
        if abs(achou[0]["precos"][faixa] - esperado) > 0.004:
            erros.append("amostra diverge: %s %s %s %s [%s] %.2f != %.2f"
                         % (praca, label, acom, cop, faixa, achou[0]["precos"][faixa], esperado))

    print("6) todas as praças novas já existem no cotador")
    antigas = set(e.get("praca") or "SP / RMSP" for e in cat)
    novas_pr = set(n["praca"] for n in novas) - antigas
    if novas_pr: erros.append("praças inéditas: %s" % sorted(novas_pr))

    print("7) nenhum código interno repetido na mesma praça/coparticipação")
    dup = [k for k, v in collections.Counter(
        (n["praca"], n["coparticipacao"], n["codint"]) for n in novas).items() if v > 1]
    if dup: erros.append("%d código(s) repetido(s), ex.: %s" % (len(dup), dup[0]))

    return erros


def main():
    cat, novas, descartes = monta()
    print("entradas novas: %d   (catálogo tem %d)\n" % (len(novas), len(cat)))
    for k, v in descartes.most_common(): print("   descartado %5d  %s" % (v, k))
    print()
    erros = travas(cat, novas)
    if erros:
        print("\n" + "!" * 70)
        for e in erros: print("!! " + e)
        print("!! NADA GRAVADO")
        return 1

    print("\nresumo por praça: %d praças, %d produtos, %d entradas"
          % (len(set(n["praca"] for n in novas)), len(set(n["label"] for n in novas)), len(novas)))
    for k, v in sorted(collections.Counter(n["label"] for n in novas).items()):
        print("   %-30s %d" % (k, v))

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-adesao-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    pid = max(e["id"] for e in cat)
    for n in novas:
        pid += 1
        n["id"] = pid
        for k in ("_fonte", "_pg"): n.pop(k)
    cat.extend(novas)
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas (catálogo agora com %d)" % (len(novas), len(cat)))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
