
"""
Agente de Eventos — Joao Pessoa + Cidades Proximas
Arquitetura otimizada: busca tudo primeiro, depois chama IA UMA vez.
Resultado: 1-2 chamadas ao modelo em vez de 30-40.
"""

import os
import json
import hashlib
import httpx
import re
import time
from datetime import datetime
from openai import OpenAI

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY")

# Modelos em ordem — gratuitos primeiro, pago como garantia
MODELOS_FALLBACK = [
    os.environ.get("MODELO_IA", "qwen/qwen3-coder:free"),
    "minimax/minimax-m2.5:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1:free",
    "gpt-4o-mini",
]

client_openrouter = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
) if OPENROUTER_API_KEY else None

client_openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def get_client(modelo: str):
    if "gpt-" in modelo:
        if not client_openai:
            raise ValueError("OPENAI_API_KEY nao configurada")
        return client_openai
    if not client_openrouter:
        raise ValueError("OPENROUTER_API_KEY nao configurada")
    return client_openrouter


def chamar_ia(prompt: str, max_tokens: int = 3000) -> str:
    """Chama o modelo com fallback automatico entre todos os modelos."""
    for modelo in MODELOS_FALLBACK:
        try:
            print(f"Usando modelo: {modelo}")
            cli = get_client(modelo)
            r = cli.chat.completions.create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            erro = str(e)
            recuperavel = any(x in erro for x in [
                "429", "404", "400", "rate", "Rate", "upstream",
                "deprecated", "not found", "NotFound", "context_length",
                "maximum context", "too long", "overloaded"
            ])
            if recuperavel:
                print(f"Modelo {modelo} falhou ({erro[:80]}). Tentando proximo...")
                time.sleep(3)
                continue
            raise

    raise RuntimeError("Todos os modelos falharam.")


# --------------------------------------------------
# MEMORIA
# --------------------------------------------------

MEMORIA_PATH = "data/eventos_enviados.json"

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
# PERFIL
# --------------------------------------------------

PERFIL = """
Abel — dono da FluxIA (agencia de IA)
Cria: agentes de atendimento, sistemas SaaS, APIs, automacoes para clinicas
Quer: palestrar, fazer networking, vender IA para clinicas e empresas
Publico-alvo: donos de clinicas (odonto, estetica, medica), empreendedores
"""

CIDADES = [
    {"nome": "Joao Pessoa", "uf": "PB", "criterio": "todos os eventos relevantes"},
    {"nome": "Campina Grande", "uf": "PB", "criterio": "tecnologia, negocios, inovacao"},
    {"nome": "Recife", "uf": "PE", "criterio": "apenas grandes eventos +200 pessoas"},
    {"nome": "Natal", "uf": "RN", "criterio": "eventos grandes ou com oportunidade de palestra"},
]

QUERIES = [
    # JP — plataformas
    "eventos Joao Pessoa PB 2026 site:sympla.com.br",
    "eventos Joao Pessoa PB 2026 site:even3.com.br",
    "eventos Joao Pessoa PB 2026 site:doity.com.br",
    "eventos Joao Pessoa 2026 site:eventbrite.com.br",
    # JP — categorias
    "workshop inteligencia artificial Joao Pessoa 2026",
    "evento tecnologia startups Joao Pessoa 2026",
    "evento marketing digital Joao Pessoa 2026",
    "evento empreendedorismo negocios Joao Pessoa 2026",
    "congresso odontologia Paraiba 2026",
    "evento clinicas saude estetica Joao Pessoa 2026",
    # JP — entidades
    "evento SEBRAE Paraiba Joao Pessoa 2026",
    "evento ACIPB CDL Joao Pessoa 2026",
    "evento CRO CRM Paraiba 2026",
    "startup PB inovacao evento 2026",
    "evento SENAC Joao Pessoa 2026",
    # Outras cidades
    "evento tecnologia IA Recife 2026 site:sympla.com.br",
    "summit conferencia Recife PE 2026",
    "evento tecnologia Campina Grande PB 2026",
    "evento empreendedorismo Natal RN 2026",
    "congresso saude clinicas Nordeste 2026",
]


# --------------------------------------------------
# FASE 1 — BUSCA (sem IA, so Tavily)
# --------------------------------------------------

def buscar_todos_eventos() -> list[dict]:
    """Faz todas as buscas via Tavily e retorna lista de resultados brutos."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        print("AVISO: TAVILY_API_KEY nao configurada")
        return []

    todos = []
    for i, query in enumerate(QUERIES):
        print(f"  [{i+1}/{len(QUERIES)}] {query[:60]}")
        try:
            r = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 5,
                },
                timeout=15
            )
            resultados = r.json().get("results", [])
            for res in resultados:
                todos.append({
                    "titulo": res.get("title", "")[:100],
                    "url":    res.get("url", ""),
                    "resumo": res.get("content", "")[:200],
                    "query":  query,
                })
        except Exception as e:
            print(f"  Erro na busca: {e}")

        time.sleep(0.5)  # respeita rate limit da Tavily

    print(f"Total de resultados brutos: {len(todos)}")
    return todos


# --------------------------------------------------
# FASE 2 — ANALISE (1 chamada a IA)
# --------------------------------------------------

def analisar_com_ia(resultados_brutos: list, hoje: str) -> list:
    """
    Envia TODOS os resultados de uma vez para a IA analisar.
    Uma unica chamada em vez de 30-40.
    """
    if not resultados_brutos:
        return []

    # Monta contexto compacto
    contexto = "\n".join([
        f"- {r['titulo']} | {r['url']} | {r['resumo'][:100]}"
        for r in resultados_brutos[:80]  # limita para nao estourar contexto
    ])

    prompt = f"""Hoje e {hoje}. Analise esses resultados de busca e extraia eventos reais.

PERFIL DE QUEM VAI RECEBER:
{PERFIL}

RESULTADOS BRUTOS:
{contexto}

INSTRUCOES:
1. Extraia apenas eventos FUTUROS (data apos {hoje})
2. Inclua apenas eventos em JP, Campina Grande, Recife ou Natal
3. Descarte noticias, artigos e resultados que nao sejam eventos
4. Para cada evento avalie oportunidade de palestra para Abel (alta/media/baixa/nenhuma)
5. Avalie se e oportunidade de negocio (vender IA para os participantes)

Retorne APENAS um JSON valido, sem markdown, sem explicacoes:
[
  {{
    "nome": "nome do evento",
    "data": "DD/MM/AAAA ou vazio",
    "local": "local ou Online",
    "cidade": "joao_pessoa|campina_grande|recife|natal",
    "resumo": "2 frases sobre o evento",
    "preco": "Gratuito ou R$ valor ou A confirmar",
    "url": "url do evento",
    "categoria": "tecnologia_ia|marketing|negocios_empreend|saude_clinicas|outros",
    "palestra": "alta|media|baixa|nenhuma",
    "motivo_palestra": "por que e ou nao uma oportunidade",
    "negocio": "alta|media|baixa",
    "motivo_negocio": "quem estara la e por que Abel pode vender"
  }}
]"""

    print("Chamando IA para analisar...")
    resposta = chamar_ia(prompt, max_tokens=4000)

    # Limpa markdown se vier
    resposta = re.sub(r"```json|```", "", resposta).strip()

    # Extrai JSON
    try:
        match = re.search(r"\[.*\]", resposta, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(resposta)
    except Exception as e:
        print(f"Erro ao parsear resposta da IA: {e}")
        print(f"Resposta recebida: {resposta[:300]}")
        return []


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

def formatar_mensagem(eventos: list, total_bruto: int) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")

    if not eventos:
        return f"📅 *Eventos — {hoje}*\n\nNenhum evento novo hoje! 👍"

    # Separa palestras de destaque
    palestras = [e for e in eventos if e.get("palestra") in ("alta", "media")]
    negocios  = [e for e in eventos if e.get("negocio") == "alta"]
    jp        = [e for e in eventos if e.get("cidade") == "joao_pessoa"]
    fora      = [e for e in eventos if e.get("cidade") != "joao_pessoa"]

    linhas = [f"📅 *Agenda — {hoje}*"]
    linhas.append(f"_{len(eventos)} eventos novos | {len(palestras)} oportunidades de palestra_\n")

    # Oportunidades de palestra
    if palestras:
        linhas.append("🎤 *PARA PALESTRAR*")
        linhas.append("─────────────────")
        for ev in palestras[:5]:
            linhas.append(f"🎤 *{ev.get('nome', '')}*")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            linhas.append(f"📍 {ev.get('local', '')} | {EMOJI_CIDADE.get(ev.get('cidade',''), '')}")
            linhas.append(f"💡 {ev.get('motivo_palestra', '')}")
            linhas.append(f"🔗 {ev.get('url', '')}")
            linhas.append("")

    # Oportunidades de negocio
    if negocios:
        linhas.append("💼 *OPORTUNIDADES DE NEGOCIO*")
        linhas.append("─────────────────")
        for ev in negocios[:5]:
            emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
            linhas.append(f"{emoji} *{ev.get('nome', '')}*")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            linhas.append(f"📍 {ev.get('local', '')} | {EMOJI_CIDADE.get(ev.get('cidade',''), '')}")
            linhas.append(f"🤝 {ev.get('motivo_negocio', '')}")
            linhas.append(f"🔗 {ev.get('url', '')}")
            linhas.append("")

    # Eventos JP
    outros_jp = [e for e in jp if e not in palestras and e not in negocios]
    if outros_jp:
        linhas.append("🏙️ *JOAO PESSOA*")
        linhas.append("─────────────────")
        for ev in outros_jp[:8]:
            emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
            linhas.append(f"{emoji} *{ev.get('nome', '')}*")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            if ev.get("local"): linhas.append(f"📍 {ev['local']}")
            linhas.append(f"💬 {ev.get('resumo', '')}")
            linhas.append(f"💰 {ev.get('preco', 'A confirmar')}")
            linhas.append(f"🔗 {ev.get('url', '')}")
            linhas.append("")

    # Outras cidades
    if fora:
        linhas.append("✈️ *VALE A VIAGEM*")
        linhas.append("─────────────────")
        for ev in fora[:5]:
            emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
            cidade = EMOJI_CIDADE.get(ev.get("cidade", ""), "")
            linhas.append(f"{emoji} *{ev.get('nome', '')}* | {cidade}")
            if ev.get("data"):  linhas.append(f"📆 {ev['data']}")
            linhas.append(f"💬 {ev.get('resumo', '')}")
            linhas.append(f"🔗 {ev.get('url', '')}")
            linhas.append("")

    linhas.append("_Agente de Eventos 🤖_")
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
        print("Nenhum resultado de busca. Verifique TAVILY_API_KEY.")
        return

    # FASE 2 — analise com IA (1 chamada)
    print("\nFASE 2: Analisando com IA...")
    eventos = analisar_com_ia(resultados_brutos, hoje)
    print(f"Eventos extraidos: {len(eventos)}")

    if not eventos:
        print("IA nao retornou eventos validos.")
        return

    # Filtra ja enviados
    novos = []
    for ev in eventos:
        ev_id = gerar_id(ev.get("url", "") or ev.get("nome", ""))
        if ev_id not in memoria:
            ev["_id"] = ev_id
            novos.append(ev)

    print(f"Novos: {len(novos)}")

    # Formata e envia
    mensagem = formatar_mensagem(novos, len(resultados_brutos))

    caminho = f"relatorio_{datetime.now().strftime('%Y-%m-%d')}.txt"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(mensagem)
    print(f"Salvo: {caminho}")
    print(mensagem[:600])

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
