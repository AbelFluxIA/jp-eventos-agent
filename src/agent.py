"""
Agente de Eventos — Joao Pessoa + Cidades Proximas
- Busca eventos relevantes para quem quer palestrar e fazer networking
- Analisa oportunidades de palestra em cada evento
- Cobre JP + cidades proximas com filtro de qualidade
- Envia via WhatsApp com classificacao de oportunidade
"""

import os
import json
import hashlib
import httpx
import re
from datetime import datetime
from openai import OpenAI

# OpenRouter — compativel com API OpenAI
# Usa modelo gratuito (Qwen3.6 Plus) com fallback para gpt-4o-mini
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY")

if OPENROUTER_API_KEY:
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    MODELO = os.environ.get("MODELO_IA", "qwen/qwen3.6-plus:free")
    print(f"Usando OpenRouter: {MODELO}")
else:
    client = OpenAI(api_key=OPENAI_API_KEY)
    MODELO = "gpt-4o-mini"
    print("Usando OpenAI: gpt-4o-mini")

MEMORIA_PATH = "data/eventos_enviados.json"

# --------------------------------------------------
# PERFIL DO USUARIO (personaliza as analises)
# --------------------------------------------------

PERFIL = """
Nome: Abel
Empresa: Agencia de IA (FluxIA)
O que faz: Cria agentes de IA personalizados para atendimento, clinicas medicas/odonto/estetica,
           sistemas SaaS, APIs, automacoes inteligentes
Quer: Comecar a palestrar, construir autoridade, fazer networking qualificado
Publico-alvo: Donos de clinicas, empreendedores, profissionais de saude, empresarios locais
Diferenciais: Agentes que parecem humanos, IA aplicada a negocios reais no Nordeste
"""

# --------------------------------------------------
# CIDADES — JP e proximas (com criterio de qualidade)
# --------------------------------------------------

CIDADES = {
    "joao_pessoa": {
        "nome": "Joao Pessoa, PB",
        "criterio": "todos os eventos relevantes",
        "distancia": 0,
    },
    "campina_grande": {
        "nome": "Campina Grande, PB",
        "criterio": "eventos de tecnologia, inovacao, negocios e saude com boa estrutura",
        "distancia": 130,
    },
    "recife": {
        "nome": "Recife, PE",
        "criterio": "apenas eventos de grande porte: conferencias, summits, congressos com mais de 200 pessoas",
        "distancia": 120,
    },
    "natal": {
        "nome": "Natal, RN",
        "criterio": "apenas eventos de grande porte ou com oportunidade clara de palestra",
        "distancia": 185,
    },
    "fortaleza": {
        "nome": "Fortaleza, CE",
        "criterio": "apenas eventos excepcionais — grandes conferencias nacionais com edicao local",
        "distancia": 500,
    },
}


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

def gerar_id_evento(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


# --------------------------------------------------
# TOOLS
# --------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_eventos_web",
            "description": "Busca eventos por cidade e categoria via Tavily.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "cidade": {
                        "type": "string",
                        "description": "Ex: joao_pessoa, campina_grande, recife, natal, fortaleza"
                    }
                },
                "required": ["query", "cidade"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "acessar_pagina_evento",
            "description": "Acessa pagina do evento para extrair preco, data, local e informacoes sobre palestrantes/call for papers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalizar_e_enviar",
            "description": "Finaliza e envia os eventos encontrados. So chame apos todas as buscas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "eventos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome":     {"type": "string"},
                                "data":     {"type": "string"},
                                "local":    {"type": "string"},
                                "cidade":   {"type": "string", "description": "Ex: joao_pessoa, recife, natal..."},
                                "resumo":   {"type": "string"},
                                "preco":    {"type": "string"},
                                "url":      {"type": "string"},
                                "categoria": {
                                    "type": "string",
                                    "enum": ["tecnologia_ia", "marketing", "negocios_empreend", "saude_clinicas", "outros"]
                                },
                                "oportunidade_palestra": {
                                    "type": "string",
                                    "enum": ["alta", "media", "baixa", "nenhuma"],
                                    "description": "Chance de Abel conseguir palestrar nesse evento"
                                },
                                "motivo_palestra": {
                                    "type": "string",
                                    "description": "Por que e uma boa ou nao oportunidade de palestra para Abel"
                                },
                                "score_evento": {
                                    "type": "integer",
                                    "description": "Score de 0-10 considerando tamanho, publico-alvo e networking"
                                }
                            },
                            "required": ["nome", "resumo", "url", "categoria", "cidade",
                                        "oportunidade_palestra", "score_evento"]
                        }
                    }
                },
                "required": ["eventos"]
            }
        }
    }
]


# --------------------------------------------------
# EXECUTORES
# --------------------------------------------------

def buscar_eventos_web(query: str, cidade: str = "joao_pessoa") -> str:
    try:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return f"[SEM TAVILY_API_KEY] Query: {query}"

        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
            },
            timeout=20
        )
        resultados = r.json().get("results", [])
        if not resultados:
            return f"Sem resultados para: {query}"

        saida = []
        for res in resultados:
            saida.append(
                f"Titulo: {res.get('title', '')}\n"
                f"URL: {res.get('url', '')}\n"
                f"Conteudo: {res.get('content', '')[:250]}\n"
            )
        return "\n---\n".join(saida)

    except Exception as e:
        return f"Erro na busca: {e}"


def acessar_pagina_evento(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; EventBot/1.0)"}
        r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        texto = re.sub(r"<style[^>]*>.*?</style>", " ", r.text, flags=re.DOTALL)
        texto = re.sub(r"<script[^>]*>.*?</script>", " ", texto, flags=re.DOTALL)
        texto = re.sub(r"<[^>]+>", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()
        return texto[:1200]
    except Exception as e:
        return f"Nao foi possivel acessar: {e}"


def executar_tool(nome: str, args: dict) -> str:
    if nome == "buscar_eventos_web":
        return buscar_eventos_web(args["query"], args.get("cidade", "joao_pessoa"))
    if nome == "acessar_pagina_evento":
        return acessar_pagina_evento(args["url"])
    return "Tool nao encontrada."


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

    # Divide mensagens longas (WhatsApp tem limite)
    partes = dividir_mensagem(mensagem, limite=3500)

    for i, parte in enumerate(partes):
        try:
            r = httpx.post(
                f"{base_url}/message/sendText/{instance}",
                json={"number": numero, "text": parte},
                headers={"apikey": api_key, "Content-Type": "application/json"},
                timeout=15
            )
            if r.status_code in (200, 201):
                print(f"WhatsApp parte {i+1}/{len(partes)} enviada!")
            else:
                print(f"Erro Evolution API: {r.status_code} — {r.text[:300]}")
                return False
        except Exception as e:
            print(f"Erro ao enviar WhatsApp: {e}")
            return False
        if len(partes) > 1:
            import time
            time.sleep(2)

    return True


def dividir_mensagem(texto: str, limite: int = 3500) -> list:
    """Divide mensagem longa em partes menores."""
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

EMOJI_PALESTRA = {
    "alta":   "🎤⭐",
    "media":  "🎤",
    "baixa":  "👀",
    "nenhuma": "",
}

EMOJI_CIDADE = {
    "joao_pessoa":    "🏙️ JP",
    "campina_grande": "🏔️ CG",
    "recife":         "🌊 Recife",
    "natal":          "☀️ Natal",
    "fortaleza":      "🦞 Fortaleza",
}


def formatar_mensagem(eventos_novos: list, total: int) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")

    if not eventos_novos:
        return (
            f"📅 *Eventos — {hoje}*\n\n"
            "Nenhum evento novo hoje. Todos ja foram enviados! 👍"
        )

    # Separa por cidade e ordena por score
    jp = sorted([e for e in eventos_novos if e.get("cidade") == "joao_pessoa"],
                key=lambda x: x.get("score_evento", 0), reverse=True)
    fora = sorted([e for e in eventos_novos if e.get("cidade") != "joao_pessoa"],
                  key=lambda x: x.get("score_evento", 0), reverse=True)

    # Separa oportunidades de palestra
    palestras = [e for e in eventos_novos if e.get("oportunidade_palestra") in ("alta", "media")]

    linhas = [f"📅 *Agenda de Eventos — {hoje}*"]
    linhas.append(f"_{len(eventos_novos)} novos | {len(palestras)} oportunidades de palestra_\n")

    # Oportunidades de palestra em destaque
    if palestras:
        linhas.append("🎤 *OPORTUNIDADES PARA PALESTRAR*")
        linhas.append("─────────────────────")
        for ev in palestras:
            emoji_p = EMOJI_PALESTRA.get(ev.get("oportunidade_palestra", ""), "")
            linhas.append(f"{emoji_p} *{ev.get('nome', '')}*")
            linhas.append(f"📍 {ev.get('local', '')} | {EMOJI_CIDADE.get(ev.get('cidade', ''), '')}")
            if ev.get("data"): linhas.append(f"📆 {ev.get('data')}")
            linhas.append(f"💡 {ev.get('motivo_palestra', '')}")
            linhas.append(f"🔗 {ev.get('url', '')}")
            linhas.append("")

    # Eventos de JP
    if jp:
        linhas.append("🏙️ *JOAO PESSOA*")
        linhas.append("─────────────────────")
        for ev in jp:
            _adicionar_evento(linhas, ev)

    # Eventos de outras cidades
    if fora:
        linhas.append("✈️ *VALE A VIAGEM*")
        linhas.append("─────────────────────")
        for ev in fora:
            cidade_label = EMOJI_CIDADE.get(ev.get("cidade", ""), ev.get("cidade", ""))
            linhas.append(f"📍 *{cidade_label}*")
            _adicionar_evento(linhas, ev)

    linhas.append("_Agente de Eventos 🤖_")
    return "\n".join(linhas)


def _adicionar_evento(linhas: list, ev: dict):
    emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
    score = ev.get("score_evento", 0)
    estrelas = "⭐" * min(score // 3, 3) if score >= 7 else ""

    linhas.append(f"{emoji} *{ev.get('nome', '')}* {estrelas}")
    if ev.get("data"):  linhas.append(f"📆 {ev.get('data')}")
    if ev.get("local"): linhas.append(f"📍 {ev.get('local')}")
    linhas.append(f"💬 {ev.get('resumo', '')}")
    linhas.append(f"💰 {ev.get('preco', 'A confirmar')}")
    if ev.get("url"):   linhas.append(f"🔗 {ev.get('url')}")
    linhas.append("")


# --------------------------------------------------
# SYSTEM PROMPT
# --------------------------------------------------

SYSTEM_PROMPT = f"""Voce e um agente especializado em descobrir eventos relevantes para Abel,
dono de uma agencia de IA no Nordeste do Brasil.

PERFIL DO ABEL:
{PERFIL}

MISSAO:
1. Encontrar eventos relevantes em JP e cidades proximas
2. Avaliar cada evento como oportunidade de palestra para Abel
3. Classificar eventos de fora de JP apenas se valerem a viagem

CIDADES E CRITERIOS:
- Joao Pessoa/PB: todos os eventos relevantes (tecnologia, IA, negocios, saude, marketing)
- Campina Grande/PB (130km): eventos de tech, inovacao e negocios com boa estrutura
- Recife/PE (120km): apenas conferencias e summits de grande porte (+200 pessoas)
- Natal/RN (185km): apenas eventos grandes OU com clara oportunidade de palestra
- Fortaleza/CE (500km): apenas eventos excepcionais — grandes conferencias nacionais

ANALISE DE OPORTUNIDADE DE PALESTRA:
Para cada evento, avalie se Abel pode palestrar considerando:
- O evento aceita propostas de palestra? (call for papers, call for speakers)
- O publico e o mesmo que Abel atende? (empreendedores, clinicas, tech)
- O tema de Abel (IA aplicada a negocios) se encaixa na programacao?
- E um evento de networking onde Abel pode se apresentar como especialista?

Classifique:
- ALTA: evento claramente alinhado, aceita palestrantes externos, publico ideal
- MEDIA: evento relevante, possibilidade de networking ou abordagem futura
- BAIXA: evento de networking mas publico parcialmente alinhado
- NENHUMA: evento tecnico fechado ou publico nao relacionado

BUSCA — faca no minimo 30 buscas:
PLATAFORMAS: site:sympla.com.br, site:even3.com.br, site:doity.com.br, site:eventbrite.com.br, site:meetup.com
ENTIDADES JP: SEBRAE PB, ACIPB, Startup PB, CRO-PB, CRM-PB, UFPB, SENAC, CDL JP
ENTIDADES RECIFE: Porto Digital, SEBRAE PE, ACPE, eventos Recife Criativo
ENTIDADES NATAL: SEBRAE RN, eventos tecnologia Natal
CATEGORIAS: tecnologia, IA, marketing, empreendedorismo, negocios, saude, clinicas, odontologia, estetica

REGRAS:
1. APENAS eventos futuros — descarte passados
2. Para eventos fora de JP, acesse a pagina para confirmar porte e relevancia
3. Busque informacoes sobre como se tornar palestrante em cada evento
4. Score 0-10 considerando: tamanho do evento, alinhamento com perfil de Abel, qualidade do networking

So chame finalizar_e_enviar apos completar TODAS as buscas."""


# --------------------------------------------------
# LOOP PRINCIPAL
# --------------------------------------------------

def rodar_agente():
    hoje = datetime.now().strftime("%d/%m/%Y")
    print("=" * 50)
    print(f"Agente de Eventos — {hoje}")
    print("=" * 50)

    memoria = carregar_memoria()
    print(f"Memoria: {len(memoria)} eventos ja enviados\n")

    mensagens = [{
        "role": "user",
        "content": (
            f"Hoje e {hoje}. Busque eventos para os proximos 90 dias em "
            f"Joao Pessoa, Campina Grande, Recife, Natal e Fortaleza. "
            f"Para JP busque tudo. Para outras cidades aplique o criterio de qualidade. "
            f"Analise cada evento como oportunidade de palestra para Abel. "
            f"Faca no minimo 30 buscas. Acesse paginas dos eventos para confirmar detalhes. "
            f"DESCARTE eventos com data anterior a hoje ({hoje})."
        )
    }]

    iteracoes = 0

    while iteracoes < 40:
        iteracoes += 1

        resposta = client.chat.completions.create(
            model=MODELO,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + mensagens,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
        )

        msg = resposta.choices[0].message
        mensagens.append(msg)

        if not msg.tool_calls:
            print("Agente finalizou.")
            break

        for tc in msg.tool_calls:
            nome = tc.function.name
            args = json.loads(tc.function.arguments)

            if nome == "finalizar_e_enviar":
                eventos = args.get("eventos", [])
                print(f"\nTotal encontrado: {len(eventos)} eventos")

                # Filtra eventos passados
                hoje_dt = datetime.now().date()
                futuros = []
                for ev in eventos:
                    data_str = ev.get("data", "")
                    futuro = True
                    if data_str:
                        match = re.search(r"(\d{2})/(\d{2})/(\d{4})", data_str)
                        if match:
                            try:
                                from datetime import date
                                d = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                                futuro = d >= hoje_dt
                            except Exception:
                                pass
                    if futuro:
                        futuros.append(ev)
                    else:
                        print(f"Descartado (passado): {ev.get('nome')} — {data_str}")

                print(f"Futuros: {len(futuros)}")

                # Filtra ja enviados
                novos = []
                for ev in futuros:
                    ev_id = gerar_id_evento(ev.get("url", "") or ev.get("nome", ""))
                    if ev_id not in memoria:
                        ev["_id"] = ev_id
                        novos.append(ev)

                print(f"Novos: {len(novos)}")

                # Conta oportunidades de palestra
                palestras = [e for e in novos if e.get("oportunidade_palestra") in ("alta", "media")]
                print(f"Oportunidades de palestra: {len(palestras)}")

                mensagem = formatar_mensagem(novos, len(eventos))

                # Salva arquivo
                caminho = f"relatorio_{datetime.now().strftime('%Y-%m-%d')}.txt"
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(mensagem)
                print(f"Salvo: {caminho}")
                print(mensagem[:800])

                enviar_whatsapp(mensagem)

                for ev in novos:
                    memoria.add(ev["_id"])
                salvar_memoria(memoria)
                print(f"Memoria: {len(memoria)} eventos registrados")

                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Enviado. {len(novos)} novos, {len(palestras)} oportunidades de palestra."
                })
                return

            else:
                print(f"Buscando: {args.get('query', args.get('url', ''))[:80]}")
                resultado = executar_tool(nome, args)
                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": resultado
                })


if __name__ == "__main__":
    rodar_agente()
