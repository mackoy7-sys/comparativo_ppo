#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera a CÓPIA do Cotador para parceiro comercial: "Cotador HapOn_JSF".

Pedido de 08/10/2026: uma cópia do Cotador para repassar a um parceiro, com
nome próprio e senha.

Por que o payload é CIFRADO e não só escondido atrás de uma tela: o Cotador
carrega os preços de 5 arquivos JSON por fetch. Uma tela de senha deixaria
`catalog.json` — a tabela de preços nacional inteira, 67 praças — aberta a
quem digitasse o endereço do arquivo. Aqui cada JSON vira um `.enc`
(AES-256-GCM, chave PBKDF2-SHA256 de 200.000 iterações sobre a senha) e só é
decifrado no navegador depois do acerto da senha. Mesmo padrão da Folha
Comercial e do Market Share.

O que SAI nesta cópia, de propósito:
  - a aba "Cotações salvas" e todo o módulo de histórico. Ele autentica no
    Supabase do HapON Learn e grava as cotações na base INTERNA; um parceiro
    não deve ter nem o login nem a gravação. O resto do código já é defensivo
    (`if(ph)`, `try{HIST...}catch`), então a remoção não quebra nada.

O que FICA igual: catálogo, coparticipação, rede, odonto, rede full, folder,
mapa de cidades e busca por CEP.

Uso: build_jsf.py [--senha haponjsf]
Saída: ~/cotador-jsf/dist/  (index.html + *.enc + logo)
"""
import base64, hashlib, json, os, re, shutil, sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SRC = "/Users/marcoscorrea/comparativo-ppo"
AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(AQUI, "dist")
NOME = "Cotador HapOn_JSF"
MARCA = "HapOn_JSF"          # assinatura no folder
SENHA = sys.argv[sys.argv.index("--senha") + 1] if "--senha" in sys.argv else "haponjsf"
DADOS = ["catalog.json", "rede.json", "copart.json", "odonto.json", "rede_full.json"]
ITER = 200_000


def corta_div(html, marcador):
    """Remove a <div> que começa em `marcador` e tudo até o </div> que a fecha."""
    i = html.index(marcador)
    j, prof = i, 0
    while j < len(html):
        if html.startswith("<div", j):
            prof += 1
        elif html.startswith("</div", j):
            prof -= 1
            if prof == 0:
                j = html.index(">", j) + 1
                break
        j += 1
    return html[:i] + html[j:]


def main():
    h = open(os.path.join(SRC, "index.html"), encoding="utf-8").read()
    orig = len(h)

    # ---- 1. nome -----------------------------------------------------------
    h = h.replace("<title>Cotador HapOn — Hapvida vs Operadoras</title>",
                  "<title>%s</title>" % NOME, 1)
    assert h.count(">Cotador HapOn<") == 1, "marca do cabeçalho não encontrada"
    h = h.replace(">Cotador HapOn<", ">%s<" % NOME, 1)
    h = h.replace("uso interno comercial", "uso comercial autorizado")
    # o selo do cabeçalho também é do time interno
    cab = '<div class="upd">Vendas Digital · '
    assert h.count(cab) == 1, "selo do cabeçalho não encontrado"
    h = h.replace(cab, '<div class="upd">%s · ' % MARCA)
    # o folder assina no canto superior direito; "Vendas Digital" é o time
    # interno, e quem entrega este folder ao cliente é o parceiro.
    assert h.count("· Vendas Digital'") == 3, "assinatura do folder não encontrada"
    h = h.replace("· Vendas Digital'", "· %s'" % MARCA)
    # e no rodapé do folder, junto da data de emissão
    rod = "Emitido em ${hoje}.</div>`;"
    assert h.count(rod) == 1, "rodapé do folder não encontrado"
    h = h.replace(rod, "Emitido em ${hoje} · %s.</div>`;" % MARCA)

    # ---- 2. fora o histórico ----------------------------------------------
    a, b = h.index("/*HIST_INI*/"), h.index("/*HIST_FIM*/") + len("/*HIST_FIM*/")
    h = h[:a] + "/* histórico removido na cópia do parceiro: grava na base interna */" + h[b:]
    h = corta_div(h, '<div class="tabpane" id="pane-hist">')
    tab = '<button class="tab" data-tab="hist" onclick="switchTab(\'hist\')">Cotações salvas</button>'
    assert h.count(tab) == 1, "aba do histórico não encontrada"
    h = h.replace(tab, "")
    assert "/*HIST_FIM*/" not in h and 'id="pane-hist"' not in h

    # ---- 3. adia o boot ----------------------------------------------------
    boot = ("fetch('odonto.json',{cache:'no-cache'}).then(r=>r.json()).then(d=>{ODONTO=d||{};})"
            ".catch(()=>{ODONTO={};})\n"
            "  .then(()=>fetch('catalog.json',{cache:'no-cache'}).then(r=>r.json())"
            ".then(d=>{CATALOG=d;boot();}))")
    assert h.count(boot) == 1, "bloco de boot não encontrado"
    h = h.replace(boot, "window.__start=()=>" + boot, 1)

    # ---- 4. cifra os dados -------------------------------------------------
    os.path.isdir(DIST) and shutil.rmtree(DIST)
    os.makedirs(DIST)
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", SENHA.encode(), salt, ITER, dklen=32)
    aes = AESGCM(key)
    mapa = {}
    for nome in DADOS:
        bruto = open(os.path.join(SRC, nome), "rb").read()
        nonce = os.urandom(12)
        ct = aes.encrypt(nonce, bruto, None)
        open(os.path.join(DIST, nome.replace(".json", ".enc")), "wb").write(nonce + ct)
        mapa[nome] = nome.replace(".json", ".enc")
        print("  cifrado %-16s %9d -> %9d b" % (nome, len(bruto), len(nonce) + len(ct)))
    # sentinela pequeno, para validar a senha sem baixar 2 MB
    nonce = os.urandom(12)
    sent = base64.b64encode(nonce + aes.encrypt(nonce, b"ok-hapon-jsf", None)).decode()

    # ---- 5. portão + shim de fetch ----------------------------------------
    gate = GATE % (base64.b64encode(salt).decode(), sent, ITER,
                   json.dumps(mapa, ensure_ascii=False), json.dumps(NOME, ensure_ascii=False))
    assert "</script>\n</body>" in h or "</script>" in h
    k = h.rindex("</script>")
    h = h[:k] + gate + h[k:]

    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(h)
    shutil.copy2(os.path.join(SRC, "hapvida_logo.jpg"), DIST)
    print("\nindex.html %d -> %d b · senha: %s" % (orig, len(h.encode()), SENHA))
    print("dist: %s" % DIST)


GATE = r"""
/* ===== Portão do parceiro =====
   Os dados vêm cifrados (AES-256-GCM, chave PBKDF2 da senha). O shim abaixo
   intercepta o fetch dos .json e devolve o conteúdo decifrado, para que o
   resto do Cotador siga sem saber de nada. Só roda o __start() depois. */
(function(){
  const SALT='%s', SENT='%s', ITER=%d, MAPA=%s, NOME=%s;
  const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  let KEY=null;
  async function deriva(pw){
    const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
    return crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(SALT),iterations:ITER,hash:'SHA-256'},
      km,{name:'AES-GCM',length:256},false,['decrypt']);
  }
  async function abre(buf,key){
    const u=new Uint8Array(buf);
    const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:u.slice(0,12)},key,u.slice(12));
    return new TextDecoder().decode(pt);
  }
  const fetchOrig=window.fetch.bind(window);
  window.fetch=function(u,o){
    const nome=typeof u==='string'?u.split('?')[0].replace(/^\.?\//,''):null;
    if(KEY&&nome&&MAPA[nome]){
      return fetchOrig(MAPA[nome],{cache:'no-cache'}).then(r=>r.arrayBuffer())
        .then(b=>abre(b,KEY)).then(t=>new Response(t,{headers:{'Content-Type':'application/json'}}));
    }
    return fetchOrig(u,o);
  };
  const css='position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;background:#0f1b2d';
  document.body.insertAdjacentHTML('beforeend',
   '<div id="jsfGate" style="'+css+'"><form id="jsfForm" style="background:#fff;border-radius:16px;padding:34px 38px;max-width:360px;width:88%%;text-align:center;font-family:inherit;box-shadow:0 18px 50px rgba(0,0,0,.35)">'
   +'<div style="font-size:32px;margin-bottom:8px">&#128274;</div>'
   +'<div style="font-weight:700;font-size:17px;color:#0f1b2d">'+NOME+'</div>'
   +'<div style="color:#5b6b80;font-size:12.5px;margin:6px 0 18px">Tabela de preços restrita. Informe a senha de acesso.</div>'
   +'<input id="jsfPw" type="password" placeholder="Senha" autocomplete="off" style="width:100%%;box-sizing:border-box;border:1px solid #cfd8e3;border-radius:9px;padding:10px 12px;font-size:14px;font-family:inherit;text-align:center">'
   +'<div id="jsfErr" style="color:#c0392b;font-size:12px;height:17px;margin-top:7px"></div>'
   +'<button type="submit" style="width:100%%;background:#f47b20;color:#fff;border:none;border-radius:9px;padding:10px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit">Entrar</button>'
   +'</form></div>');
  async function tenta(pw,quieto){
    const err=document.getElementById('jsfErr');
    try{
      const k=await deriva(pw);
      await abre(b64(SENT).buffer,k);            // sentinela: valida a senha
      KEY=k; sessionStorage.setItem('jsf_pw',pw);
      document.getElementById('jsfGate').remove();
      window.__start();
    }catch(e){
      sessionStorage.removeItem('jsf_pw');
      if(!quieto&&err)err.textContent='Senha incorreta.';
    }
  }
  document.getElementById('jsfForm').onsubmit=e=>{e.preventDefault();tenta(document.getElementById('jsfPw').value,false);};
  const salvo=sessionStorage.getItem('jsf_pw');
  if(salvo)tenta(salvo,true); else document.getElementById('jsfPw').focus();
})();
"""

if __name__ == "__main__":
    main()
