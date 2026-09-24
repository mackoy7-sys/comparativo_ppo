#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mescla os precos de REEMBOLSO PARCIAL no catalog.json.

Nao cria entradas novas. Cada entrada PPO que tem par conferido ganha um campo
`pr2` com os 10 precos do reembolso parcial; `precos` continua sendo o
reembolso TOTAL, que e o que o cotador ja usava. Assim nenhum filtro do
index.html muda de resultado e nao ha duas entradas disputando a mesma
combinacao — o seletor so troca de qual conjunto ler.

Onde nao ha par conferido, o campo simplesmente nao existe, e a UI nao oferece
a opcao. Premium 900 e Infinity nunca terao: nao ha reembolso parcial para
esses produtos (regra do produto, conferida nos 5 PDFs e 9 pracas).

Travas antes de gravar:
  1. o parcial tem de ser menor que o total em TODAS as 10 faixas;
  2. a curva de faixa etaria do parcial nao pode decrescer;
  3. o fator total/parcial tem de ser praticamente constante no par (<0,2%);
  4. nenhuma entrada Premium 900 / Infinity pode receber pr2.

Uso:  python3 merge_reembolso.py            (ensaio)
      python3 merge_reembolso.py --gravar
"""
import json, shutil, sys, datetime
from collections import Counter

H = "/Users/marcoscorrea/comparativo-ppo/"
BANDS = ["00 a 18", "19 a 23", "24 a 28", "29 a 33", "34 a 38",
         "39 a 43", "44 a 48", "49 a 53", "54 a 58", "59 ou mais"]
SO_TOTAL = {"900", "Infinity"}
FONTE = {
    "ss_demais":  dict(mei=False, vmin=2,  vmax=29, contratacao=None),
    "ss_mei":     dict(mei=True,  vmin=2,  vmax=29, contratacao=None),
    "pme_comp":   dict(mei=False, vmin=30, vmax=99, contratacao="Compulsório"),
    "pme_adesao": dict(mei=False, vmin=30, vmax=99, contratacao="Adesão"),
    "ss_1vida":   dict(mei=False, vmin=1,  vmax=1,  contratacao=None),
}


def main():
    gravar = "--gravar" in sys.argv
    cat = json.load(open(H + "catalog.json", encoding="utf-8"))
    pares = json.load(open(H + "reembolso_parcial.json", encoding="utf-8"))["pares"]

    ix = {}
    for i, c in enumerate(cat):
        if c.get("operadora") != "Hapvida" or c.get("tipo") != "Empresarial":
            continue
        for fonte, f in FONTE.items():
            if (bool(c.get("mei")) == f["mei"] and c.get("vmin") == f["vmin"]
                    and c.get("vmax") == f["vmax"]
                    and (c.get("contratacao") or None) == f["contratacao"]):
                ix["|".join([c["praca"], fonte, c["label"], c["acomodacao"],
                             c["coparticipacao"]])] = i

    aplicar, recusadas, semdestino = [], [], []
    for chave, pr in pares.items():
        i = ix.get(chave)
        if i is None:
            semdestino.append(chave)
            continue
        c = cat[i]
        total = c["precos"]
        if c.get("plano") in SO_TOTAL:
            recusadas.append((chave, "produto não tem reembolso parcial")); continue
        if any(b not in pr for b in BANDS):
            recusadas.append((chave, "faltam faixas")); continue
        if not all(pr[b] < total[b] - 0.004 for b in BANDS):
            recusadas.append((chave, "parcial não é menor em todas as faixas")); continue
        v = [pr[b] for b in BANDS]
        if any(v[k + 1] < v[k] - 0.005 for k in range(9)):
            recusadas.append((chave, "curva do parcial decresce")); continue
        rs = [total[b] / pr[b] for b in BANDS]
        if max(rs) - min(rs) > 0.002:
            recusadas.append((chave, f"fator varia {max(rs)-min(rs):.4f} no par")); continue
        aplicar.append((i, chave, {b: pr[b] for b in BANDS}, sum(rs) / len(rs)))

    print(f"pares no arquivo:          {len(pares)}")
    print(f"  vão para o catálogo:     {len(aplicar)}")
    print(f"  recusados pelas travas:  {len(recusadas)}")
    print(f"  sem entrada de destino:  {len(semdestino)}")
    for ch, por in recusadas[:10]:
        print(f"     !! {ch}  — {por}")

    print("\nfator total ÷ parcial, por produto e praça:")
    por = {}
    for i, chave, pr, fat in aplicar:
        por.setdefault((cat[i]["label"], cat[i]["praca"]), []).append(fat)
    for (label, praca), fs in sorted(por.items()):
        print(f"   {label:18} {praca:26} ×{sum(fs)/len(fs):.4f}  ({len(fs)} entradas)")

    if not gravar:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bkp = H + "catalog.json.bak-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(H + "catalog.json", bkp)
    for c in cat:
        c.pop("pr2", None)
    for i, chave, pr, fat in aplicar:
        cat[i]["pr2"] = pr
    json.dump(cat, open(H + "catalog.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    n = sum(1 for c in cat if "pr2" in c)
    print(f"\ngravado: {n} entradas com reembolso parcial. backup em {bkp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
