#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carrega no odonto.json o ramo EMPRESARIAL, que nunca tinha entrado.

O PROBLEMA: as 428 entradas "+ Odonto" empresariais saiam com valor dental
ZERO -- o odontoVal() procura ODONTO[praca]['Empresarial'][...] e o arquivo so
tinha o ramo 'Individual'. Toda cotacao PME com odonto mostrava "Mensalidade
incompleta" e entregava ao cliente um total sem a parte odontologica. As 398
entradas PF estavam certas; so o lado empresarial faltava.

A FONTE e o quadro ODONTOLOGIA que toda pagina da remessa carrega. Ancorado no
que a propria tabela emite -- REGISTRO ANS 471.904/14-2 e CÓD. INTERNO 9732 --
e nao no rotulo:

    porte                VALOR      VALOR PROMO
    Super Simples 1-29   R$ 78,87   R$ 23,25
    PME 30-99            R$ 75,84   R$ 14,87

O VALOR PROMO e o que vale: "Valor Promocional quando beneficiario adquire, no
ato da contratacao, um plano medico-hospitalar HAPVIDA" -- que e exatamente o
caso de quem esta cotando. E por isso que o valor depende do PORTE e nao da
praca: o desconto e da campanha, nao da regiao.

⚠️ O valor muda por PORTE, o que o odonto.json nao sabia representar -- a chave
era praca x tipo x familia. O ramo Empresarial entra com um nivel a mais:

    "Empresarial": {"1-29": {"Ambulatorial": {...}, "Hospitalar": {...}},
                    "30-99": {...}}

A familia (Ambulatorial/Hospitalar) e mantida por simetria com o Individual,
mas no Empresarial o quadro da tabela e UM so por pagina: as duas familias
recebem o mesmo valor. Fica assim para o dia em que a tabela separar.

Praca sem o quadro na pagina NAO recebe valor inventado: fica de fora, e o
odontoFalta() continua avisando na tela. Hoje sao 21 pracas no PME.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, json, os, re, shutil, sys, time, unicodedata
import pdfplumber

AQUI = os.path.dirname(os.path.abspath(__file__))
ODO = os.path.join(AQUI, "odonto.json")
RAIZ = "/Users/marcoscorrea/Downloads/"
HAP = RAIZ + "[Hapvida]_Tabela_de_Vendas_-_" + "Vigência_21_10_2026_a_31_12_2026/"
CLI = RAIZ + "[Clinipam]_Tabela_de_Vendas_-_" + "Vigência_21_10_2026_a_31_12_2026/"
CCG = RAIZ + "[CCG]_Tabela_de_Vendas_-_" + "Vigência_21_10_2026_a_31_12_2026/"
NDI = RAIZ + "HMO/"


def acha(dirp, pedaco):
    """Primeiro PDF da pasta cujo nome contem o pedaco (ASCII, sem acento)."""
    if not os.path.isdir(dirp):
        return dirp + pedaco + ".pdf"
    for f in sorted(os.listdir(dirp)):
        if f.lower().endswith(".pdf") and pedaco.lower() in f.lower():
            return dirp + f
    return dirp + pedaco + ".pdf"



# (arquivo, porte, promo de referencia) — a referencia e trava, nao suposicao:
# praca que fuja dela so passa se estiver em EXCECOES, conferida a mao.
FONTES = [
    (HAP + "20261021 a 20261231 - Super Simples 1 vida.pdf", "1-29", 23.25),
    (HAP + "20261021 a 20261231 - Super Simples 2 a 29 vidas.pdf", "1-29", 23.25),
    (HAP + "20261021 a 20261231 - PME v2.pdf", "30-99", 14.87),
    (CLI + "20261021 a 20261231 - Super Simples.pdf", "1-29", 23.25),
    (CLI + "20261021 a 20261231 - PME v2.pdf", "30-99", 14.87),
    (CCG + "20261021 a 20261231 - Super Simples - 1 vida.pdf", "1-29", 23.25),
    (CCG + "20261021 a 20261231 - Super Simples - 2 a 29 vidas.pdf", "1-29", 23.25),
    (CCG + "20261021 a 20261231 - PME.pdf", "30-99", 14.87),
    # NDI SP/RJ: o odonto e GRATUITO junto do medico (VALOR PROMO R$ 0,00)
    (NDI + "20261021 a 20261231 - Super Simples 1 Vida v2.pdf", "1-29", 0.00),
    (NDI + "20261021 a 20261231 - Super Simples 2 a 29 vidas - Demais Empresas.pdf", "1-29", 0.00),
    (NDI + "20261021 a 20261231 - Super Simples 2 a 29 vidas - MEI.pdf", "1-29", 0.00),
    # ⚠️ o nome deste arquivo vem com o acento corrompido pela origem
    # ("Compulsขrio"), entao e resolvido por pedaco ASCII, nao por literal
    (acha(NDI, "PME - Compuls"), "30-99", 0.00),
    # NDI Minas (vigencia 01/10, que segue valendo: nao veio remessa nova)
    (RAIZ + "20261001 a 20261231 - Super Simples.pdf", "1-29", 24.50),
    (RAIZ + "20261001 a 20261231 - PME NDI Minas.pdf", "30-99", 14.87),
]

# Pracas cujo VALOR PROMO difere da referencia. Lidas a mao na linha crua, pelo
# registro 471.904/14-2 + cod. 9732:
#   Uberaba PME ... "+ODONTO PREMIUM NACIONAL 471.904/14-2 9732 R$ 1 9,63"
EXCECOES = {("Uberaba - MG", "30-99"): 19.63}

# Em Uberaba e Uberlandia o quadro do Super Simples tem UMA coluna so
# ("VALOR PROMO *", sem a coluna VALOR). Nao e valor faltando: e coluna a
# menos. Nesses casos o `cheio` fica None e o folder usa so o promocional,
# que e o que o cliente paga.

# Cada rede vende um produto odontologico proprio, com registro e codigo
# proprios -- o valor e que e o mesmo. Ancorar no PAR (registro, codigo), que e
# o que a tabela emite, e nao no nome, que varia ("PREMIUM NACIONAL",
# "PREMIUM", "COLETIVO EMPRESARIAL ODONTOLOGICO").
PRODUTOS = [
    ("471.904/14-2", "9732",  "Premium Nacional"),             # Hapvida sede
    ("495.607/23-9", "20869", "Premium"),                      # Clinipam
    ("495.628/23-1", "20748", "Coletivo Empresarial Odonto"),  # CCG
    ("495.614/23-1", "40832", "Odonto Premium"),               # NDI SP/RJ
    ("495.901/23-9", "23389", "Premium (NDI MG)"),             # NDI Minas
]
# A praca aparece de tres jeitos nas remessas: "GOIÂNIA - GO" (caixa alta),
# "São Paulo - SP" (caixa mista, nas tabelas NDI) e "JOINVILLE" (sem UF, no PME
# da Hapvida). Em vez de um regex que tente adivinhar qual linha e a praca --
# e que, frouxo o bastante para pegar as tres formas, pega tambem "TABELA DE
# VENDAS PROMOCIONAL" --, quem decide e o CATALOGO: testa-se as primeiras
# linhas e fica a primeira que casa com uma praca conhecida.
TOPO = 5   # quantas linhas do alto da pagina considerar
CAT = os.path.join(AQUI, "catalog.json")
# "R$ 78,87" e tambem "R$ 7 5,84" (o PDF parte o numero no meio)
VAL = re.compile(r"R\$\s*((?:\d[\d\s\.]*),\d{2})")

# O PDF escreve a praca em CAIXA ALTA ("UBERABA - MG") e o catalogo em caixa
# mista e com acento ("Uberaba - MG"). Em vez de um de-para a mao, que erra em
# acento e conectivo, o nome e casado contra a LISTA DE PRACAS DO CATALOGO,
# comparando sem acento e sem caixa -- a mesma lista que o cotador usa.
def deacc(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _chave(s):
    return re.sub(r"\s+", " ", deacc(s or "").upper()).strip()


# A unica praca cujo nome de tabela nao e o nome de catalogo: as tabelas NDI
# escrevem "São Paulo - SP" e o catalogo chama a praca inteira de "SP / RMSP",
# porque ela cobre os 39 municipios da regiao metropolitana.
APELIDOS = {"SAO PAULO - SP": "SP / RMSP", "SAO PAULO": "SP / RMSP"}


def mapa_pracas():
    """nome normalizado -> praca do catalogo, com e sem UF.

    A forma SEM UF so entra quando e inequivoca: se duas pracas de UFs
    diferentes tivessem a mesma cidade, "JOINVILLE" nao poderia decidir qual e,
    e aí e melhor nao casar do que casar errado."""
    cat = json.load(open(CAT, encoding="utf-8"))
    pracas = {e.get("praca") for e in cat if e.get("praca")}
    m = {_chave(p): p for p in pracas}
    sem_uf = collections.Counter(_chave(re.sub(r"\s*-\s*[A-Z]{2}$", "", p)) for p in pracas)
    for p in pracas:
        k = _chave(re.sub(r"\s*-\s*[A-Z]{2}$", "", p))
        if sem_uf[k] == 1:
            m.setdefault(k, p)
    for apelido, praca in APELIDOS.items():
        if praca in pracas:
            m.setdefault(apelido, praca)
    return m


def num(s):
    return float(s.replace(" ", "").replace(".", "").replace(",", "."))


def le(fn, porte, referencia):
    """praca -> (cheio, promo), lido da linha que carrega o registro e o codigo."""
    out, sem, estranhos, uma_col = {}, [], [], []
    pdf = pdfplumber.open(fn)
    for pg in pdf.pages:
        linhas = (pg.extract_text() or "").split("\n")
        cid = next((PRACAS[_chave(l)] for l in linhas[:TOPO]
                    if _chave(l) in PRACAS), None)
        if not cid:          # página sem praça conhecida — nada a preencher
            continue
        # a linha certa e a que tem O REGISTRO e O CODIGO -- nao o rotulo
        alvo = cod = prod = None
        for l in linhas:
            seco = re.sub(r"\s+", "", l)
            for reg, c, nome in PRODUTOS:
                if re.sub(r"\s+", "", reg) in seco and c in seco:
                    alvo, cod, prod = l, c, nome
                    break
            if alvo:
                break
        if not alvo:
            sem.append(cid)
            continue
        # os valores vem DEPOIS do codigo. E preciso cortar a TAXA DE ADESAO,
        # que em algumas pracas (Uberaba) divide a mesma linha e colocaria
        # R$ 20,00 como se fosse o promocional.
        trecho = alvo[alvo.find(cod) + len(cod):]
        corte = re.search(r"\bTX\b|TAXA DE ADES", trecho, re.I)
        if corte:
            trecho = trecho[:corte.start()]
        vs = [num(v) for v in VAL.findall(trecho)]
        if not vs:
            sem.append(cid); continue
        # o PROMOCIONAL e sempre a ultima coluna do quadro; o `cheio` so existe
        # quando o quadro tem as duas
        # R$ 0,00 e preco, nao ausencia: nas pracas NDI o odonto e gratuito
        # junto do medico, e isso precisa chegar ao cotador como zero de
        # verdade -- nao como "nao carregado".
        promo = vs[-1]
        cheio = vs[0] if len(vs) >= 2 else None
        if cheio is None:
            uma_col.append(cid)
        ref = EXCECOES.get((cid, porte), referencia)
        if abs(promo - ref) > 0.005:
            estranhos.append((cid, vs))
            continue
        out[cid] = (cheio, promo, prod)
    pdf.close()
    return out, sem, estranhos, uma_col


def main():
    global PRACAS
    PRACAS = mapa_pracas()
    print("praças conhecidas pelo catálogo: %d\n" % len(PRACAS))
    odo = json.load(open(ODO, encoding="utf-8"))
    novo = {}   # praca -> porte -> (cheio, promo, produto)
    erros, conflitos = [], []

    for fn, porte, referencia in FONTES:
        if not os.path.exists(fn):
            erros.append("arquivo ausente: " + fn.split("/")[-1]); continue
        achou, sem, estranhos, uma_col = le(fn, porte, referencia)
        rede = fn.split("/")[-2].split("]")[0].lstrip("[")
        nome = fn.split("/")[-1].replace("20261021 a 20261231 - ", "")[:32]
        prods = sorted({v[2] for v in achou.values()})
        print("%-9s %-34s %-6s %2d praças  promo %.2f  [%s]"
              % (rede, nome, porte, len(achou), referencia, ", ".join(prods) or "—"))
        exc = [c for c in achou if (c, porte) in EXCECOES]
        for c in exc:
            print("     exceção conferida: %-24s promo %.2f" % (c, achou[c][1]))
        if uma_col:
            print("     quadro com só a coluna promocional (%d): %s"
                  % (len(uma_col), ", ".join(u.split(" - ")[0] for u in uma_col)))
        if sem:
            print("     sem o quadro de odonto (%d): %s"
                  % (len(sem), ", ".join(s.split(" - ")[0] for s in sem[:8])))
        for cid, vs in estranhos:
            print("     ⚠ promocional fora da referência em %-24s %s" % (cid, vs))
            erros.append("promocional inesperado em %s (%s): %s — se for correto, "
                         "entra em EXCECOES" % (cid, fn[22:50], vs))
        for cid, v in achou.items():
            # Praca atendida por DUAS redes (Belo Horizonte esta na remessa
            # Hapvida e na NDI MG) tem dois quadros de odonto, com valores
            # diferentes. Deixar o ultimo arquivo lido vencer seria sorteio;
            # fica o PRIMEIRO -- a ordem de FONTES poe a rede principal da
            # praca na frente -- e o conflito e relatado, porque o produto
            # certo depende do plano medico, e nao so da praca.
            ja = novo.setdefault(cid, {}).get(porte)
            if ja and (abs(ja[1] - v[1]) > 0.005 or ja[2] != v[2]):
                conflitos.append((cid, porte, ja, v))
                continue
            novo[cid][porte] = v

    if conflitos:
        print("\n⚠ praça com mais de uma rede — fica o valor da primeira fonte:")
        for cid, porte, fica, sai in conflitos:
            print("   %-22s %-6s fica %.2f (%s)  ·  descartado %.2f (%s)"
                  % (cid, porte, fica[1], fica[2], sai[1], sai[2]))

    print("\npraças com valor empresarial: %d" % len(novo))
    por_porte = {}
    for cid, m in novo.items():
        for p in m:
            por_porte[p] = por_porte.get(p, 0) + 1
    for p, q in sorted(por_porte.items()):
        print("   porte %-6s %d praças" % (p, q))

    fora = sorted(set(odo) - set(novo))
    if fora:
        print("\npraças do odonto.json que não recebem ramo empresarial (%d):" % len(fora))
        print("   " + ", ".join(f.split(" - ")[0] for f in fora))

    print("\ntravas:")
    print("  1. o ramo Individual não é tocado")
    print("  2. praça sem o quadro na página não recebe valor — fica avisando na tela")
    print("  3. valor diferente do esperado aborta em vez de gravar")
    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = ODO + ".bak-emp-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(ODO, bak)
    for cid, m in novo.items():
        ramo = odo.setdefault(cid, {}).setdefault("Empresarial", {})
        for porte, (cheio, promo, prod) in m.items():
            d = {"promo": promo, "produto": prod}
            if cheio is not None:
                d["cheio"] = cheio
            ramo[porte] = {"Ambulatorial": dict(d), "Hospitalar": dict(d)}
    json.dump(odo, open(ODO, "w"), ensure_ascii=False)
    print("\ngravado: ramo empresarial em %d praças" % len(novo))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
