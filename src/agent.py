"""
Agente de Eventos — Joao Pessoa + Cidades Proximas
- Usa apenas OpenAI (sem confusao com OpenRouter)
- Pesquisa como palestrar em cada evento (call for speakers, contato)
- Calcula custo-beneficio de viagem para outras cidades
"""

import os
import json
import hashlib
import httpx
import re
import time
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODELO = os.environ.get("MODELO_IA", "gpt-4o-mini")

MEMORIA_PATH = "data/eventos_enviados.json"

PERFIL = """
Abel — dono da FluxIA (agencia de IA no Nordeste)
Cria: agentes de atendimento, sistemas SaaS, APIs, automacoes para clinicas
Quer: palestrar, fazer networking, vender IA para clinicas e empresas
Publico-alvo: donos de clinicas (odonto, estetica, medica), empreendedores
Tema de palestra: IA aplicada a negocios, agentes de atendimento, automacao para clinicas
"""

# Custo estimado de viagem por cidade (ida+volta + 1 dia)
CUSTO_VIAGEM = {
    "joao_pessoa":    0,
    "campina_grande": 80,    # onibus ~2h
    "recife":         150,   # onibus/carro ~2h + possivel hospedagem
    "natal":          200,   # onibus ~3h + possivel hospedagem
    "fortaleza":      500,   # passagem + hospedagem obrigatoria
}

QUERIES_EVENTOS = [
    "eventos Joao Pessoa PB 2026 site:sympla.com.br",
    "eventos Joao Pessoa PB 2026 site:even3.com.br",
    "eventos Joao Pessoa PB 2026 site:doity.com.br",
    "eventos Joao Pessoa 2026 site:eventbrite.com.br",
    "workshop inteligencia artificial Joao Pessoa 2026",
    "evento tecnologia startups Joao Pessoa 2026",
    "evento marketing digital Joao Pessoa 2026",
    "evento empreendedorismo negocios Joao Pessoa 2026",
    "congresso odontologia Paraiba 2026",
    "evento clinicas saude estetica Joao Pessoa 2026",
    "evento SEBRAE Paraiba Joao Pessoa 2026",
    "evento ACIPB CDL Joao Pessoa 2026",
    "evento CRO CRM Paraiba 2026",
    "startup PB inovacao evento 2026",
    "evento SENAC Joao Pessoa 2026",
    "summit conferencia Recife PE 2026 site:sympla.com.br",
    "evento tecnologia inovacao Recife 2026",
    "evento empreendedorismo Campina Grande PB 2026",
    "evento tecnologia Campina Grande PB 2026",
    "evento empreendedorismo Natal RN 2026",
    "congresso saude clinicas Nordeste 2026",
    "evento IA inteligencia artificial Nordeste 2026",
]

# Queries especificas para buscar como palestrar
def queries_palestra(nome_evento: str, url: str) -> list:
    nome_curto = nome_evento[:40]
    return [
        f'"{nome_curto}" call for speakers 2026',
        f'"{nome_curto}" como palestrar submeter proposta',
        f'site:{url.split("/")[2]} call for speakers palestrantes',
    ]


# --------------------------------------------------
# MEMORIA
# --------------------------------------------------

def carregar_memoria() -> set:
    try:
        with open(MEMORIA_PATH, "r") as f:
            return set(json.load(f).get("enviados", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def salvar_memoria(enviados: set):
    os.makedirs("data", exist_ok=True)
    with open(MEMORIA_PATH, "w") as f:
        json.dump({"enviados": list(enviados)}, f, indent=2)

def gerar_id(texto: str) -> str:
    return hashlib.md5(texto.encode()).hexdigest()[:12]


# --------------------------------------------------
# TAVILY
# --------------------------------------------------

def buscar_tavily(query: str, max_results: int = 5) -> list:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query,
                  "search_depth": "basic", "max_results": max_results},
            timeout=15
        )
        return r.json().get("results", [])
    except Exception as e:
        print(f"  Erro Tavily: {e}")
        return []


def acessar_pagina(url: str) -> str:
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"},
                      timeout=10, follow_redirects=True)
        texto = re.sub(r"<style[^>]*>.*?</style>", " ", r.text, flags=re.DOTALL)
        texto = re.sub(r"<script[^>]*>.*?</script>", " ", texto, flags=re.DOTALL)
        texto = re.sub(r"<[^>]+>", " ", texto)
        return re.sub(r"\s+", " ", texto).strip()[:800]
    except Exception:
        return ""


# --------------------------------------------------
# FASE 1 — BUSCA DE EVENTOS
# --------------------------------------------------

def buscar_todos_eventos() -> list:
    print(f"Fazendo {len(QUERIES_EVENTOS)} buscas...")
    todos = []
    for i, query in enumerate(QUERIES_EVENTOS):
        print(f"  [{i+1}/{len(QUERIES_EVENTOS)}] {query[:60]}")
        resultados = buscar_tavily(query, max_results=5)
        for res in resultados:
            todos.append({
                "titulo": res.get("title", "")[:100],
                "url":    res.get("url", ""),
                "resumo": res.get("content", "")[:180],
            })
        time.sleep(0.3)
    print(f"Total bruto: {len(todos)} resultados")
    return todos


# --------------------------------------------------
# FASE 2 — EXTRAIR EVENTOS COM IA
# --------------------------------------------------

def extrair_eventos(resultados_brutos: list, hoje: str) -> list:
    contexto = "\n".join([
        f"- {r['titulo']} | {r['url']} | {r['resumo'][:120]}"
        for r in resultados_brutos[:80]
    ])

    prompt = f"""Hoje e {hoje}. Extraia eventos reais desses resultados de busca.

PERFIL:
{PERFIL}

RESULTADOS:
{contexto}

REGRAS:
1. Apenas eventos FUTUROS (apos {hoje})
2. Apenas em JP, Campina Grande, Recife ou Natal
3. Descarte noticias, cursos online permanentes, resultados que nao sejam eventos datados
4. Seja conservador — se nao tiver certeza que e evento futuro, descarte

Retorne APENAS JSON valido sem markdown:
[
  {{
    "nome": "nome completo do evento",
    "data": "DD/MM/AAAA ou vazio se nao souber",
    "local": "local fisico ou Online",
    "cidade": "joao_pessoa|campina_grande|recife|natal",
    "resumo": "2 frases diretas sobre o evento",
    "preco": "Gratuito|R$ valor|A confirmar",
    "url": "url exata",
    "categoria": "tecnologia_ia|marketing|negocios_empreend|saude_clinicas|outros",
    "publico_estimado": "pequeno(<50)|medio(50-200)|grande(+200)|desconhecido",
    "potencial_negocio": "alto|medio|baixo",
    "motivo_negocio": "quem estara presente e por que Abel pode vender"
  }}
]"""

    try:
        r = client.chat.completions.create(
            model=MODELO,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=3000,
        )
        resposta = r.choices[0].message.content.strip()
        resposta = re.sub(r"```json|```", "", resposta).strip()
        match = re.search(r"\[.*\]", resposta, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(resposta)
    except Exception as e:
        print(f"Erro ao extrair eventos: {e}")
        return []


# --------------------------------------------------
# FASE 3 — PESQUISAR COMO PALESTRAR
# --------------------------------------------------

def pesquisar_como_palestrar(evento: dict) -> dict:
    """
    Para cada evento com potencial de palestra,
    busca informacoes reais sobre como se tornar palestrante.
    """
    nome = evento.get("nome", "")
    url  = evento.get("url", "")

    print(f"  Pesquisando como palestrar: {nome[:50]}")

    info_palestra = {
        "tem_call_for_speakers": False,
        "como_palestrar": "",
        "contato": "",
        "prazo_submissao": "",
        "link_inscricao_palestrante": "",
    }

    # Busca informacoes sobre call for speakers
    queries = [
        f"{nome} call for speakers palestrantes 2026",
        f"{nome} como se tornar palestrante submeter proposta",
        f'site:{url.split("/")[2] if "/" in url else url} palestrante speaker',
    ]

    resultados = []
    for q in queries[:2]:  # limita para nao gastar muita Tavily
        res = buscar_tavily(q, max_results=3)
        resultados.extend(res)
        time.sleep(0.2)

    # Tenta acessar a pagina do evento para buscar info de palestrante
    conteudo_pagina = acessar_pagina(url) if url else ""

    if not resultados and not conteudo_pagina:
        info_palestra["como_palestrar"] = "Nao encontrado — contate os organizadores diretamente"
        return info_palestra

    # IA analisa e extrai informacoes de como palestrar
    contexto_palestra = "\n".join([
        f"- {r.get('title','')} | {r.get('url','')} | {r.get('content','')[:150]}"
        for r in resultados[:6]
    ])
    if conteudo_pagina:
        contexto_palestra += f"\n\nCONTEUDO DA PAGINA DO EVENTO:\n{conteudo_pagina[:600]}"

    prompt = f"""Analise as informacoes abaixo sobre o evento "{nome}" e extraia como Abel pode palestrar.

Abel quer saber:
1. Existe call for speakers / submissao de propostas aberta?
2. Qual o processo para se tornar palestrante?
3. Tem prazo para submissao?
4. Qual contato ou link para se inscrever como palestrante?
5. Se nao tiver processo formal, qual a melhor estrategia para Abel conseguir falar nesse evento?

INFORMACOES ENCONTRADAS:
{contexto_palestra}

Retorne APENAS JSON valido:
{{
  "tem_call_for_speakers": true|false,
  "como_palestrar": "instrucoes claras e praticas em 2-3 frases",
  "contato": "email ou link de contato dos organizadores",
  "prazo_submissao": "data limite ou vazio",
  "link_inscricao_palestrante": "link direto ou vazio",
  "estrategia_recomendada": "o que Abel deve fazer especificamente para entrar como palestrante"
}}"""

    try:
        r = client.chat.completions.create(
            model=MODELO,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )
        resposta = r.choices[0].message.content.strip()
        resposta = re.sub(r"```json|```", "", resposta).strip()
        return json.loads(resposta)
    except Exception as e:
        print(f"  Erro ao analisar palestra: {e}")
        info_palestra["como_palestrar"] = "Erro ao buscar — verifique o site do evento"
        return info_palestra


# --------------------------------------------------
# FASE 4 — CALCULAR CUSTO-BENEFICIO (outras cidades)
# --------------------------------------------------

def calcular_custo_beneficio(evento: dict) -> dict:
    cidade = evento.get("cidade", "joao_pessoa")
    if cidade == "joao_pessoa":
        return {"vale_ir": True, "analise": "", "custo_estimado": 0}

    custo = CUSTO_VIAGEM.get(cidade, 200)
    publico = evento.get("publico_estimado", "desconhecido")
    potencial = evento.get("potencial_negocio", "baixo")
    categoria = evento.get("categoria", "outros")

    # Score de valor
    score_publico  = {"pequeno(<50)": 1, "medio(50-200)": 2, "grande(+200)": 3, "desconhecido": 1}.get(publico, 1)
    score_potencial = {"alto": 3, "medio": 2, "baixo": 1}.get(potencial, 1)
    score_categoria = 3 if categoria in ("tecnologia_ia", "negocios_empreend", "saude_clinicas") else 1
    score_total = score_publico + score_potencial + score_categoria  # max: 9

    # Decide se vale ir
    # Eventos pequenos de baixo potencial nao valem viagem
    if custo <= 100:
        vale_ir = score_total >= 4
    elif custo <= 200:
        vale_ir = score_total >= 6
    else:
        vale_ir = score_total >= 8

    if vale_ir:
        analise = (
            f"Vale a viagem! Custo estimado: R${custo}. "
            f"Publico {publico}, potencial de negocio {potencial}. "
            f"Oportunidade de networking e visibilidade justifica o investimento."
        )
    else:
        analise = (
            f"Custo R${custo} nao justifica para esse evento. "
            f"Publico {publico} e potencial {potencial} sao baixos demais. "
            f"Monitore para proximas edicoes quando tiver mais informacoes."
        )

    return {
        "vale_ir": vale_ir,
        "custo_estimado": custo,
        "analise": analise,
        "score": score_total,
    }


# --------------------------------------------------
# WHATSAPP
# --------------------------------------------------

def enviar_whatsapp(mensagem: str) -> bool:
    base_url = os.environ.get("EVOLUTION_API_URL", "").rstrip("/manager").rstrip("/")
    api_key  = os.environ.get("EVOLUTION_API_KEY")
    instance = os.environ.get("EVOLUTION_INSTANCE")
    numero   = os.environ.get("WHATSAPP_NUMERO_DESTINO")

    if not all([base_url, api_key, instance, numero]):
        print("WhatsApp nao configurado.")
        return False

    partes = dividir_mensagem(mensagem)
    for i, parte in enumerate(partes):
        try:
            r = httpx.post(
                f"{base_url}/message/sendText/{instance}",
                json={"number": numero, "text": parte},
                headers={"apikey": api_key, "Content-Type": "application/json"},
                timeout=15
            )
            if r.status_code in (200, 201):
                print(f"WhatsApp {i+1}/{len(partes)} enviado!")
            else:
                print(f"Erro Evolution: {r.status_code} — {r.text[:200]}")
                return False
        except Exception as e:
            print(f"Erro WhatsApp: {e}")
            return False
        if len(partes) > 1:
            time.sleep(2)
    return True


def dividir_mensagem(texto: str, limite: int = 3500) -> list:
    if len(texto) <= limite:
        return [texto]
    partes = []
    linhas = texto.split("\n")
    parte_atual = ""
    for linha in linhas:
        if len(parte_atual) + len(linha) + 1 > limite:
            if parte_atual:
                partes.append(parte_atual.strip())
            parte_atual = linha + "\n"
        else:
            parte_atual += linha + "\n"
    if parte_atual.strip():
        partes.append(parte_atual.strip())
    return partes


# --------------------------------------------------
# FORMATAR MENSAGEM
# --------------------------------------------------

EMOJI_CAT = {
    "tecnologia_ia":     "🤖",
    "marketing":         "📣",
    "negocios_empreend": "💼",
    "saude_clinicas":    "🏥",
    "outros":            "📌",
}
EMOJI_CIDADE = {
    "joao_pessoa":    "🏙️ JP",
    "campina_grande": "🏔️ CG",
    "recife":         "🌊 Recife",
    "natal":          "☀️ Natal",
}

def formatar_mensagem(eventos_com_analise: list) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")

    if not eventos_com_analise:
        return f"📅 *Eventos — {hoje}*\n\nNenhum evento novo hoje! 👍"

    # Separa por tipo
    com_palestra   = [e for e in eventos_com_analise if e.get("_palestra", {}).get("tem_call_for_speakers")]
    sem_call       = [e for e in eventos_com_analise
                      if not e.get("_palestra", {}).get("tem_call_for_speakers")
                      and e.get("potencial_negocio") in ("alto", "medio")
                      and e.get("cidade") == "joao_pessoa"]
    vale_viagem    = [e for e in eventos_com_analise
                      if e.get("cidade") != "joao_pessoa"
                      and e.get("_viagem", {}).get("vale_ir")]
    nao_vale       = [e for e in eventos_com_analise
                      if e.get("cidade") != "joao_pessoa"
                      and not e.get("_viagem", {}).get("vale_ir")]

    linhas = [f"📅 *Agenda — {hoje}*\n"]

    # Eventos com call for speakers aberto
    if com_palestra:
        linhas.append("🎤 *CALL FOR SPEAKERS ABERTO*")
        linhas.append("_Submeta sua proposta agora!_")
        linhas.append("─────────────────────")
        for ev in com_palestra:
            p = ev.get("_palestra", {})
            emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
            linhas.append(f"{emoji} *{ev.get('nome', '')}*")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            linhas.append(f"📍 {ev.get('local', '')} | {EMOJI_CIDADE.get(ev.get('cidade',''), '')}")
            linhas.append(f"👥 Publico: {ev.get('publico_estimado', 'desconhecido')}")
            linhas.append(f"\n📋 *Como palestrar:*")
            linhas.append(f"{p.get('como_palestrar', '')}")
            if p.get("prazo_submissao"):
                linhas.append(f"⏰ Prazo: {p['prazo_submissao']}")
            if p.get("link_inscricao_palestrante"):
                linhas.append(f"🔗 Inscrição: {p['link_inscricao_palestrante']}")
            elif p.get("contato"):
                linhas.append(f"📩 Contato: {p['contato']}")
            linhas.append(f"🌐 Evento: {ev.get('url', '')}")
            if ev.get("potencial_negocio") == "alto":
                linhas.append(f"💼 Negócio: {ev.get('motivo_negocio', '')}")
            linhas.append("")

    # Eventos sem call formal mas com estrategia
    if sem_call:
        linhas.append("🎯 *ESTRATEGIA PARA PALESTRAR*")
        linhas.append("_Sem call aberto — use a estrategia abaixo_")
        linhas.append("─────────────────────")
        for ev in sem_call[:4]:
            p = ev.get("_palestra", {})
            emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
            linhas.append(f"{emoji} *{ev.get('nome', '')}*")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            linhas.append(f"📍 {ev.get('local', '')} | {EMOJI_CIDADE.get(ev.get('cidade',''), '')}")
            linhas.append(f"💡 *Estrategia:* {p.get('estrategia_recomendada', '')}")
            if p.get("contato"):
                linhas.append(f"📩 Contato: {p['contato']}")
            linhas.append(f"🌐 {ev.get('url', '')}")
            if ev.get("potencial_negocio") == "alto":
                linhas.append(f"💼 {ev.get('motivo_negocio', '')}")
            linhas.append("")

    # Vale a viagem
    if vale_viagem:
        linhas.append("✈️ *VALE A VIAGEM*")
        linhas.append("─────────────────────")
        for ev in vale_viagem:
            v = ev.get("_viagem", {})
            emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
            cidade = EMOJI_CIDADE.get(ev.get("cidade", ""), "")
            linhas.append(f"{emoji} *{ev.get('nome', '')}* | {cidade}")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            linhas.append(f"💰 Custo viagem: ~R${v.get('custo_estimado', 0)}")
            linhas.append(f"📊 {v.get('analise', '')}")
            linhas.append(f"🌐 {ev.get('url', '')}")
            linhas.append("")

    # Nao vale viagem (resumido)
    if nao_vale:
        linhas.append("📋 *OUTRAS CIDADES (nao compensa agora)*")
        for ev in nao_vale[:3]:
            v = ev.get("_viagem", {})
            cidade = EMOJI_CIDADE.get(ev.get("cidade", ""), "")
            linhas.append(f"• {ev.get('nome', '')} | {cidade} | R${v.get('custo_estimado',0)} | {ev.get('data','')}")
        linhas.append("")

    linhas.append("_Agente de Eventos FluxIA 🤖_")
    return "\n".join(linhas)


# --------------------------------------------------
# PRINCIPAL
# --------------------------------------------------

def rodar_agente():
    hoje = datetime.now().strftime("%d/%m/%Y")
    print("=" * 50)
    print(f"Agente de Eventos — {hoje}")
    print("=" * 50)

    memoria = carregar_memoria()
    print(f"Memoria: {len(memoria)} eventos ja enviados\n")

    # FASE 1 — busca sem IA
    print("FASE 1: Buscando eventos...")
    resultados_brutos = buscar_todos_eventos()

    if not resultados_brutos:
        print("Nenhum resultado. Verifique TAVILY_API_KEY.")
        return

    # FASE 2 — extrai eventos (1 chamada IA)
    print("\nFASE 2: Extraindo eventos com IA...")
    eventos = extrair_eventos(resultados_brutos, hoje)
    print(f"Eventos extraidos: {len(eventos)}")

    if not eventos:
        print("Nenhum evento valido encontrado.")
        return

    # Filtra ja enviados
    novos = []
    for ev in eventos:
        ev_id = gerar_id(ev.get("url", "") or ev.get("nome", ""))
        if ev_id not in memoria:
            ev["_id"] = ev_id
            novos.append(ev)

    print(f"Novos: {len(novos)}")
    if not novos:
        enviar_whatsapp(f"📅 *Eventos JP — {hoje}*\n\nNenhum evento novo hoje! Todos ja foram enviados. 👍")
        return

    # FASE 3 — pesquisa como palestrar (1 chamada por evento relevante)
    print("\nFASE 3: Pesquisando como palestrar...")
    for ev in novos:
        potencial = ev.get("potencial_negocio", "baixo")
        categoria = ev.get("categoria", "outros")
        eh_relevante = potencial in ("alto", "medio") or categoria in ("tecnologia_ia", "negocios_empreend", "saude_clinicas")

        if eh_relevante:
            ev["_palestra"] = pesquisar_como_palestrar(ev)
        else:
            ev["_palestra"] = {
                "tem_call_for_speakers": False,
                "como_palestrar": "",
                "estrategia_recomendada": "",
                "contato": "",
            }
        time.sleep(1)

    # FASE 4 — calcula custo-beneficio viagem
    print("\nFASE 4: Calculando custo-beneficio de viagem...")
    for ev in novos:
        ev["_viagem"] = calcular_custo_beneficio(ev)

    # Formata e envia
    mensagem = formatar_mensagem(novos)

    caminho = f"relatorio_{datetime.now().strftime('%Y-%m-%d')}.txt"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(mensagem)
    print(f"\nSalvo: {caminho}")
    print(mensagem[:800])

    enviado = enviar_whatsapp(mensagem)

    # Atualiza memoria
    for ev in novos:
        memoria.add(ev["_id"])
    salvar_memoria(memoria)
    print(f"Memoria: {len(memoria)} eventos registrados")

    if not enviado:
        print("AVISO: WhatsApp nao enviado. Verifique Evolution API.")


if __name__ == "__main__":
    rodar_agente()
