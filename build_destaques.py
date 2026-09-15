# -*- coding: utf-8 -*-
"""Le o folder "Destaques de Rede RMSP - HMO" (agosto/2026) e gera destaques.json.

Por que este arquivo existe: a base do Dash Rede Full NAO tem varios hospitais
que o folder oficial da RMSP lista -- Cruz Azul, Santa Izildinha, Rubem Berta,
Hospital Universitario Sao Francisco, Previna, entre outros. Sao ausencias reais
(zero ocorrencias em 12.480 estabelecimentos), nao questao de grafia. Entao o
folder de agosto entra como fonte COMPLEMENTAR da rede do cotador.

O PDF traz 4 colunas de produto HMO (Nosso Medico RMSP, Smart UP, Smart Flex,
Smart Prime) com codigos H / PS / M combinados por hifen ("H-M-PS") e "-" ou
"–" para sem cobertura. A leitura e por POSICAO X das palavras, nao por regex
na linha: nome de hospital e nome de cidade sao os dois multi-palavra
("Hospital e Maternidade Christovao da Gama" em "Sao Bernardo do Campo"), e
qualquer separacao por texto erra.

Nome e cidade NAO tem fronteira fixa: as duas colunas sao centralizadas, entao
"Sao Bernardo do Campo" comeca em x=290 e "Taboao da Serra" em x=306. Cortar
num x fixo partia a cidade ("Hospital Notrecare ABC Sao" + "Bernardo do Campo").
A separacao e pelo MAIOR VAO entre palavras consecutivas a esquerda das colunas
de cobertura -- o vao nome/cidade passa de 80pt, os vaos internos ficam abaixo
de 20pt.

Este arquivo e transcricao PURA do PDF: so as 4 colunas HMO que o folder tem.
A regra comercial de 12/09 -- estes hospitais tambem valem para a linha PPO --
e aplicada no build_rede_full.py, junto com o casamento contra o Dash, para
ficar num lugar so.

Saida: ~/comparativo-ppo/destaques.json
"""
import json, os, re, unicodedata
from datetime import datetime

import pdfplumber

PDF = os.path.expanduser("~/Downloads/Destaques de Rede  RMSP - HMO 21.08.26 (1).pdf")
OUT = os.path.expanduser("~/comparativo-ppo/destaques.json")

# colunas de cobertura: x fixo, medido no cabecalho da pagina 2
COBS = [("NMRMSP", 460, 560), ("SUP", 560, 630), ("SFX", 630, 710), ("SPRA", 710, 999)]
VAO_MIN = 40   # menor vao aceito como separador entre nome e cidade

SEM = {"-", "–", "—", "", "--"}


def n(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper().strip()
    return re.sub(r"\s+", " ", s)


def codigo(txt):
    """'H-M-PS' -> mascara de bits do Dash (1 H, 2 PS, 4 M)."""
    t = (txt or "").strip()
    if t in SEM:
        return 0
    m = 0
    for p in re.split(r"[-–]", t.upper()):
        p = p.strip()
        if p == "H":
            m |= 1
        elif p == "PS":
            m |= 2
        elif p == "M":
            m |= 4
    return m


def linhas_do_pdf():
    out = []
    with pdfplumber.open(PDF) as pdf:
        for pg in pdf.pages:
            linhas = {}
            for w in pg.extract_words():
                # agrupa por linha (tolerancia de 3pt no topo)
                chave = round(w["top"] / 3)
                linhas.setdefault(chave, []).append(w)
            for _, ws in sorted(linhas.items()):
                ws = sorted(ws, key=lambda x: x["x0"])
                esq = [w for w in ws if w["x0"] < COBS[0][1]]
                reg = {c: " ".join(w["text"] for w in ws if a <= w["x0"] < b)
                       for c, a, b in COBS}
                # nome | cidade: corta no maior vao entre palavras
                corte, maior = None, 0
                for i in range(1, len(esq)):
                    vao = esq[i]["x0"] - esq[i - 1]["x1"]
                    if vao > maior:
                        maior, corte = vao, i
                if corte is None or maior < VAO_MIN:
                    continue
                reg["nome"] = " ".join(w["text"] for w in esq[:corte]).strip()
                reg["cidade"] = " ".join(w["text"] for w in esq[corte:]).strip()
                if not reg["nome"] or not reg["cidade"]:
                    continue
                if not any(reg[c] for c, _, _ in COBS):
                    continue
                out.append(reg)
    return out


def main():
    regs = linhas_do_pdf()
    print(f"linhas lidas do PDF: {len(regs)}")

    unidades, indice, ignoradas, fundidas = [], {}, 0, []
    for r in regs:
        nome, cid = r["nome"], n(r["cidade"])
        planos = {}
        for k in ("NMRMSP", "SUP", "SFX", "SPRA"):
            m = codigo(r[k])
            if m:
                planos[k] = m
        if not planos:
            ignoradas += 1          # cabeçalho e rodapé caem aqui
            continue
        # duplicidade: mesma unidade na mesma cidade vira uma linha so (OR dos bits)
        ch = (n(nome), cid)
        if ch in indice:
            alvo = indice[ch]
            for k, m in planos.items():
                alvo["p"][k] = alvo["p"].get(k, 0) | m
            fundidas.append(f'{nome} ({cid})')
            continue
        reg = {"n": nome, "b": "", "c": cid, "u": "SP", "r": "Destaques RMSP", "p": planos}
        indice[ch] = reg
        unidades.append(reg)

    unidades.sort(key=lambda x: (x["c"], n(x["n"])))
    out = {
        "meta": {
            "gerado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fonte": "Destaques de Rede RMSP — HMO, vigência agosto/2026",
            "obs": ("Folder oficial da RMSP. Entra como complemento porque a base do "
                    "Rede Full não tem parte destes hospitais. A coluna Smart Prime "
                    "também vale para Smart Prime Enfermaria e para a linha PPO."),
        },
        "unidades": unidades,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"unidades: {len(unidades)}  |  linhas de cabeçalho/rodapé ignoradas: {ignoradas}")
    print(f"duplicadas fundidas: {len(fundidas)}" + ("" if not fundidas else " -> " + "; ".join(fundidas)))
    print(f"cidades: {len(set(u['c'] for u in unidades))}")
    print(f"{OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
