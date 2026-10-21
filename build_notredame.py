#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injeta no index.html os quadros DIFERENCIAIS e EXEMPLOS DE REEMBOLSO.

Pedido de 23/09: no folder de cotacao, quando houver produto NotreDame Saude,
entram esses dois quadros ANTES da rede de atendimento. O titulo do segundo
perde o "- PME" (o quadro vale para a cotacao, nao so para PME).

Os dados sao transcricao do material comercial da operadora (folder de
produtos). Ficam aqui, num script, e nao digitados direto no index: quando a
operadora atualizar o material, mexe-se so nesta tabela e roda de novo.

Uso: python3 build_notredame.py
"""
import json, re, sys

H = "/Users/marcoscorrea/comparativo-ppo/index.html"

# ---------------------------------------------------------------- DIFERENCIAIS
DIF_COLS = ["Advance 600", "Advance 700", "Premium 900", "Infinity 1000"]
DIF = [
    ["Aconselhamento médico telefônico", "Sim", "Sim", "Sim", "Sim"],
    ["Assistência em Viagem", "Nacional", "Nacional",
     "Nacional/Internacional USD/€ 60.000", "Nacional/Internacional USD/€ 100.000"],
    ["Check-up Titulares ¹", "-", "-", "-", "Sim"],
    ["Cirurgia Refrativa – Hipermetropia", "Até grau 6,0 ²", "Até grau 6,0 ²",
     "Até grau 6,0 ²", "Até grau 6,0 ²"],
    ["Cirurgia Refrativa – Miopia", "De grau -5,0 a -10,0 ²", "De grau -5,0 a -10,0 ²",
     "Acima do grau -3,0 ³", "Sem limite de grau ³"],
    ["Clube de Vantagens e Benefícios", "Sim", "Sim", "Sim", "Sim"],
    ["Coleta domiciliar ¹", "-", "-", "Sim ⁴", "Sim ⁴"],
    ["Consulta com Nutricionista", "Conforme Rol ANS", "Conforme Rol ANS",
     "Conforme Rol ANS", "Sem limites de sessões"],
    ["Escleroterapia de veias", "-", "-", "18 sessões ³", "25 sessões ³"],
    ["Hidroterapia", "-", "10 sessões ³", "30 sessões ³", "40 sessões ³"],
    ["Medicina Preventiva", "Sim", "Sim", "Sim", "Sim"],
    ["Programa de Imunização – Vacinas ⁴", "-", "-", "Sim", "Sim"],
    ["Reembolso de consultas e exames simples", "7 dias (úteis)", "7 dias (úteis)",
     "5 dias (úteis)", "3 dias (úteis)"],
    ["Reembolso demais procedimentos", "30 dias (corridos)", "30 dias (corridos)",
     "10 dias (úteis)", "10 dias (úteis)"],
    ["Reembolso no Exterior ⁵", "Sim", "Sim", "Sim", "Sim"],
    ["Remissão ⁶", "de 0 a 24 meses", "de 0 a 24 meses", "de 0 a 24 meses",
     "de 0 a 24 meses"],
    ["Retaguarda Hospital Albert Einstein", "-", "-", "-", "Sim"],
    ["Retaguarda Hospital Sírio Libanês", "-", "-", "-", "Sim"],
    ["RPG com justificativa médica", "12 sessões ³", "12 sessões ³",
     "30 sessões ³", "40 sessões ³"],
    ["Teste de Incompatibilidade alimentar", "-", "-", "-", "Sim ⁷"],
    ["Transplantes (Rol)",
     "Rim, Córnea, Medula (autólogo e heterólogo) e Transplante de fígado",
     "Rim, Córnea, Medula (autólogo e heterólogo) e Transplante de fígado",
     "Rim, Córnea, Medula (autólogo e heterólogo) e Transplante de fígado",
     "Rim, Córnea, Medula (autólogo e heterólogo) e Transplante de fígado"],
    ["Transplantes (Extra-Rol)", "-", "-", "Coração e Pulmão ¹",
     "Coração, Pâncreas e Pulmão ¹"],
]
DIF_NOTAS = (
    "1) Somente nos prestadores indicados pela NotreDame Saúde. Disponível em São Paulo "
    "e Rio de Janeiro. | 2) Com ou sem astigmatismo associado com grau até 4,0. | "
    "3) São Paulo e Rio de Janeiro: atendimento na rede de prestadores indicada ou por "
    "reembolso. Demais praças: atendimento por reembolso. | 4) Coleta e Vacina "
    "Domiciliar são serviços oferecidos por prestadores indicados pela NotreDame Saúde. "
    "Disponível em São Paulo e Rio de Janeiro. Cobertura de Vacinas conforme Calendário "
    "do Ministério da Saúde. | 5) Reembolso limitado ao valor do plano contratado, "
    "conforme regras e condições gerais. | 6) Contratação opcional."
)

# ---------------------------------------------------- EXEMPLOS DE REEMBOLSO
# cada coluna: (produto, detalhe). "RC" no material da operadora = reembolso parcial.
REEMB_COLS = [
    ["Advance 600", "reemb. total · Enf/Apt"],
    ["Advance 600 RC", "reemb. parcial · Enf/Apt"],
    ["Advance 700", "reemb. total · Enf/Apt"],
    ["Advance 700 RC", "reemb. parcial · Enf/Apt"],
    ["Premium 900", "reemb. total · Apto"],
    ["Premium 900", "reemb. parcial · Apto"],
    ["Infinity 1000", "reemb. total · Apto"],
]
REEMB = [
    {"l": "Consulta em consultório (no horário normal ou preestabelecido)",
     "v": ["90,00", "90,00", "96,00", "96,00", "240,00", "240,00", "435,00"]},
    {"g": "Exames e terapias"},
    {"l": "Escleroterapia de Veias – por sessão",
     "v": ["-", "-", "-", "-", "121,82", "-", "203,04"]},
    {"l": "Acupuntura por sessão",
     "v": ["67,87", "-", "67,87", "-", "106,46", "-", "151,00"]},
    {"l": "Colesterol total – pesquisa e/ou dosagem",
     "v": ["4,20", "-", "4,20", "-", "4,41", "-", "4,61"]},
    {"l": "Consulta ambulatorial por nutricionista",
     "v": ["19,03", "-", "19,03", "-", "60,88", "-", "101,47"]},
    {"l": "ECG convencional de até 12 derivações",
     "v": ["26,98", "-", "26,98", "-", "68,84", "-", "109,43"]},
    {"l": "Endoscopia digestiva alta",
     "v": ["274,80", "-", "274,80", "-", "451,47", "-", "628,14"]},
    {"l": "Fisioterapia",
     "v": ["19,03", "-", "19,03", "-", "60,88", "-", "101,47"]},
    {"l": "Hemograma com contagem de plaquetas ou frações (eritrograma, leucograma, plaquetas)",
     "v": ["9,32", "-", "9,32", "-", "9,53", "-", "9,73"]},
    {"l": "RM – Crânio (encéfalo)",
     "v": ["685,17", "-", "685,17", "-", "833,61", "-", "982,06"]},
    {"l": "RX – Tórax – 1 incidência",
     "v": ["30,35", "-", "30,35", "-", "72,20", "-", "112,79"]},
    {"l": "Reeducação Postural Global",
     "v": ["19,03", "-", "19,03", "-", "60,88", "-", "101,47"]},
    {"l": "Sessão individual ambulatorial de fonoaudiologia",
     "v": ["19,03", "-", "19,03", "-", "60,88", "-", "101,47"]},
    {"l": "Sessão de psicoterapia individual",
     "v": ["59,38", "-", "59,38", "-", "190,02", "-", "316,70"]},
    {"l": "TC – Tórax",
     "v": ["365,56", "-", "365,56", "-", "495,15", "-", "624,75"]},
    {"l": "Teste ergométrico computadorizado (inclui ECG basal convencional)",
     "v": ["132,13", "-", "132,13", "-", "215,88", "-", "297,09"]},
    {"l": "US – Transvaginal (útero, ovário, anexos e vagina)",
     "v": ["93,47", "-", "93,47", "-", "203,86", "-", "310,90"]},
    {"g": "Honorários médicos"},
    {"l": "Adenoidectomia",
     "v": ["321,98", "-", "643,96", "-", "1.609,90", "1.609,90", "3.219,79"]},
    {"l": "Apendicectomia",
     "v": ["822,09", "-", "1.644,19", "-", "4.110,47", "4.110,47", "8.220,94"]},
    {"l": "Hemorroidectomia aberta ou fechada, com ou sem esfincterotomia",
     "v": ["614,02", "-", "1.228,04", "-", "3.070,10", "3.070,10", "6.140,20"]},
    {"l": "Hérnia de disco cervical – tratamento cirúrgico",
     "v": ["1.579,57", "-", "3.159,14", "-", "7.897,85", "7.897,85", "15.795,70"]},
    {"l": "Histerectomia total – qualquer via",
     "v": ["1.389,42", "-", "2.778,83", "-", "6.947,08", "6.947,08", "13.894,16"]},
    {"l": "Instalação de marcapasso epimiocárdio temporário",
     "v": ["480,30", "-", "960,59", "-", "2.401,48", "2.401,48", "4.802,95"]},
    {"l": "Parto (via vaginal)",
     "v": ["1.000,00", "-", "2.000,00", "-", "5.000,00", "5.000,00", "9.999,99"]},
    {"l": "Parto (Cesariana)",
     "v": ["1.180,07", "-", "2.360,15", "-", "5.900,37", "5.900,37", "11.800,74"]},
    {"l": "Revascularização do miocárdio (Ponte de Safena)",
     "v": ["2.123,68", "-", "4.247,36", "-", "10.618,39", "10.618,39", "21.236,78"]},
]
REEMB_NOTAS = (
    "Valores expressos em reais (R$). A tabela completa com todos os procedimentos "
    "possíveis para reembolso (TNDI-I — Tabela NotreDame Intermédica), atualizada em "
    "conformidade com o Rol vigente, consta registrada no 1º Oficial de Registro de "
    "Títulos e Documentos e Civil de Pessoas Jurídicas da cidade de São Paulo sob "
    "nº 3583096 e publicada no Portal do Beneficiário. A TNDI-I pode ser atualizada "
    "sempre que houver alteração no Rol de Procedimentos da ANS. Os limites máximos "
    "reembolsáveis, em valor ou quantidade, observam o contrato e as diretrizes de "
    "utilização do Rol. Informações resumidas: os produtos Infinity, Premium 900, "
    "Premium 900 Care, Advance 700 e Advance 600 são regidos pelas respectivas "
    "condições gerais, que devem ser lidas antes da contratação — www.notredame.com.br"
)


# ============================ LINHA METAIS (21/10/2026) ============================
# Transcricao das duas pecas que a Diretoria enviou em 20/10: o quadro de
# diferenciais e os exemplos de reembolso (TNDI) da linha nova.
MET_DIF_COLS = ["Prata", "Prata Max", "Ouro", "Ouro Max", "Diamante", "Diamante Max"]
MET_DIF = [
    ["Assistência em viagem", "Nacional", "Nacional",
     "Nacional + Internacional USD/€ 60.000", "Nacional + Internacional USD/€ 60.000",
     "Nacional + Internacional USD/€ 100.000", "Nacional + Internacional USD/€ 300.000"],
    ["Check-up Titulares ¹", "-", "-", "-", "-", "Sim", "Sim"],
    ["Check-up Dependentes ¹", "-", "-", "-", "-", "-", "Sim"],
    ["Concierge de Saúde", "-", "-", "-", "-", "Sim", "Sim"],
    ["Coleta domiciliar ²", "-", "-", "Sim", "Sim", "Sim", "Sim"],
    ["Reembolso de consultas e exames", "Até 7 dias úteis", "Até 7 dias úteis",
     "Até 5 dias úteis", "Até 5 dias úteis", "Até 3 dias úteis", "Até 3 dias úteis"],
    ["Reembolso de procedimentos", "30 dias (corridos)", "30 dias (corridos)",
     "10 dias úteis", "10 dias úteis", "10 dias úteis", "10 dias úteis"],
    ["Reembolso no exterior ³", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim"],
    ["Retaguarda hospitalar Sírio-Libanês", "-", "-", "-", "-", "Sim", "Sim"],
    ["Retaguarda hospitalar Albert Einstein", "-", "-", "-", "-", "-", "Sim"],
    ["Orientação médica por telefone", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim"],
    ["Médico na Tela — consulta médica por vídeo", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim"],
    ["Psicólogo na Tela — atendimento psicológico online", "Sim", "Sim", "Sim", "Sim", "Sim", "Sim"],
    ["Programa de imunização — Vacinas ²", "-", "-", "Sim", "Sim", "Sim", "Sim"],
    ["Transplante (Extra Rol ANS) ¹", "-", "-", "Coração e Pulmão", "Coração e Pulmão",
     "Coração, Pulmão e Pâncreas", "Coração, Pulmão e Pâncreas"],
    ["Cirurgia Refrativa - Miopia", "Conforme Rol ANS", "Conforme Rol ANS",
     "Acima do grau -3,0 ⁴", "Acima do grau -3,0 ⁴", "Sem limite de grau", "Sem limite de grau"],
    ["RPG com justificativa médica ⁴", "12 sessões", "12 sessões", "30 sessões",
     "30 sessões", "40 sessões", "40 sessões"],
    ["Hidroterapia ⁴", "-", "10 sessões", "30 sessões", "30 sessões", "40 sessões", "40 sessões"],
    ["Escleroterapia de veias ⁴", "-", "-", "18 sessões", "18 sessões", "25 sessões", "25 sessões"],
]
MET_DIF_NOTAS = (
    "1) Somente nos prestadores indicados pela NotreDame Saúde. | 2) Coleta e Vacina "
    "Domiciliar são serviços oferecidos por prestadores indicados pela NotreDame Saúde; "
    "cobertura de vacinas conforme Calendário do Ministério da Saúde. | 3) Reembolso "
    "limitado ao valor do plano contratado, conforme regras e condições gerais. | "
    "4) Atendimento na rede de prestadores indicada ou por reembolso, conforme a praça."
)

# O nivel de reembolso e propriedade do PRODUTO, nao escolha do vendedor:
# Prata/Prata Max reembolsam so consultas; Ouro/Ouro Max, consultas e honorarios
# medicos; Diamante/Diamante Max, total. O material traz Ouro e Ouro Max na
# MESMA coluna — os valores sao iguais nos dois.
MET_REEMB_COLS = [
    ["Prata", "parcial · consultas"],
    ["Prata Max", "parcial · consultas"],
    ["Ouro / Ouro Max", "parcial · consultas e honorários"],
    ["Diamante", "total"],
    ["Diamante Max", "total"],
]
MET_REEMB = [
    {"l": "Consulta", "v": ["90,00", "110,00", "150,00", "250,00", "500,00"]},
    {"g": "Honorários médicos"},
    {"l": "Adenoidectomia", "v": ["-", "-", "664,28", "996,42", "1.826,78"]},
    {"l": "Apendicectomia", "v": ["-", "-", "1.687,35", "2.531,03", "4.640,22"]},
    {"l": "Artrodese da coluna com instrumentação por segmento",
     "v": ["-", "-", "3.332,26", "4.998,40", "9.163,73"]},
    {"l": "Colecistectomia sem colangiografia", "v": ["-", "-", "2.004,98", "3.007,48", "5.513,71"]},
    {"l": "Colecistectomia sem colangiografia por videolaparoscopia",
     "v": ["-", "-", "3.070,56", "4.423,06", "7.804,32"]},
    {"l": "Hérnia de disco cervical - tratamento cirúrgico",
     "v": ["-", "-", "3.237,81", "4.856,71", "8.903,96"]},
    {"l": "Hérnia de disco tóraco-lombar - tratamento cirúrgico",
     "v": ["-", "-", "2.459,14", "3.688,70", "6.762,62"]},
    {"l": "Histerectomia total - qualquer via", "v": ["-", "-", "2.844,82", "4.267,23", "7.823,25"]},
    {"l": "Parto (cesariana)", "v": ["-", "-", "2.420,18", "3.630,26", "6.655,48"]},
    {"l": "Parto (via vaginal)", "v": ["-", "-", "2.060,03", "3.090,04", "5.665,07"]},
    {"l": "Revascularização do miocárdio", "v": ["-", "-", "4.326,03", "6.489,04", "11.896,57"]},
    {"g": "Exames e terapias"},
    {"l": "Consulta ambulatorial por nutricionista", "v": ["-", "-", "-", "101,49", "126,87"]},
    {"l": "RX - Tórax", "v": ["-", "-", "-", "115,16", "140,53"]},
    {"l": "TC - Coluna cervical ou dorsal ou lombossacra", "v": ["-", "-", "-", "419,34", "451,79"]},
    {"l": "TC - Crânio", "v": ["-", "-", "-", "482,98", "524,45"]},
    {"l": "US - Transvaginal", "v": ["-", "-", "-", "313,51", "380,41"]},
    {"l": "Hemograma", "v": ["-", "-", "-", "9,76", "9,90"]},
    {"l": "Mamografia digital bilateral", "v": ["-", "-", "-", "423,32", "502,49"]},
    {"l": "Endoscopia digestiva alta", "v": ["-", "-", "-", "628,15", "698,82"]},
    {"l": "RM - Coluna cervical ou dorsal ou lombar", "v": ["-", "-", "-", "912,36", "959,87"]},
    {"l": "TC - Tórax", "v": ["-", "-", "-", "533,56", "575,03"]},
    {"l": "Acupuntura por sessão", "v": ["-", "-", "-", "150,99", "174,74"]},
    {"l": "Sessão de psicoterapia individual", "v": ["-", "-", "-", "316,69", "395,87"]},
    {"l": "Sessão individual ambulatorial de fonoaudiologia", "v": ["-", "-", "-", "101,49", "126,87"]},
]
MET_REEMB_NOTAS = (
    "Valores expressos em reais (R$), conforme a TNDI (Tabela NotreDame Intermédica). "
    "O nível de reembolso é característica do produto: Prata e Prata Max reembolsam "
    "consultas; Ouro e Ouro Max, consultas e honorários médicos; Diamante e Diamante Max, "
    "reembolso total. Os limites máximos reembolsáveis, em valor ou quantidade, observam o "
    "contrato e as diretrizes de utilização do Rol da ANS, que pode ser atualizado. "
    "Leia as condições gerais antes da contratação — www.notredame.com.br"
)

INI, FIM = "/*ND_INI*/", "/*ND_FIM*/"


def bloco():
    j = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return (
        INI
        + "const ND_DIF_COLS=" + j(DIF_COLS) + ","
        + "ND_DIF=" + j(DIF) + ","
        + "ND_DIF_NOTAS=" + j(DIF_NOTAS) + ","
        + "ND_REEMB_COLS=" + j(REEMB_COLS) + ","
        + "ND_REEMB=" + j(REEMB) + ","
        + "ND_REEMB_NOTAS=" + j(REEMB_NOTAS) + ","
        + "ND_MET_DIF_COLS=" + j(MET_DIF_COLS) + ","
        + "ND_MET_DIF=" + j(MET_DIF) + ","
        + "ND_MET_DIF_NOTAS=" + j(MET_DIF_NOTAS) + ","
        + "ND_MET_REEMB_COLS=" + j(MET_REEMB_COLS) + ","
        + "ND_MET_REEMB=" + j(MET_REEMB) + ","
        + "ND_MET_REEMB_NOTAS=" + j(MET_REEMB_NOTAS) + ";"
        + FIM
    )


def main():
    s = open(H, encoding="utf-8").read()
    novo = bloco()
    if INI in s:
        s = re.sub(re.escape(INI) + r".*?" + re.escape(FIM), lambda m: novo, s, flags=re.S)
        acao = "substituído"
    else:
        # entra logo antes do gerador do folder NotreDame
        marca = "/* ===== quadros NotreDame no folder ===== */"
        if marca not in s:
            raise SystemExit("ABORTADO: não achei onde inserir — rode o patch do index antes")
        s = s.replace(marca, novo + "\n" + marca, 1)
        acao = "inserido"
    open(H, "w", encoding="utf-8").write(s)
    print(f"bloco ND {acao}: {len(novo)} chars · {len(DIF)} linhas de diferenciais · "
          f"{len([r for r in REEMB if 'l' in r])} linhas de reembolso")


if __name__ == "__main__":
    main()
