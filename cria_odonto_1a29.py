#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cria o produto "+ Odonto" para 1 a 29 vidas no Empresarial Hapvida.

O PEDIDO (21/10/2026): "nos produtos de 01 a 29 vidas para a regiao Hapvida nao
esta aparecendo os valores com odonto". O vendedor escolhia "Nosso Plano +
Odonto" e levava "requer 30-99 vidas".

POR QUE NAO EXISTIA, e por que nao era bug de carga: no PME 30-99 a tabela traz
uma COLUNA propria para quem leva odonto, marcada com asterisco no codigo
interno (39936* ao lado de 21223) -- ali o preco MEDICO e abatido, entao sao
dois produtos e duas colunas. No Super Simples 1-29 nao ha asterisco: o preco
medico e o mesmo com ou sem odonto, e o dental entra por fora, pelo quadro
ODONTOLOGIA da propria pagina, a R$ 23,25 por vida ("Valor Promocional quando
beneficiario adquire, no ato da contratacao, um plano medico-hospitalar") e em
contrato separado, como a propria tabela diz na OBS.

Ou seja: o produto combinado EXISTE e e vendido -- so nao ganha coluna propria
porque nao ha o que descontar. As entradas criadas aqui refletem isso:

  - precos: OS MESMOS da entrada sem odonto (copia exata, sem desconto);
  - rotulo: "<plano> + Odonto", que e como o vendedor ja escolhe em 30-99;
  - o valor dental NAO entra nos precos -- entra pelo odonto.json, somado por
    vida pelo odontoVal(), e o folder ja mostra "Plano de saude" +
    "Plano odontologico" = mensalidade.

So entram pracas que tem valor dental carregado para o porte 1-29; praca sem
valor nao ganha produto que o vendedor nao conseguiria cotar.

Ensaio por padrao; grava so com --gravar (backup com carimbo de hora).
"""
import collections, copy, json, os, shutil, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(AQUI, "catalog.json")
ODO = os.path.join(AQUI, "odonto.json")


def fam(e):
    return "Ambulatorial" if e["acomodacao"] == "Ambulatorial" else "Hospitalar"


def main():
    cat = json.load(open(CAT, encoding="utf-8"))
    odo = json.load(open(ODO, encoding="utf-8"))

    def val(e):
        """None = praca sem valor carregado. 0.0 = odonto GRATUITO, que e preco.

        Nas pracas NDI o quadro traz VALOR PROMO R$ 0,00 -- o odonto sai de
        graca junto do medico. Tratar isso como 'sem valor' tirava justamente
        SP/RMSP, Santos, Campinas e o Rio da criacao do produto."""
        d = ((odo.get(e["praca"], {}).get("Empresarial", {})
              .get("1-29", {})).get(fam(e)) or {})
        return d.get("promo") if "promo" in d else None

    base = [e for e in cat
            if e.get("operadora") == "Hapvida"
            and e.get("tipo") == "Empresarial"
            and not e.get("contratacao")
            and e.get("vmax") and e["vmax"] <= 29
            and " + Odonto" not in e["label"]]

    ja = {(e.get("praca"), e["label"], e["acomodacao"], e["coparticipacao"],
           e.get("vmin"), e.get("vmax"), bool(e.get("mei"))) for e in cat}

    criar, sem_valor = [], []
    for e in base:
        k = (e.get("praca"), e["label"] + " + Odonto", e["acomodacao"],
             e["coparticipacao"], e.get("vmin"), e.get("vmax"), bool(e.get("mei")))
        if k in ja:
            continue
        if val(e) is None:
            sem_valor.append(e); continue
        criar.append(e)

    print("entradas Hapvida Empresarial de 1 a 29 vidas: %d" % len(base))
    print("a criar com odonto: %d" % len(criar))
    print("sem valor dental na praça (ficam de fora): %d" % len(sem_valor))
    if sem_valor:
        for p, q in collections.Counter(e["praca"] for e in sem_valor).most_common():
            print("   %-28s %d" % (p, q))

    print("\npor praça (amostra):")
    cont = collections.Counter(e["praca"] for e in criar)
    for p, q in list(sorted(cont.items()))[:6]:
        print("   %-28s %d" % (p, q))
    print("   ... %d praças no total" % len(cont))

    erros = []
    print("\ntravas:")

    print("  1. só Hapvida/Empresarial, porte até 29 vidas, sem Adesão/Compulsório")
    if any(e["operadora"] != "Hapvida" or e.get("tipo") != "Empresarial"
           or e.get("contratacao") or e["vmax"] > 29 for e in criar):
        erros.append("entrada fora do escopo")

    print("  2. o preço médico é cópia exata do plano sem odonto (a tabela não desconta)")

    print("  3. nenhuma duplica entrada que já exista")
    novas_k = [(e.get("praca"), e["label"] + " + Odonto", e["acomodacao"],
                e["coparticipacao"], e.get("vmin"), e.get("vmax"), bool(e.get("mei")))
               for e in criar]
    if len(set(novas_k)) != len(novas_k):
        erros.append("o próprio lote tem chave repetida")
    if set(novas_k) & ja:
        erros.append("uma chave criada já existe no catálogo")

    print("  4. toda entrada criada tem valor dental para cotar")
    if any(val(e) is None for e in criar):
        erros.append("entrada criada sem valor dental")

    if erros:
        print("\n" + "!" * 72)
        for x in erros: print("!! " + x)
        print("!! NADA GRAVADO")
        return 1

    if "--gravar" not in sys.argv:
        print("\n(ensaio — nada gravado. Rode com --gravar.)")
        return 0

    bak = CAT + ".bak-odo29-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CAT, bak)
    pid = max(e["id"] for e in cat)
    for e in criar:
        pid += 1
        n = copy.deepcopy(e)
        n["label"] = e["label"] + " + Odonto"
        n["id"] = pid
        cat.append(n)
    json.dump(cat, open(CAT, "w"), ensure_ascii=False)
    print("\ngravado: %d entradas criadas, catálogo agora com %d" % (len(criar), len(cat)))
    print("backup: " + bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
