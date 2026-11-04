# -*- coding: utf-8 -*-
"""Levanta prefixo de CEP (5 digitos) -> bairro, para SP capital e Rio capital.

Por que: casar o bairro pelo NOME que o ViaCEP devolve nao funciona. O CEP
05615-000 (Morumbi na planilha) devolve "Vila Progredior", que e sub-bairro do
distrito Morumbi — e o mesmo vale para Jardim Everest, Vila Inah, Jardim Leonor.
Com o mapa prefixo->bairro em maos da para montar FAIXAS de CEP por bairro da
lista, que e como o cotador vai casar.

Consulta XXXXX-000 de cada prefixo. Cache em disco para poder retomar.
Saida: /tmp/cep_prefixos.json  {prefixo: [bairro, cidade, uf]}
"""
import json, os, sys, time, urllib.request
import concurrent.futures as cf

OUT = '/tmp/cep_prefixos.json'
FAIXAS = [(1000, 5999), (22000, 22999)]   # SP capital (+ arredores), Rio Zona Sul/Barra

cache = json.load(open(OUT)) if os.path.exists(OUT) else {}
alvo = ['%05d' % i for a, b in FAIXAS for i in range(a, b + 1)]
falta = [p for p in alvo if p not in cache]
print('prefixos alvo: %d | ja em cache: %d | a consultar: %d'
      % (len(alvo), len(alvo) - len(falta), len(falta)))


def q(p):
    for _ in range(3):
        try:
            with urllib.request.urlopen('https://viacep.com.br/ws/%s000/json/' % p, timeout=15) as r:
                d = json.loads(r.read().decode())
            if d.get('erro'):
                return p, None
            return p, [d.get('bairro') or '', d.get('localidade') or '', d.get('uf') or '']
        except Exception:
            time.sleep(0.6)
    return p, 'ERRO'


t0 = time.time()
feito = 0
with cf.ThreadPoolExecutor(8) as ex:
    for p, v in ex.map(q, falta):
        cache[p] = v
        feito += 1
        if feito % 250 == 0:
            json.dump(cache, open(OUT, 'w'), ensure_ascii=False)
            el = time.time() - t0
            print('  %d/%d  %.0fs  (%.1f req/s, faltam ~%.0fs)'
                  % (feito, len(falta), el, feito / el, (len(falta) - feito) / max(feito / el, .1)),
                  flush=True)

json.dump(cache, open(OUT, 'w'), ensure_ascii=False)
erros = sum(1 for v in cache.values() if v == 'ERRO')
vazios = sum(1 for v in cache.values() if v is None)
ok = sum(1 for v in cache.values() if isinstance(v, list))
print('\nFIM: %d prefixos | %d com bairro | %d inexistentes | %d erro de rede'
      % (len(cache), ok, vazios, erros))
