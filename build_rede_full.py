# -*- coding: utf-8 -*-
"""Cotador HapOn V4 — resumo de rede fiel ao Dash Rede Full.

Ate a V3 o resumo de rede do folder saia do rede.json, uma base curada a mao,
focada em RMSP e usada sobretudo para o comparativo com concorrente. Resultado:
quem cotava Jundiai ou Recife levava no PDF a rede da Grande Sao Paulo, e
laboratorio nao aparecia em lugar nenhum.

Aqui a rede dos produtos Hapvida/NDI/Clinipam/CCG passa a vir do MESMO arquivo
que alimenta o Dash Rede Full (~/rede-full/rede_data.json), com:

  - filtro pela praca cotada (cidade + regiao metropolitana, raio de 30 km);
  - codigo de servico decodificado do bitmask do Dash:
        1 H  Hospital eletivo
        2 PS Pronto-socorro
        4 M  Maternidade
        8 C  Consultorios/clinicas   (nao vai para a tabela, so conta no rodape)
       16 L  Laboratorio/SADT        <- a informacao nova pedida na V4
  - a TABELA lista so unidades com H, PS ou M, e o L entra como codigo extra
    da propria unidade (ex.: "H,PS,L");
  - como 96,8% dos hospitais tambem sao SADT, o L sozinho nao informa quase
    nada -- entao sai tambem um BLOCO de laboratorios INDEPENDENTES (SADT que
    nao e hospital), que e o que o cliente de fato pergunta e que ate a V3
    nunca apareceu no folder.

Recorte geografico: cidade + regiao metropolitana da praca. Como em 10 das 464
combinacoes isso zerava a tabela (Smart Flex em Americana, Nosso Plano em Feira
de Santana e em Parauapebas), o arquivo carrega tambem os hospitais do RESTO DO
ESTADO, que o folder usa como complemento quando a praca rende pouca coisa.

O comparativo com concorrentes (aba "Rede de atendimento") continua no
rede.json: a Rede Full nao tem Amil/Bradesco/Porto/SulAmerica, e trocar so o
lado Hapvida deixaria o lado a lado com bases diferentes.

Fonte COMPLEMENTAR (12/09): o folder oficial "Destaques de Rede RMSP - HMO"
(destaques.json, gerado pelo build_destaques.py). A base do Dash nao tem varios
hospitais que esse folder lista -- Cruz Azul, Santa Izildinha, Rubem Berta,
Hospital Universitario Sao Francisco, Previna. Cada unidade do folder e casada
contra o Dash pelo nome (na mesma cidade) para NAO duplicar: se ja existe, os
bits sao somados por OR; se nao existe, entra como unidade nova.

E, por decisao comercial do usuario, os hospitais do folder tambem entram na
linha PPO (Advance 600/700, Premium 900, 900 Care, Infinity) com a UNIAO das 4
colunas HMO -- a uniao, e nao a coluna Smart Prime, porque em Suzano o Saint
Nicholas tem PS no Smart UP e nao no Smart Prime.

Saida: ~/comparativo-ppo/rede_full.json (hospitais) e rede_full_labs.json
(laboratorios; arquivo separado porque sozinho tem ~6,5 mil unidades e o
folder so precisa dele na hora de imprimir).
"""
import json, math, os, re, sys, unicodedata
from collections import defaultdict
from datetime import datetime

SRC   = os.path.expanduser("~/rede-full/rede_data.json")
CAT   = os.path.expanduser("~/comparativo-ppo/catalog.json")
OUT   = os.path.expanduser("~/comparativo-ppo/rede_full.json")
OUTL  = os.path.expanduser("~/comparativo-ppo/rede_full_labs.json")
MIN_PRACA = 15   # abaixo disso o folder completa com o resto do estado
RAIO  = 30.0   # km — "regiao metropolitana" das pracas que nao tem lista propria

def n(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().upper().strip()
    return re.sub(r"\s+", " ", s)

# --- praca -> cidades ---------------------------------------------------
# A RMSP é a única com lista fechada (é a mesma do index.html, e Santos tem
# praça própria, então fica de fora). As demais saem por raio.
RMSP = [n(x) for x in ["Arujá","Barueri","Biritiba-Mirim","Caieiras","Cajamar","Carapicuíba",
  "Cotia","Diadema","Embu das Artes","Embu-Guaçu","Ferraz de Vasconcelos","Francisco Morato",
  "Franco da Rocha","Guararema","Guarulhos","Itapecerica da Serra","Itapevi","Itaquaquecetuba",
  "Jandira","Juquitiba","Mairiporã","Mauá","Mogi das Cruzes","Osasco","Pirapora do Bom Jesus",
  "Poá","Ribeirão Pires","Rio Grande da Serra","Salesópolis","Santa Isabel","Santana de Parnaíba",
  "Santo André","São Bernardo do Campo","São Caetano do Sul","São Lourenço da Serra","São Paulo",
  "Suzano","Taboão da Serra","Vargem Grande Paulista"]]
PRACA_CIDADES_FIXAS = {"SP / RMSP": ("SP", RMSP, "SAO PAULO")}

# --- mapeamento plano do cotador -> chave de plano da Rede Full ---------
# Chaves e praças de comercialização conferidas contra o PLANS de
# ~/rede-full/build_rede.py (é a mesma tabela que gerou o rede_data.json).
NE_CAPS = [n(x) for x in ["Juazeiro do Norte","Fortaleza","Maceió","Mossoró","Natal",
                          "João Pessoa","Campina Grande","Recife","São Luís","Salvador"]]
# Bahia sem praça própria na Rede Full cai na mesma rede do Nordeste.
NE_EXTRA = [n(x) for x in ["Alagoinhas","Camaçari","Feira de Santana"]]

def _amb(acom): return acom == "Ambulatorial"
def _apto(acom): return acom == "Apartamento"

# planos com chave única, independente de praça (produtos NDI compartilhados)
FIXOS = {
    "600":                  lambda a, c: "A6A" if _apto(a) else "A6E",
    "700":                  lambda a, c: "A7A" if _apto(a) else "A7E",
    "900":                  lambda a, c: "P9A",
    "900 Care":             lambda a, c: "P9CA",
    "Infinity":             lambda a, c: "I1A",
    "Smart Prime":          lambda a, c: "SPRA" if _apto(a) else "SPRE",
    "Smart UP":             lambda a, c: "SUP",
    "Smart Flex":           lambda a, c: "SFX",
    "Smart 300":            lambda a, c: "S3E",
    "Smart 500":            lambda a, c: "S5A" if _apto(a) else "S5E",
    "Smart 200 Rio":        lambda a, c: "S2E",
    "Smart Rio":            lambda a, c: "SMR",
    "Nosso Médico RMSP":    lambda a, c: "NMRMSP",
    "Pleno Vale do Paraíba":lambda a, c: "PLV",
    "Adapt 300 Estadual":   lambda a, c: "A3E",
    "Adapt 300 Sul":        lambda a, c: "A3S",
    "Adapt 500 Estadual":   lambda a, c: "A5E",
    "Personal UP":          lambda a, c: "PUP",
    "Nosso Plano Municipal":lambda a, c: "NPMT",
    "Nosso Plano Grupo Municípios": lambda a, c: "NPGMS" if _amb(a) else "NPGM",
    "Pop":                  lambda a, c: "CPOP",
    "Pop Estadual":         lambda a, c: "CPE",
    "Pop Vale dos Sinos":   lambda a, c: "CPV",
    "Mix":                  lambda a, c: "MIX",
}

NOSSO_MEDICO = {
    "BELO HORIZONTE":"NMB", "UBERLANDIA":"NMI", "UBERABA":"NMI", "BRASILIA":"NMDF",
    "GOIANIA":"NMGO", "ANAPOLIS":"NMGO", "BELEM":"NMBE", "MANAUS":"NMMA", "JOINVILLE":"NMJO",
    "SALVADOR":"NMSSA", "RECIFE":"NMRE", "MACEIO":"NMMC", "JUAZEIRO DO NORTE":"NMJZ",
    "JOAO PESSOA":"NMJP", "ARACAJU":"NMAJ", "SAO LUIS":"NMSL", "MOSSORO":"NMMO",
    "NATAL":"NMNA", "TERESINA":"NMTE", "ARARAQUARA":"NMAR", "BAURU":"NMBA", "FRANCA":"NMFR",
    "LINS":"NMLS", "RIBEIRAO PRETO":"NMRP", "SAO JOSE DOS CAMPOS":"NMSJ",
    "SERTAOZINHO":"NMST", "LIMEIRA":"NMLM", "SOROCABA":"NMSO", "JUNDIAI":"NMJU",
    "CAMPINAS":"NMCA", "AMERICANA":"NMAM", "CURITIBA":"NMC", "LONDRINA":"NML",
    "MARINGA":"NMM", "BALNEARIO CAMBORIU":"NMBC",
    "PORTO ALEGRE":"CNM", "CANOAS":"CNM", "NOVO HAMBURGO":"CNM", "SAO LEOPOLDO":"CNM",
}

PLENO = {
    "ARARAQUARA":"PLAS", "SAO CARLOS":"PLAS", "RIBEIRAO PRETO":"PLRP", "SERTAOZINHO":"PLRP",
    "BAURU":"PLBA", "FRANCA":"PLFR",
    "JABOTICABAL":"PLIN", "BARRETOS":"PLIN", "MARILIA":"PLIN", "PIRACICABA":"PLIN",
    "PIRASSUNUNGA":"PLIN", "LINS":"PLIN",
    "CAMPO GRANDE":"PLECO", "DOURADOS":"PLECO", "TRES LAGOAS":"PLECO", "CUIABA":"PLECO",
    "RONDONOPOLIS":"PLECO", "QUIRINOPOLIS":"PLECO", "RIO VERDE":"PLECO",
    "CURITIBA":"PLE", "LONDRINA":"PLE", "BALNEARIO CAMBORIU":"PLE",
    "CAMPINAS":"PLC", "SOROCABA":"PLS", "JUNDIAI":"PLJ",
}

INTEGRADO = {
    "JABOTICABAL":"INTSP", "BARRETOS":"INTSP", "MARILIA":"INTSP", "PIRACICABA":"INTSP",
    "PIRASSUNUNGA":"INTSP", "SAO CARLOS":"INTSP",
    "CAMPO GRANDE":"INTCO", "DOURADOS":"INTCO", "TRES LAGOAS":"INTCO", "CUIABA":"INTCO",
    "RONDONOPOLIS":"INTCO", "QUIRINOPOLIS":"INTCO", "RIO VERDE":"INTCO",
}

def nosso_plano(acom, cid, sem_obst):
    """Nosso Plano varia por praça e por acomodação (Ambulatorial = 'Sem Acomodação')."""
    a = _amb(acom)
    if cid == "BELO HORIZONTE":       return "NPBS" if a else "NPB"
    if cid == "UBERLANDIA":           return "NPSA" if a else "NPU"
    if cid == "UBERABA":              return "NPSA" if a else ("NPUA" if _apto(acom) else "NPUE")
    if cid == "BRASILIA":             return "NPDFS" if a else "NPDF"
    if cid in ("GOIANIA", "ANAPOLIS"):return "NPGO"
    if cid in ("BELEM", "MANAUS"):    return "NPBMS" if a else "NPBM"
    if cid == "JOINVILLE":            return "NPSFJS" if a else "NPSFJ"
    if cid == "PARAUAPEBAS":          return "NPPAS" if a else "NPPA"
    if cid == "ARACAJU":              return "NP2A"
    if cid == "TERESINA":             return "NPGMS" if a else "NPGM"
    if cid in NE_CAPS or cid in NE_EXTRA: return "NPNES" if a else "NPNE"
    if cid == "SAO JOSE DOS CAMPOS":  return "NPSJ"
    if cid == "LIMEIRA":              return "NPLI"
    if cid in ("ARARAQUARA","BAURU","FRANCA","LINS","RIBEIRAO PRETO","SERTAOZINHO"): return "NPISP"
    if cid == "CURITIBA":             return "NPA" if a else ("NPCL" if sem_obst else "NPCO")
    if cid == "LONDRINA":             return "NPA" if a else ("NPCL" if sem_obst else "NPLO")
    if cid == "MARINGA":              return "NPA" if a else "NPM"
    if cid == "BALNEARIO CAMBORIU":   return "NPA" if a else ("NPCL" if sem_obst else "NPBC")
    if cid in ("PORTO ALEGRE","CANOAS","NOVO HAMBURGO","SAO LEOPOLDO"): return "CNPS" if a else "CNP"
    return None

def chave(plano, label, acom, cid):
    """(plano, label, acomodação, cidade da praça) -> chave de plano da Rede Full."""
    if plano in FIXOS:      return FIXOS[plano](acom, cid)
    if plano == "Nosso Médico": return NOSSO_MEDICO.get(cid)
    if plano == "Pleno":        return PLENO.get(cid)
    if plano == "Integrado":    return INTEGRADO.get(cid)
    if plano == "Nosso Plano":  return nosso_plano(acom, cid, "s/ Obstetrícia" in (label or ""))
    return None

# --- folder Destaques de Rede RMSP (fonte complementar) -----------------
DEST = os.path.expanduser("~/comparativo-ppo/destaques.json")
PPO_KEYS = ["A6A", "A6E", "A7A", "A7E", "P9A", "P9CA", "I1A"]
HMO_COLS = ["NMRMSP", "SUP", "SFX", "SPRA"]

# O casamento automatico por sobreposicao de palavras erra feio: "Cruz Azul"
# casou com "Oswaldo Cruz" pelo token CRUZ, e "Pronto Atendimento Aruja" com
# "Hospital Ipiranga Aruja" pelo nome da cidade. Entao a regra e dupla:
#   1) casa sozinho SO quando o nome normalizado e IDENTICO (63 dos 97);
#   2) os outros 34 foram conferidos um a um contra a base e estao aqui.
# O que nao esta em nenhuma das duas entra como unidade NOVA.
ABREV = {"HOSP": "HOSPITAL", "STA": "SANTA", "STO": "SANTO", "MAT": "MATERNIDADE",
         "CLIN": "CLINICA", "CLINICAS": "CLINICA", "UNIV": "UNIVERSITARIO",
         "ESPEC": "ESPECIALIZADO", "MED": "MEDICO", "ATEND": "ATENDIMENTO"}
RUIDO = {"DE", "DA", "DO", "DOS", "DAS", "E", "A", "O"}

def _tok(s):
    t = re.sub(r"[^A-Z0-9 ]", " ", n(s)).split()
    return frozenset(ABREV.get(w, w) for w in t if w not in RUIDO)

# (nome no folder, cidade) -> nome na base do Dash. Conferido a mao em 12/09.
CASAR = {
    ("Hospital São Francisco Americana", "AMERICANA"): "HOSP SAO FRANCISCO AMER",
    ("CEMA Hospital - Barueri", "BARUERI"): "CEMA HOSP ESPEC",
    ("Santa Casa de Bragança Paulista", "BRAGANCA PAULISTA"): "SANTA CASA BRAGANCA",
    ("Hospital e Maternidade Celso Pierro", "CAMPINAS"): "HOSPITAL E MATERNIDADE CELSO P",
    ("Hospital Madre Theodora Campinas", "CAMPINAS"): "HOSP MADRE THEODORA",
    ("Hospital e Maternidade Keila", "GUARULHOS"): "HOSPITAL KEILA FERREIRA",
    ("Pronto Atendimento Mogi das Cruzes", "MOGI DAS CRUZES"): "PRONTO ATEND MOGI DAS CRUZES",
    ("Assoc Benef Sagrado Coração de Jesus", "MONTE MOR"): "HOSP SAGRADO CORACAO",
    ("CEMA Hospital - Osasco", "OSASCO"): "CEMA HOSP ESPEC",
    ("Pronto Atendimento Ribeirão Pires", "RIBEIRAO PIRES"): "PRONTO ATEND RIBEIRAO PIRES",
    ("Hospital e Maternidade Christóvão da Gama", "SANTO ANDRE"): "HOSP CHRISTOVAO DA GAMA",
    # unidade própria Hapvida em Santo André — o folder chama de "Unidade
    # Avançada", a base de "Pronto Atendimento"
    ("Unidade Avançada Santo André", "SANTO ANDRE"): "PRONTO ATENDIMENTO SANTO ANDRE",
    ("Hospital Notrecare ABC", "SAO BERNARDO DO CAMPO"): "MATERNIDADE NOTRECARE ABC",
    # único "Santa Rita" da base em SP (Vila Mariana); sem bairro no folder para
    # cruzar, mas criar uma segunda linha "Santa Rita" pareceria duplicata
    ("Casa de Saúde Santa Rita", "SAO PAULO"): "HOSPITAL SANTA RITA",
    ("Hospital Albert Sabin - Lapa", "SAO PAULO"): "HOSPITAL ALBERT SABIN",
    ("Hospital das Clínicas da FMUSP", "SAO PAULO"): "HOSPITAL DAS CLINICAS SP",
    ("Hospital Nossa Sra. Rosário", "SAO PAULO"): "HOSPITAL NOSSA SENHORA ROSARIO",
    ("Hospital Rubem Berta", "SAO PAULO"): "INSTITUTO RUBEM BERTA",
    ("Hospital Sant Patrick (Portinari)", "SAO PAULO"): "HOSP SAINT PATRICK",
    ("Pronto Atendimento Zona Sul", "SAO PAULO"): "PRONTO ATENDIMENTO ZONA SUL SP",
    ("Hospital Saint Nicholas", "SUZANO"): "HOSP SAINT NICHOLAS MEDICAL",
    ("Pronto Atendimento Taboão da Serra", "TABOAO DA SERRA"): "PRONTO ATEND TABOAO DA SERRA",
    ("Pronto Atendimento Várzea Paulista", "VARZEA PAULISTA"): "PRONTO ATEND VARZEA PAULISTA",
}
# O folder de agosto nao tem coluna de bairro, e nenhuma destas 11 unidades
# existe na base do Dash (procurei tambem entre clinicas e laboratorios) nem
# tem bairro util no rede.json. Os tres primeiros saem do rede.json, casando
# pelo nome; os oito restantes foram informados pelo usuario em 12/09.
BAIRRO_DEST = {
    # do rede.json (base curada interna)
    ("Hospital e Maternidade Cruz Azul", "SAO PAULO"): "Cambuci",
    ("Hospital Santa Izildinha", "SAO PAULO"): "São Mateus",
    # rede.json traz esta unidade como "CC NDI - São Miguel"
    ("Pronto Atendimento São Miguel", "SAO PAULO"): "São Miguel Paulista",
    # informados pelo usuario
    ("AMICO Saúde", "CAIEIRAS"): "Caieiras",
    ("Pronto Atendimento Diadema", "DIADEMA"): "Diadema",
    ("CEMA Hospital - Guarulhos", "GUARULHOS"): "Vila Itapegica",
    ("Hospital HAOC", "INDAIATUBA"): "Centro",
    ("Pronto Atendimento Nova Vida - Jandira I", "JANDIRA"): "Centro",
    ("Hospital e Maternidade BP Santo André", "SANTO ANDRE"): "Vila Bastos",
    ("CEMA Hospital - São Paulo", "SAO PAULO"): "Mooca",
    ("CEMA Hospital - Taboao", "TABOAO DA SERRA"): "Jardim Helena",
}

# conferidas e que NAO existem na base — entram como linha nova, sem duplicar
NOVAS_OK = {
    ("AMICO Saúde", "CAIEIRAS"),
    ("Pronto Atendimento Diadema", "DIADEMA"),
    ("CEMA Hospital - Guarulhos", "GUARULHOS"),
    ("Hospital HAOC", "INDAIATUBA"),
    ("Pronto Atendimento Nova Vida - Jandira I", "JANDIRA"),
    ("Hospital e Maternidade BP Santo André", "SANTO ANDRE"),
    ("CEMA Hospital - São Paulo", "SAO PAULO"),
    ("Hospital e Maternidade Cruz Azul", "SAO PAULO"),
    ("Hospital Santa Izildinha", "SAO PAULO"),
    ("Pronto Atendimento São Miguel", "SAO PAULO"),
    ("CEMA Hospital - Taboao", "TABOAO DA SERRA"),
}

def destaques(existentes):
    """Funde o folder da RMSP com a base do Dash, sem duplicar hospital."""
    if not os.path.exists(DEST):
        print("  ! destaques.json ausente — folder da RMSP não entrou")
        return []
    dest = json.load(open(DEST, encoding="utf-8"))["unidades"]
    porcidade = {}
    for u in existentes:
        if u["u"] == "SP":
            porcidade.setdefault(u["c"], []).append(u)

    novas, exato, curado, sem_regra = [], 0, 0, []
    for d in dest:
        cob = 0
        for k in HMO_COLS:
            cob |= d["p"].get(k, 0)
        planos = dict(d["p"])
        if d["p"].get("SPRA"):
            planos["SPRE"] = d["p"]["SPRA"]
        for k in PPO_KEYS:      # regra comercial 12/09: o PPO inclui a rede HMO
            planos[k] = planos.get(k, 0) | cob

        ch = (d["n"], d["c"])
        vizinhos = porcidade.get(d["c"], [])
        alvo = None
        if ch in CASAR:
            alvo = next((u for u in vizinhos if n(u["n"]) == n(CASAR[ch])), None)
            if alvo is None:
                raise SystemExit(f"de-para aponta para nome inexistente: {ch} -> {CASAR[ch]}")
            curado += 1
        elif ch in NOVAS_OK:
            pass
        else:
            alvo = next((u for u in vizinhos if _tok(u["n"]) == _tok(d["n"])), None)
            if alvo is not None:
                exato += 1
            else:
                sem_regra.append(ch)

        if alvo is not None:
            for k, m in planos.items():
                alvo["p"][k] = alvo["p"].get(k, 0) | m
        else:
            reg = {"n": d["n"], "b": BAIRRO_DEST.get(ch, ""), "c": d["c"], "u": "SP",
                   "r": "Destaques RMSP", "p": planos}
            novas.append(reg)
            porcidade.setdefault(d["c"], []).append(reg)

    if sem_regra:
        raise SystemExit("unidade do folder sem casamento exato e fora do de-para "
                         "(conferir a mão antes de publicar):\n  " +
                         "\n  ".join(f"{a} [{b}]" for a, b in sem_regra))
    sem_bairro = [f'{r["n"]} [{r["c"]}]' for r in novas if not r["b"]]
    print(f"  destaques RMSP: {len(dest)} do folder — {exato} casaram por nome idêntico, "
          f"{curado} pelo de-para conferido, {len(novas)} entraram como novas")
    if sem_bairro:
        print(f"  ! sem bairro ({len(sem_bairro)}), sai '—' no folder: " + "; ".join(sem_bairro))
    return novas


# --- região de SP (agrupamento do folder) -------------------------------
# O folder antigo abria a rede de SP por ZONA (Centro, Zona Sul, Zona Oeste,
# Zona Norte, Zona Leste, ABCD, Grande SP, Grande SP - Sul, Interior e depois
# as demais em ordem alfabética). O Dash só tem cidade e bairro, então a região
# vem do rede.json, que carrega esse campo, em camadas:
#   1) mesmo nome de unidade (e mesmo lado: capital x cidade)  — o mais preciso
#   2) bairro, para a capital, por maioria (o rede.json tem 14 bairros com mais
#      de uma zona, todos com maioria clara na Zona Leste)
#   3) cidade, fora da capital
#   4) o que sobrar em SP é Interior — são cidades pequenas (Viradouro,
#      Buritama, Ilha Solteira...) que nenhuma outra região reivindica
REDE = os.path.expanduser("~/comparativo-ppo/rede.json")

# seis unidades da capital que nenhuma camada resolve. Decididas pelo ENDEREÇO
# da própria base do Dash, não por palpite:
ZONA_MANUAL = {
    # R Verbo Divino 290, Chácara Santo Antônio
    "SANTA ISABELLA": "São Paulo - Zona Sul",
    # R Dr Galvão Guimarães, Jd Santa Adélia (São Mateus)
    "MASTER CLIN": "São Paulo - Zona Leste",
    # R Rafael Monteiro Valeiro, Jd Tuá (Itaim Paulista)
    "HOSP MAT 8 DE MAIO": "São Paulo - Zona Leste",
    # Av Raimundo Pereira de Magalhães 1257, Pirituba. ⚠ a coordenada do Dash
    # para esta unidade é um fallback arredondado e aponta para o sul — o
    # endereço é que vale
    "HOSPITAL PREVINA PLENA SAUDE": "São Paulo - Zona Norte",
    # R Jaguaribe 144, Vila Buarque
    "SANTA CASA DE MISERICORDIA SP": "São Paulo - Centro",
    # Av Nossa Senhora do Sabará 2375, Vila Santana
    "HOSP MAT VIDAS": "São Paulo - Zona Sul",
}
# as 11 unidades que vieram só do folder de agosto não estão no rede.json
ZONA_DESTAQUES = {
    "Hospital e Maternidade Cruz Azul": "São Paulo - Centro",
    "Hospital Santa Izildinha": "São Paulo - Zona Leste",
    "Pronto Atendimento São Miguel": "São Paulo - Zona Leste",
    "CEMA Hospital - São Paulo": "São Paulo - Zona Leste",
    "AMICO Saúde": "Grande SP",
    "Pronto Atendimento Diadema": "ABCD",
    "CEMA Hospital - Guarulhos": "Grande SP",
    "Hospital HAOC": "Campinas e Região",
    "Pronto Atendimento Nova Vida - Jandira I": "Grande SP",
    "Hospital e Maternidade BP Santo André": "ABCD",
    "CEMA Hospital - Taboao": "Grande SP",
}

def _maioria(c):
    return c.most_common(1)[0][0] if c else None

def marca_regiao(unidades):
    """Preenche o campo 'g' (região) das unidades de SP."""
    if not os.path.exists(REDE):
        print("  ! rede.json ausente — folder de SP fica agrupado por cidade")
        return
    from collections import Counter, defaultdict
    R = json.load(open(REDE, encoding="utf-8"))
    por_nome_cap, por_nome_cid = defaultdict(Counter), defaultdict(Counter)
    por_bairro, por_cidade = defaultdict(Counter), defaultdict(Counter)
    for v in R.values():
        for h in v["hospitais"]:
            r = h.get("regiao") or ""
            if not r:
                continue
            nome, bairro = n(h["nome"]), n(h["bairro"])
            if r.startswith("São Paulo -"):
                por_nome_cap[nome][r] += 1
                por_bairro[bairro][r] += 1
            else:
                # fora da capital o campo "bairro" do rede.json traz a cidade
                por_nome_cid[(nome, bairro)][r] += 1
                por_cidade[bairro][r] += 1

    cont = Counter()
    for u in unidades:
        if u["u"] != "SP":
            continue
        nome = n(u["n"])
        capital = u["c"] == "SAO PAULO"
        g = None
        if u.get("r") == "Destaques RMSP":
            g = ZONA_DESTAQUES.get(u["n"]); cont["folder"] += 1 if g else 0
        if not g and capital and nome in ZONA_MANUAL:
            g = ZONA_MANUAL[nome]; cont["endereço"] += 1
        if not g:
            g = _maioria(por_nome_cap[nome] if capital else por_nome_cid[(nome, u["c"])])
            if g: cont["nome"] += 1
        if not g and capital:
            for b in (n(x) for x in u["b"].split(" / ") if x):
                g = _maioria(por_bairro.get(b))
                if g: cont["bairro"] += 1; break
        if not g and not capital:
            g = _maioria(por_cidade.get(u["c"]))
            if g: cont["cidade"] += 1
        if not g:
            g = "Interior"; cont["Interior (resto de SP)"] += 1
        u["g"] = g
    print("  região de SP: " + ", ".join(f"{v} por {k}" for k, v in cont.most_common()))


# --- geografia ----------------------------------------------------------
def km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    x = math.sin((la2-la1)*p/2)**2 + math.cos(la1*p)*math.cos(la2*p)*math.sin((lo2-lo1)*p/2)**2
    return 12742 * math.asin(min(1, math.sqrt(x)))

def main():
    data = json.load(open(SRC, encoding="utf-8"))
    rows = data["rows"]
    cat  = json.load(open(CAT, encoding="utf-8"))

    # centróide de cada cidade a partir das próprias unidades da Rede Full
    pts = defaultdict(list)
    for r in rows:
        if r.get("ll"): pts[(r["uf"], n(r["ci"]))].append(r["ll"])
    cent = {k: (sum(p[0] for p in v)/len(v), sum(p[1] for p in v)/len(v)) for k, v in pts.items()}

    # praça -> (uf, [cidades])
    pracas = {}
    for p in sorted({c.get("praca") or "SP / RMSP" for c in cat}):
        if p in PRACA_CIDADES_FIXAS:
            pracas[p] = PRACA_CIDADES_FIXAS[p]; continue
        m = re.match(r"^(.*?)\s*-\s*([A-Z]{2})$", p)
        if not m:
            print(f"  ! praça sem UF, ignorada: {p}"); continue
        cid, uf = n(m.group(1)), m.group(2)
        base = cent.get((uf, cid))
        if not base:
            pracas[p] = (uf, [cid], cid); continue
        viz = sorted(c for (u, c), ll in cent.items() if u == uf and km(base, ll) <= RAIO)
        pracas[p] = (uf, viz, cid)

    # praça+plano+acomodação -> chave da Rede Full (só o que o catálogo vende)
    planos, faltando = {}, defaultdict(set)
    for c in cat:
        if c["operadora"] != "Hapvida": continue
        p = c.get("praca") or "SP / RMSP"
        cid = "SAO PAULO" if p == "SP / RMSP" else n(re.sub(r"\s*-\s*[A-Z]{2}$", "", p))
        k = chave(c["plano"], c.get("label"), c["acomodacao"], cid)
        obst = "SO" if "s/ Obstetrícia" in (c.get("label") or "") else "CO"
        idx = f'{p}|{c["plano"]}|{c["acomodacao"]}|{obst}'
        if k: planos[idx] = k
        else: faltando[c["plano"]].add(p)

    usadas = set(planos.values())
    cidades_ok = {(uf, c) for uf, lst, _ in pracas.values() for c in lst}
    ufs_ok = {uf for uf, _, _ in pracas.values()}

    # HOSPITAIS: unidade com H/PS/M em alguma chave vendida. Entram os do estado
    # inteiro — o folder mostra primeiro os da praça e só desce para o resto do
    # estado quando a praça rende menos de MIN_PRACA unidades.
    # LABORATÓRIOS: SADT que não é hospital, só nas cidades da praça (o bloco é
    # sobre onde o cliente coleta exame, não faz sentido varrer o estado).
    unidades, labs = [], []
    for r in rows:
        if r["uf"] not in ufs_ok: continue
        pl = {k: v for k, v in r["pl"].items() if k in usadas}
        if not pl: continue
        reg = {"n": r["no"], "b": r.get("ba") or "", "c": n(r["ci"]),
               "u": r["uf"], "r": r.get("re") or "", "p": pl}
        if any(v & 7 for v in pl.values()):
            unidades.append(reg)
        elif (r["uf"], n(r["ci"])) in cidades_ok and any(v & 16 for v in pl.values()):
            labs.append(reg)
    # ---- folder "Destaques de Rede RMSP" entra como complemento ----
    unidades += destaques(unidades)

    # A base do Dash traz uma linha por ENDEREÇO: o Hospital e Maternidade
    # Ipiranga de Arujá, por exemplo, aparece duas vezes (nº 90 e nº 208), cada
    # uma com parte dos serviços. No Dash isso é detalhe de unidade; num folder
    # de proposta vira o mesmo hospital repetido com informação pela metade.
    # Aqui as linhas de mesma (unidade, bairro, cidade, UF) viram uma só, com os
    # bits somados por OR.
    def funde(lst):
        """Uma linha por (unidade, cidade) — o folder do cliente não repete hospital.

        A base traz uma linha por ENDEREÇO, o que gera dois tipos de repetição:
        o mesmo prédio em números diferentes (H. e Mat. Ipiranga de Arujá, nº 90
        e nº 208) e filiais do mesmo nome em bairros diferentes (H. Carlos
        Chagas no Centro e na Vila Vicentina, em Guarulhos). Nos dois casos a
        cobertura vem PARTIDA entre as linhas — o H. Evangélico de BH aparece
        com H numa e PS na outra. Fundindo por nome+cidade, com OR dos bits, o
        vendedor vê a cobertura real. Os bairros distintos são preservados na
        própria célula, para não esconder que são endereços diferentes."""
        ix, out = {}, []
        for r in lst:
            k = (r["u"], r["c"], r["n"])
            if k in ix:
                alvo = ix[k]
                for pk, m in r["p"].items(): alvo["p"][pk] = alvo["p"].get(pk, 0) | m
                if r["r"] == "Própria": alvo["r"] = "Própria"
                if r["b"] and r["b"] not in alvo["_bs"]:
                    alvo["_bs"].append(r["b"])
            else:
                r["_bs"] = [r["b"]] if r["b"] else []
                ix[k] = r; out.append(r)
        for r in out:
            r["b"] = " / ".join(r.pop("_bs"))
        return out
    unidades, labs = funde(unidades), funde(labs)
    marca_regiao(unidades)
    for lst in (unidades, labs):
        lst.sort(key=lambda x: (x["u"], x["c"], x["b"], x["n"]))

    out = {
        "meta": {
            "gerado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fonte": "Dash Rede Full (rede-full/rede_data.json)",
            "raio_km": RAIO,
            "min_praca": MIN_PRACA,
            "bits": {"1": "H", "2": "PS", "4": "M", "8": "C", "16": "L"},
            "legenda": {"H": "Hospital", "PS": "Pronto-socorro", "M": "Maternidade",
                        "C": "Consultórios/clínicas", "L": "Laboratório/SADT"},
        },
        "pracas": {p: {"uf": uf, "cidades": cids, "sede": sede}
                   for p, (uf, cids, sede) in pracas.items()},
        "planos": planos,
        "unidades": unidades,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({"meta": out["meta"], "labs": labs},
              open(OUTL, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    print(f"praças: {len(pracas)}  |  combinações plano×praça: {len(planos)}  "
          f"|  chaves Rede Full usadas: {len(usadas)}")
    print(f"{OUT}   hospitais: {len(unidades):5}  ({os.path.getsize(OUT)/1024:.0f} KB)")
    print(f"{OUTL}   laboratórios: {len(labs):5}  ({os.path.getsize(OUTL)/1024:.0f} KB)")
    if faltando:
        print("\n!! sem chave na Rede Full:")
        for p, prs in sorted(faltando.items()):
            print(f"   {p}: {sorted(prs)}")

if __name__ == "__main__":
    main()
