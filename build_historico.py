#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HISTORICO DE COTACOES no Cotador HapOn.

Pedido dos vendedores (24/09/2026): eles nao tinham como recuperar uma cotacao
feita dias antes. Busca por CPF, CNPJ, telefone ou nome do cliente.

Onde os dados ficam: no MESMO Supabase do HapOn Learn, porque e la que ja existe
a identidade do vendedor (perfis, papeis, equipes). Tabela criada por
supabase_cotacoes.sql. Visibilidade: o dono sempre ve; gerente e diretor veem
tudo; supervisor ve a propria equipe — a mesma regra ja usada em `progresso`.

Como o Cotador sabe quem e o vendedor: a sessao chega pelo hash da URL quando o
app do time abre o Cotador no iframe (o app ja faz isso com o Learn — basta o
card ter sso=True). NAO conte com a sessao valendo no Cotador aberto direto:
Chrome e Safari particionam o armazenamento de iframes de outro site, entao o
que o supabase-js grava dentro do app fica preso ao app.

O Cotador NAO fica atras de login. Sem sessao ele funciona exatamente como
antes; so a aba de historico avisa como habilitar. E o supabase-js entra de
forma preguicosa: se o CDN falhar, nada quebra — some so o historico.

Uso: python3 build_historico.py
"""
import re, sys

H = "/Users/marcoscorrea/comparativo-ppo/index.html"
INI, FIM = "/*HIST_INI*/", "/*HIST_FIM*/"

CSS = """
  /* ===== histórico de cotações ===== */
  .hist-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
  .hist-bar input{flex:1;min-width:230px;padding:9px 13px;border:1px solid var(--line);border-radius:9px;font-size:13.5px;color:var(--txt)}
  .hist-bar input:focus{outline:none;border-color:var(--hap)}
  .hist-aviso{background:#eef1fa;border:1px solid #c9d3ee;border-radius:10px;padding:16px 18px;font-size:13.5px;line-height:1.6;color:var(--navy)}
  .hist-vazio{color:var(--muted);font-size:13.5px;padding:24px 4px}
  .hist-item{border:1px solid var(--line);border-radius:11px;padding:13px 15px;margin-bottom:9px;display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center}
  .hist-item:hover{border-color:var(--hap)}
  .hist-cli{font-weight:700;color:var(--navy);font-size:14.5px}
  .hist-meta{font-size:12px;color:var(--muted);line-height:1.6;margin-top:3px}
  .hist-val{font-size:16px;font-weight:700;color:var(--navy);text-align:right;white-space:nowrap}
  .hist-acao{display:flex;gap:7px;justify-content:flex-end;margin-top:6px}
  .hist-acao button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 11px;font-size:12px;cursor:pointer;color:var(--txt)}
  .hist-acao button:hover{border-color:var(--hap)}
  .hist-dono{display:inline-block;background:#f1f3f9;border-radius:5px;padding:1px 6px;font-size:11px;margin-left:6px}
  .hist-selo{display:inline-block;border:1px solid var(--line);color:var(--muted);border-radius:5px;padding:1px 6px;font-size:10.5px;font-weight:600;margin-left:6px;vertical-align:middle}
  .hist-selo.ok{border-color:#bcd9c4;background:#eef7f0;color:#2b6b3f}
  .hist-login{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 6px}
  .hist-login input{flex:1;min-width:180px;padding:9px 12px;border:1px solid var(--line);border-radius:9px;font-size:13.5px}
  .hist-msg{font-size:12.5px;color:#b3261e;min-height:18px;margin-bottom:4px}
  .hist-quem{font-size:12.5px;color:var(--muted);margin-bottom:10px}
  .hist-quem a{color:var(--hap)}
  @media(max-width:620px){.hist-item{grid-template-columns:1fr}.hist-val{text-align:left}}
"""

JS = r"""
/* ===================== HISTÓRICO DE COTAÇÕES =====================
   Guarda a cotação no Supabase do HapOn Learn — é lá que a identidade do
   vendedor já existe. Tudo aqui é opcional: sem sessão, ou com o CDN fora do
   ar, o Cotador funciona exatamente como antes.                          */
const HIST=(function(){
  const SB_URL='https://xqmhzvkzjkkzwqhbyneo.supabase.co';
  const SB_KEY='sb_publishable_hbPdC6CRhyY2tPGAAJL0dA_2wG7lcuR';
  /* O documento não é gravado por extenso: guarda-se o hash e os 4 últimos
     dígitos. O sal mora aqui, no JS servido ao navegador, então isso é uma
     camada a mais e não criptografia — quem controla o acesso é a RLS. O ganho
     real: um dump da tabela não entrega CPF legível, e nem a gestão, que pode
     ler as linhas, vê o número inteiro. */
  const SAL='cotador-hapon::2026';
  let _sb=null,_sdk=null,_perfil=undefined;

  const dig=s=>(s||'').replace(/\D/g,'');

  /* Os dois logos (Hapvida e NotreDame) são data-URI e sozinhos respondem por
     56 dos 92 KB do folder. São iguais em toda cotação e já estão no index.html,
     então saem na gravação e voltam na exibição, pelo alt. */
  function enxuga(html){return html.replace(/src="data:image[^"]*"/g,'src="@logo"');}
  function reidrata(html){
    const src=t=>((t||'').match(/src="([^"]*)"/)||[])[1]||'';
    const mapa={'Hapvida':src(LOGO_SVG),'NotreDame Saúde':src(NOTRE_LOGO_SVG)};
    return html.replace(/<img[^>]*src="@logo"[^>]*>/g,function(tag){
      const alt=(tag.match(/alt="([^"]*)"/)||[])[1]||'';
      return tag.replace('@logo',mapa[alt]||'');});
  }

  function sdk(){
    if(_sdk)return _sdk;
    _sdk=new Promise(function(ok,nao){
      if(window.supabase)return ok();
      const s=document.createElement('script');
      s.src='https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2';
      s.onload=()=>ok(); s.onerror=()=>nao(new Error('CDN do Supabase indisponível'));
      document.head.appendChild(s);
    });
    return _sdk;
  }
  async function cli(){
    if(_sb)return _sb;
    await sdk();
    _sb=window.supabase.createClient(SB_URL,SB_KEY,{auth:{
      persistSession:true,autoRefreshToken:true,detectSessionInUrl:true,storageKey:'cot_auth'}});
    return _sb;
  }
  async function hash(d){
    const b=new TextEncoder().encode(SAL+dig(d));
    const h=await crypto.subtle.digest('SHA-256',b);
    return Array.from(new Uint8Array(h)).map(x=>x.toString(16).padStart(2,'0')).join('');
  }
  /* quem está usando: false = sem sessão (o Cotador segue aberto do mesmo jeito) */
  async function quem(){
    if(_perfil!==undefined)return _perfil;
    try{
      const c=await cli();
      const s=(await c.auth.getSession()).data.session;
      if(!s){_perfil=false;return _perfil;}
      const r=await c.from('perfis').select('id,nome,papel,equipe_id').eq('id',s.user.id).maybeSingle();
      _perfil=r.data||false;
    }catch(e){_perfil=false;}
    return _perfil;
  }
  const gestao=p=>!!p&&['supervisor','gerente','diretor'].indexOf(p.papel)>=0;

  /* ---- estado da cotação, para reabrir exatamente como estava ---- */
  function estado(){
    return {v:1,praca:pracaSel,categoria:categoria,cotMode:cotMode,opMode:opMode,
      meiMode:meiMode,contratMode:contratMode,prodSel:Object.assign({},prodSel),
      vidasHMO:Object.assign({},vidasHMO),vidasPPO:Object.assign({},vidasPPO),
      cols:matrixCols.map(c=>({op:c.op,slots:c.slots.map(s=>Object.assign({},s))})),
      cliente:val('clienteNome'),consultor:val('consultorNome'),
      fone:val('clienteFone'),doc:''};   // o documento não vai no payload
  }
  function val(id){const e=document.getElementById(id);return e?(e.value||'').trim():'';}

  async function salvar(rows,tv){
    const p=await quem(); if(!p)return;
    /* chamado depois de o folder já estar montado no #folder — é ele que vira o
       arquivo exato que o cliente recebeu */
    const fel=document.getElementById('folder');
    const d=dig(val('clienteDoc'));
    const reg={vendedor_id:p.id,
      cliente_nome:val('clienteNome')||null,
      cliente_fone:dig(val('clienteFone'))||null,
      doc_tipo:d.length===11?'CPF':(d.length===14?'CNPJ':null),
      doc_hash:(d.length===11||d.length===14)?await hash(d):null,
      doc_fim:d?d.slice(-4):null,
      praca:pracaSel,vidas:tv,
      total:rows.reduce((s,r)=>s+r.total,0),
      folder_html:fel?enxuga(fel.innerHTML):null,
      folder_cls:fel?fel.className:null,
      folder_em:fel?new Date().toISOString():null,
      resumo:rows.map(r=>r.c.label+' · '+r.c.acomodacao).join(' | ').slice(0,400),
      payload:estado()};
    try{
      const c=await cli();
      const r=await c.from('cotacoes').insert(reg);
      if(r.error)console.warn('histórico: não salvou —',r.error.message);
    }catch(e){console.warn('histórico: não salvou —',e.message);}
  }

  async function buscar(termo){
    const c=await cli(); const p=await quem(); if(!p)return [];
    let q=c.from('cotacoes')
      .select('id,criado_em,cliente_nome,cliente_fone,doc_tipo,doc_fim,praca,total,vidas,resumo,vendedor_id,folder_em,perfis(nome)')
      .order('criado_em',{ascending:false}).limit(100);
    const t=(termo||'').trim(), d=dig(t);
    if(t){
      if(d.length===11||d.length===14) q=q.eq('doc_hash',await hash(d));
      else if(d.length>=8)             q=q.like('cliente_fone','%'+d+'%');
      else                             q=q.ilike('cliente_nome','%'+t+'%');
    }
    const r=await q;
    if(r.error){console.warn('histórico:',r.error.message);return [];}
    return r.data||[];
  }

  /* Aplica um estado salvo na tela. Sem alert e sem trocar de aba: quem chama
     decide o que fazer depois. */
  function aplicar(e){
    pracaSel=e.praca; categoria=e.categoria; cotMode=e.cotMode; opMode=e.opMode;
    meiMode=e.meiMode; contratMode=e.contratMode;
    Object.keys(prodSel).forEach(k=>delete prodSel[k]); Object.assign(prodSel,e.prodSel);
    BANDS.forEach(b=>{vidasHMO[b]=(e.vidasHMO||{})[b]||0;vidasPPO[b]=(e.vidasPPO||{})[b]||0;});
    matrixCols=e.cols.map(c=>({op:c.op,slots:c.slots.map(s=>Object.assign(emptySlot(),s))}));
    ['clienteNome','consultorNome','clienteFone'].forEach(function(id,i){
      const el=document.getElementById(id); if(el)el.value=[e.cliente,e.consultor,e.fone][i]||'';});
    buildPracaChips(); buildProdChips(); buildCotModeChips();
    buildVidas(); buildMatrix(); refreshTot(); recompute();
  }

  /* VER O FOLDER de uma cotação salva.
     Não carrega a cotação na calculadora de propósito: mexer nela criaria uma
     cotação nova com cara de antiga. Aqui só se vê (e se salva de novo) o que
     foi entregue ao cliente. A tela do vendedor volta como estava. */
  async function folder(id){
    const c=await cli();
    const r=await c.from('cotacoes')
      .select('payload,cliente_nome,total,folder_html,folder_cls,folder_em').eq('id',id).maybeSingle();
    if(r.error||!r.data){alert('Não consegui abrir esta cotação.');return;}

    /* Caminho bom: o folder ORIGINAL está guardado (até 30 dias). Mostra-se o
       arquivo exato que o cliente recebeu — mesmos preços, mesma data — e a
       tela do vendedor nem chega a ser tocada. */
    if(r.data.folder_html){
      const fel=document.getElementById('folder');
      fel.className=r.data.folder_cls||'';
      fel.innerHTML=reidrata(r.data.folder_html);
      const t0=document.title;
      document.title='Cotacao'+(r.data.cliente_nome?' - '+r.data.cliente_nome:'');
      try{await Promise.all([...fel.querySelectorAll('img')].map(i=>i.decode()));}catch(e){}
      window.print();
      setTimeout(function(){document.title=t0;},600);
      return;
    }

    /* Passados os 30 dias o snapshot foi apagado: remonta com a tabela vigente,
       avisando o que mudou. */
    const antes=estado();                       // o que o vendedor está fazendo agora
    const abaAtual=document.querySelector('.tab.active');
    try{
      aplicar(r.data.payload);
      /* A cotação pode não existir mais como foi salva: a tabela daquela praça
         pode ter mudado de faixa de porte, ou o produto pode ter saído de linha.
         Sem este aviso o vendedor recebia o genérico "informe as vidas e
         selecione ao menos um plano" — que não diz nada sobre o que houve. */
      const orfaos=[];
      matrixCols.forEach(function(col,ci){col.slots.forEach(function(x,si){
        if(x.plano&&x.acom&&x.seg&&!resolved(ci,si))orfaos.push(x.plano+' · '+x.acom);});});
      if(orfaos.length){
        alert('Não consigo remontar esta cotação com as tabelas de hoje.\n\n'+
          'Sem preço atual para: '+orfaos.join(', ')+'.\n\n'+
          'A tabela da praça mudou desde que ela foi salva. Os dados do cliente '+
          'continuam aqui no histórico — para ofertar de novo, faça uma cotação nova.');
        return;
      }
      /* A tabela de preços pode ter mudado desde a cotação. Refazer o folder em
         silêncio entregaria ao cliente um valor diferente do que foi combinado,
         sem ninguém perceber. */
      const hoje=selectedPlans().reduce((s,x)=>s+planTotal(x),0);
      const salvo=Number(r.data.total||0);
      if(Math.abs(hoje-salvo)>0.005){
        const ok=confirm('Esta cotação foi salva em R$ '+fmt(salvo)+' e hoje os mesmos planos dão R$ '+fmt(hoje)+'.\n\n'+
          'A tabela de preços mudou desde então. O folder sai com o valor de HOJE.\n\nGerar assim mesmo?');
        if(!ok)return;
      }
      /* Não dá para depender de gerarFolder() resolver: ele termina em
         window.print(), que é modal, e antes disso espera o decode() dos logos.
         Se ficar pendurado, a tela do vendedor ficaria presa na cotação antiga.
         O conteúdo do folder já está montado quando o print dispara, então
         soltar depois de um tempo é seguro — e garante a volta. */
      await Promise.race([gerarFolder().catch(function(){}),
                          new Promise(function(r){setTimeout(r,12000);})]);
    }finally{
      aplicar(antes);                           // devolve a tela ao ponto em que estava
      if(abaAtual)switchTab(abaAtual.dataset.tab);
    }
  }

  /* EDITAR uma cotação salva. Os vendedores pediram isso de volta em 25/09.
     O risco que existia — "cotação mexida vira outra com cara de antiga" — se
     resolve sozinho porque salvar() sempre INSERE: a original continua no
     histórico, com o folder original dela, e a edição entra como registro novo
     quando o vendedor gerar o folder. */
  async function editar(id){
    const c=await cli();
    const r=await c.from('cotacoes').select('payload,cliente_nome').eq('id',id).maybeSingle();
    if(r.error||!r.data){alert('Não consegui abrir esta cotação.');return;}
    aplicar(r.data.payload);
    /* O CPF/CNPJ não é gravado por extenso, então não há como devolvê-lo ao
       campo. Deixá-lo como estava faria a cotação nova sair com o documento do
       cliente ANTERIOR, sem ninguém perceber. */
    const doc=document.getElementById('clienteDoc'); if(doc)doc.value='';
    switchTab('calc');
    const orfaos=[];
    matrixCols.forEach(function(col,ci){col.slots.forEach(function(x,si){
      if(x.plano&&x.acom&&x.seg&&!resolved(ci,si))orfaos.push(x.plano+' · '+x.acom);});});
    alert('Cotação de '+(r.data.cliente_nome||'cliente sem nome')+' carregada para edição.\n\n'+
      (orfaos.length
        ? '⚠ Sem preço atual para: '+orfaos.join(', ')+'. A tabela desta praça mudou — reveja a seleção.\n\n'
        : '')+
      'A original continua no histórico, intacta. Ao gerar o folder, isto entra como uma cotação NOVA.\n\n'+
      'Redigite o CPF ou CNPJ: por segurança ele não fica guardado por extenso, só o suficiente para a busca.');
  }

  async function apagar(id){
    if(!confirm('Apagar esta cotação do histórico? Não dá para desfazer.'))return;
    const c=await cli(); const r=await c.from('cotacoes').delete().eq('id',id);
    if(r.error){alert('Não consegui apagar: '+r.error.message);return;}
    render();
  }

  const fmtD=s=>{const d=new Date(s);return d.toLocaleDateString('pt-BR')+' '+
    d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});};

  async function render(){
    const box=document.getElementById('histLista'); if(!box)return;
    box.innerHTML='<div class="hist-vazio">Carregando…</div>';
    let p;
    try{p=await quem();}catch(e){p=false;}
    if(!p){
      box.innerHTML='<div class="hist-aviso"><b>Entre com o seu acesso do HapON Learn para guardar e buscar cotações.</b><br>'+
        'Aberto pelo app HapON Vendas, o Cotador já reconhece você. O cálculo e o folder funcionam sem login.'+
        '<form class="hist-login" onsubmit="event.preventDefault();HIST.entrar()">'+
        '<input type="email" id="histEmail" placeholder="nome@hapvida.com.br" autocomplete="email" required>'+
        '<input type="password" id="histSenha" placeholder="Senha" autocomplete="current-password" required>'+
        '<button class="btn vd" id="histEntrar" type="submit">Entrar</button></form>'+
        '<div id="histMsg" class="hist-msg"></div>'+
        '<a href="https://hub-hapvida-learn.vercel.app" target="_blank" style="color:var(--hap);font-size:12.5px">Esqueci a senha / primeiro acesso →</a></div>';
      return;
    }
    const itens=await buscar(document.getElementById('histBusca').value);
    if(!itens.length){
      box.innerHTML=quemBarra(p)+'<div class="hist-vazio">Nenhuma cotação encontrada. '+
        'As cotações entram aqui quando você gera o folder.</div>';
      return;
    }
    const eu=p.id, ger=gestao(p);
    box.innerHTML=quemBarra(p)+itens.map(function(x){
      const doc=x.doc_fim?(x.doc_tipo||'Doc')+' final '+x.doc_fim:'';
      const fone=x.cliente_fone?telFmt(x.cliente_fone):'';
      const dono=(ger&&x.vendedor_id!==eu&&x.perfis)?'<span class="hist-dono">'+esc(x.perfis.nome)+'</span>':'';
      const selo=x.folder_em
        ? '<span class="hist-selo ok" title="O folder guardado é o arquivo exato que o cliente recebeu.">folder original</span>'
        : '<span class="hist-selo" title="Passaram-se mais de 30 dias: o folder será remontado com a tabela de hoje, e você será avisado se o preço mudou.">remontado hoje</span>';
      return '<div class="hist-item"><div>'+
        '<div class="hist-cli">'+esc(x.cliente_nome||'(sem nome)')+dono+selo+'</div>'+
        '<div class="hist-meta">'+fmtD(x.criado_em)+' · '+esc(x.praca||'')+' · '+(x.vidas||0)+' vida(s)'+
        (doc?' · '+doc:'')+(fone?' · '+fone:'')+'<br>'+esc(x.resumo||'')+'</div></div>'+
        '<div><div class="hist-val">R$ '+fmt(x.total||0)+'</div>'+
        '<div class="hist-acao"><button onclick="HIST.folder(\''+x.id+'\')" title="Abre o folder desta cotação para ver e salvar em PDF. Não altera a cotação — para mudar algo, faça uma nova.">Ver folder</button>'+
        '<button onclick="HIST.editar(\''+x.id+'\')" title="Carrega esta cotação na calculadora para alterar. A original continua no histórico; ao gerar o folder, a alterada entra como cotação nova.">Editar</button>'+
        (x.vendedor_id===eu?'<button onclick="HIST.apagar(\''+x.id+'\')">Apagar</button>':'')+
        '</div></div></div>';}).join('');
  }
  function quemBarra(p){
    return '<div class="hist-quem">Conectado como <b>'+esc(p.nome||'')+'</b> · '+
      '<a href="#" onclick="event.preventDefault();HIST.sair()">sair</a></div>';
  }
  async function entrar(){
    const m=document.getElementById('histMsg'), b=document.getElementById('histEntrar');
    const email=val('histEmail'), senha=(document.getElementById('histSenha')||{}).value||'';
    if(!email||!senha){m.textContent='Preencha e-mail e senha.';return;}
    b.disabled=true; m.textContent='Entrando…';
    try{
      const c=await cli();
      const r=await c.auth.signInWithPassword({email:email,password:senha});
      if(r.error){b.disabled=false;
        m.textContent=/invalid/i.test(r.error.message)?'E-mail ou senha incorretos.':'Não foi possível entrar: '+r.error.message;return;}
      _perfil=undefined;
      const p=await quem();
      if(!p){b.disabled=false;m.textContent='Login feito, mas não achei o seu perfil no HapON Learn.';return;}
      render();
    }catch(e){b.disabled=false;m.textContent='Não foi possível entrar agora. Tente de novo em instantes.';}
  }
  async function sair(){
    try{const c=await cli(); await c.auth.signOut();}catch(e){}
    _perfil=false; render();
  }
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
  function telFmt(d){return d.length===11?'('+d.slice(0,2)+') '+d.slice(2,7)+'-'+d.slice(7):
                     d.length===10?'('+d.slice(0,2)+') '+d.slice(2,6)+'-'+d.slice(6):d;}

  return {salvar:salvar,render:render,folder:folder,editar:editar,apagar:apagar,quem:quem,estado:estado,entrar:entrar,sair:sair};
})();
/* Aberto pelo app, a sessão chega no hash. Lê já na abertura: se esperasse o
   primeiro folder, o vendedor que só consulta nunca ficaria reconhecido. */
if(/access_token=/.test(location.hash)){try{HIST.quem();}catch(e){}}
"""


def main():
    s = open(H, encoding="utf-8").read()
    n0 = len(s.encode())

    # --- CSS
    if ".hist-bar{" in s:
        # já inserido antes: troca o bloco inteiro, para mudanças no CSS valerem
        a = s.index("  /* ===== histórico de cotações ===== */")
        b = s.index("  /* plan cards */", a)
        s = s[:a] + CSS.strip("\n") + "\n" + s[b:]
    else:
        alvo = "  /* plan cards */"
        if alvo not in s:
            raise SystemExit("ABORTADO: não achei onde inserir o CSS")
        s = s.replace(alvo, CSS.strip("\n") + "\n" + alvo, 1)

    # --- aba
    if 'data-tab="hist"' not in s:
        alvo = '<button class="tab" data-tab="area" onclick="switchTab(\'area\')">Área de comercialização</button>'
        if alvo not in s:
            raise SystemExit("ABORTADO: não achei a barra de abas")
        s = s.replace(alvo, alvo +
                      '\n    <button class="tab" data-tab="hist" onclick="switchTab(\'hist\')">Cotações salvas</button>', 1)

    # --- painel da aba, logo depois do pane-area
    if 'id="pane-hist"' not in s:
        m = re.search(r'<div class="tabpane" id="pane-area">', s)
        if not m:
            raise SystemExit("ABORTADO: não achei o painel da Área de Comercialização")
        # fecha onde o proximo painel comecaria: insere antes do fechamento da secao de abas
        pane = ('\n  <div class="tabpane" id="pane-hist">\n'
                '    <div class="card">\n'
                '      <h2 style="margin:0 0 4px">Cotações salvas</h2>\n'
                '      <p style="margin:0 0 14px;color:var(--muted);font-size:13.5px">'
                'Toda cotação entra aqui quando você gera o folder. Busque por CPF, CNPJ, '
                'telefone ou nome do cliente.</p>\n'
                '      <div class="hist-bar">\n'
                '        <input id="histBusca" placeholder="CPF, CNPJ, telefone ou nome do cliente" '
                'onkeydown="if(event.key===\'Enter\')HIST.render()">\n'
                '        <button class="btn vd" onclick="HIST.render()">Buscar</button>\n'
                '      </div>\n'
                '      <div id="histLista"></div>\n'
                '    </div>\n'
                '  </div>\n')
        fim = s.index("</div>", s.index('<div class="tabpane" id="pane-area">'))
        # sobe até o fechamento do painel da área: procura o proximo "\n  </div>"
        fecha = s.index("\n  </div>", s.index('<div class="tabpane" id="pane-area">'))
        s = s[:fecha + len("\n  </div>")] + pane + s[fecha + len("\n  </div>"):]

    # --- switchTab passa a conhecer a aba
    velho = ("  document.getElementById('pane-area').classList.toggle('active',t==='area');\n"
             "  if(t==='rede'){loadRede();}")
    if velho in s:
        s = s.replace(velho,
                      "  document.getElementById('pane-area').classList.toggle('active',t==='area');\n"
                      "  const ph=document.getElementById('pane-hist');\n"
                      "  if(ph)ph.classList.toggle('active',t==='hist');\n"
                      "  if(t==='rede'){loadRede();}\n"
                      "  if(t==='hist'){try{HIST.render();}catch(e){}}", 1)

    # --- deep link da aba
    s = s.replace("match(/^#\\/?(calc|rede|area)$/)", "match(/^#\\/?(calc|rede|area|hist)$/)")

    # --- campos de identificação do cliente
    if 'id="clienteDoc"' not in s:
        alvo = '<input id="consultorNome" placeholder="Consultor de Vendas (aparece no folder)">'
        if alvo not in s:
            raise SystemExit("ABORTADO: não achei o campo do consultor")
        s = s.replace(alvo, alvo +
                      '\n          <input id="clienteDoc" placeholder="CPF ou CNPJ (para achar depois)" '
                      'inputmode="numeric" title="Não é gravado por extenso: guardamos só o suficiente para você reencontrar a cotação.">'
                      '\n          <input id="clienteFone" placeholder="Telefone do cliente" inputmode="tel">', 1)

    # --- salva ao gerar o folder: é aí que a cotação virou algo entregue
    alvo = "  const t0=document.title;\n  document.title='Cotacao'"
    if "HIST.salvar(" not in s:
        if alvo not in s:
            raise SystemExit("ABORTADO: não achei o ponto de geração do folder")
        s = s.replace(alvo,
                      "  // o folder é o momento em que a cotação virou algo entregue ao cliente\n"
                      "  try{HIST.salvar(rows,tv);}catch(e){}\n" + alvo, 1)

    # --- o módulo
    bloco = INI + JS + FIM
    if INI in s:
        s = re.sub(re.escape(INI) + r".*?" + re.escape(FIM), lambda m: bloco, s, flags=re.S)
        acao = "substituído"
    else:
        marca = "/* ===== quadros NotreDame no folder ===== */"
        if marca not in s:
            raise SystemExit("ABORTADO: não achei onde inserir o módulo")
        s = s.replace(marca, bloco + "\n" + marca, 1)
        acao = "inserido"

    open(H, "w", encoding="utf-8").write(s)
    print("histórico %s — index.html: %d -> %d bytes" % (acao, n0, len(s.encode())))


if __name__ == "__main__":
    main()
