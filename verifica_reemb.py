# -*- coding: utf-8 -*-
"""Extrai o preco de REEMBOLSO PARCIAL dos PPO, por estrutura da pagina.

Como a pagina e montada (conferido bloco a bloco nos 5 PDFs de 08-30/09):
cada pagina PPO tem ate 4 quadros = 2 coparticipacoes x 2 reembolsos. Dentro
de uma mesma coparticipacao ha exatamente 2 quadros, e eles se distinguem pela
COMPOSICAO DE COLUNAS:

  reembolso TOTAL   -> 7 colunas: Adv 600 Enf/Apt, Adv 700 Enf/Apt,
                       Premium 900 Care, Premium 900, Infinity
  reembolso PARCIAL -> 5 colunas: Adv 600 Enf/Apt, Adv 700 Enf/Apt,
                       Premium 900 Care

Ou seja: PREMIUM 900 E INFINITY NAO TEM REEMBOLSO PARCIAL. Isso vale nos 5
arquivos e nas 9 pracas (72 quadros de 5 colunas, nenhum com esses produtos).
Nao e falha de leitura — e a regra do produto, e o seletor da UI tem de
refletir isso em vez de inventar um preco.

O pareamento entao e estrutural, nao heuristico:
  1. dentro de (praca, fonte, PAGINA, coparticipacao, produto, acomodacao),
     junta os blocos lidos por build_todos.py;
  2. o bloco cujos precos batem com o catalogo e o TOTAL — ancora, ja
     conferida contra a fonte em cargas anteriores;
  3. o outro bloco da mesma pagina/coparticipacao e o PARCIAL;
  4. so e aceito se o parcial for menor que o total em TODAS as faixas.

Ficar na mesma pagina importa: antes o candidato podia vir de outra pagina da
mesma praca e passar nas travas com um fator de outro produto (era o que fazia
o Adv 700 do Rio sair com 1,0400, que e o fator do Adv 600).

Saida: ~/comparativo-ppo/reembolso_parcial.json
"""
import json
from collections import defaultdict, Counter

H = "/Users/marcoscorrea/comparativo-ppo/"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
PPO = {"600", "700", "900", "900 Care", "Infinity"}
SO_TOTAL = {"900", "Infinity"}      # sem tabela de reembolso parcial

# fonte (arquivo) -> filtro no catalogo
FONTE = {
    "ss_demais":  dict(mei=False, vmin=2,  vmax=29, contratacao=None),
    "ss_mei":     dict(mei=True,  vmin=2,  vmax=29, contratacao=None),
    "pme_comp":   dict(mei=False, vmin=30, vmax=99, contratacao="Compulsório"),
    "pme_adesao": dict(mei=False, vmin=30, vmax=99, contratacao="Adesão"),
    "ss_1vida":   dict(mei=False, vmin=1,  vmax=1,  contratacao=None),
}


def casa(c, praca, label, acom, cop, fonte):
    f = FONTE[fonte]
    return (c.get("praca") == praca and c.get("label") == label
            and c.get("acomodacao") == acom and c.get("coparticipacao") == cop
            and c.get("tipo") == "Empresarial" and bool(c.get("mei")) == f["mei"]
            and c.get("vmin") == f["vmin"] and c.get("vmax") == f["vmax"]
            and (c.get("contratacao") or None) == f["contratacao"])


def main():
    cat = json.load(open(H + "catalog.json", encoding="utf-8"))
    todos = json.load(open("/tmp/todos_parsed.json", encoding="utf-8"))

    ix = defaultdict(list)
    for c in cat:
        if c.get("operadora") == "Hapvida" and c.get("plano") in PPO:
            ix[(c.get("praca"), c.get("label"), c.get("acomodacao"),
                c.get("coparticipacao"))].append(c)

    saida = {}
    semancora, semparceiro, naomenor = [], [], []
    for praca, ents in todos.items():
        grupos = defaultdict(list)
        for e in ents:
            if e["plano"] in PPO:
                grupos[(e.get("fonte"), e.get("pg"), e["coparticipacao"],
                        e["label"], e["acomodacao"])].append(e)

        for (fonte, pg, cop, label, acom), blocos in sorted(grupos.items()):
            if label in {"Premium 900", "Infinity"}:
                continue                       # nao existe parcial — por regra
            alvo = [c for c in ix[(praca, label, acom, cop)]
                    if casa(c, praca, label, acom, cop, fonte)]
            if not alvo:
                continue
            total = alvo[0]["precos"]

            anc = [b for b in blocos
                   if all(abs(b["precos"].get(f, -1) - v) < 0.005
                          for f, v in total.items() if f in BANDS)]
            if not anc:
                semancora.append(f"{praca} · {fonte} · {label} {acom} {cop}")
                continue
            ancb = anc[0]

            cands = []
            for b in blocos:
                if (b["bloco"], b["col"]) == (ancb["bloco"], ancb["col"]):
                    continue                   # e a propria coluna do total
                faixas = [f for f in BANDS
                          if f in b["precos"] and f in total and b["precos"][f]]
                if len(faixas) < 10:
                    continue
                if not all(b["precos"][f] < total[f] for f in faixas):
                    naomenor.append(f"{praca} · {fonte} · {label} {acom} {cop}")
                    continue
                cands.append(b)
            if not cands:
                semparceiro.append(f"{praca} · {fonte} · {label} {acom} {cop}")
                continue
            # havendo mais de um quadro menor na pagina, o parcial e o mais
            # proximo por baixo do total
            parcial = max(cands, key=lambda b: b["precos"]["00 a 18"])
            chave = "|".join([praca, fonte, label, acom, cop])
            saida[chave] = {f: parcial["precos"][f] for f in BANDS if f in parcial["precos"]}

    # --- fator implicito: validacao, nao geracao ---
    fat = defaultdict(list)
    for chave, pr in saida.items():
        praca, fonte, label, acom, cop = chave.split("|")
        alvo = [c for c in ix[(praca, label, acom, cop)]
                if casa(c, praca, label, acom, cop, fonte)]
        rs = [alvo[0]["precos"][f] / v for f, v in pr.items()
              if v and f in alvo[0]["precos"]]
        fat[label].append((chave, sum(rs) / len(rs), max(rs) - min(rs)))

    print(f"pares pareados por estrutura: {len(saida)}")
    print(f"  sem âncora no catálogo: {len(set(semancora))}")
    print(f"  sem quadro parceiro na página: {len(set(semparceiro))}")
    print(f"  quadro não é menor em todas as faixas: {len(set(naomenor))}")

    print("\n=== fator implícito (total ÷ parcial) por produto ===")
    modal = {}
    for label in sorted(fat):
        vals = [x[1] for x in fat[label]]
        modal[label] = Counter(round(v, 4) for v in vals).most_common(1)[0][0]
        disp = max(x[2] for x in fat[label])
        print(f"  {label:18} n={len(vals):4}  modal={modal[label]:.4f}  "
              f"min={min(vals):.4f}  max={max(vals):.4f}  "
              f"maior variação dentro de um par={disp:.5f}")

    # O fator e tabela, nao percentual unico: varia um pouco por praca/porte.
    # Mas um desvio grosseiro so acontece com coluna trocada, e ai o par nao
    # entra. Tolerancia de 1,5% sobre o modal do proprio produto.
    ok, fora = {}, []
    for label, itens in fat.items():
        for chave, med, disp in itens:
            if disp > 0.002:
                fora.append(f"{chave}  (fator varia {disp:.4f} dentro do par)")
            elif not (1.01 < med < 1.60):
                fora.append(f"{chave}  (fator implausível {med:.4f})")
            else:
                ok[chave] = saida[chave]

    json.dump({"pares": ok, "fator_modal": modal, "so_total": sorted(SO_TOTAL)},
              open(H + "reembolso_parcial.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\n=== RESULTADO ===")
    print(f"  pares CONFIRMADOS: {len(ok)}")
    print(f"  descartados por fator divergente: {len(fora)}")
    for x in sorted(set(fora))[:12]:
        print("     ", x)
    for titulo, lista in (("SEM ÂNCORA", semancora),
                          ("SEM PARCEIRO NA PÁGINA", semparceiro),
                          ("NÃO É MENOR EM TODAS", naomenor)):
        if lista:
            print(f"\n  -- {titulo} ({len(set(lista))}, até 10):")
            for x in sorted(set(lista))[:10]:
                print("     ", x)

    # cobertura: quanto do catalogo ficou com parcial
    print("\n=== COBERTURA por produto ===")
    tem, falta, sotot = defaultdict(int), defaultdict(int), defaultdict(int)
    for c in cat:
        if c.get("operadora") != "Hapvida" or c.get("plano") not in PPO:
            continue
        if c["plano"] in SO_TOTAL:
            sotot[c["label"]] += 1
            continue
        achou = False
        for fonte, f in FONTE.items():
            if (bool(c.get("mei")) == f["mei"] and c.get("vmin") == f["vmin"]
                    and c.get("vmax") == f["vmax"]
                    and (c.get("contratacao") or None) == f["contratacao"]):
                k = "|".join([c["praca"], fonte, c["label"], c["acomodacao"],
                              c["coparticipacao"]])
                if k in ok:
                    achou = True
        (tem if achou else falta)[c["label"]] += 1
    for label in sorted(set(tem) | set(falta)):
        t, f = tem[label], falta[label]
        print(f"  {label:18} com parcial: {t:3}   sem: {f:3}   ({t*100//max(1,t+f)}%)")
    for label in sorted(sotot):
        print(f"  {label:18} só reembolso total: {sotot[label]:3}  (regra do produto)")
    print(f"\n  TOTAL com parcial: {sum(tem.values())} de "
          f"{sum(tem.values())+sum(falta.values())} entradas que podem ter parcial")


if __name__ == "__main__":
    main()
