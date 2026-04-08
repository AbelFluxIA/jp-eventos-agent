"""
Agente de Eventos — João Pessoa, PB
- Busca diária de eventos com OpenAI GPT-4o
- Envia via WhatsApp (Evolution API)
- Memória de eventos já enviados (sem repetição)
- Cobre: tech, IA, marketing, negócios, empreendedorismo, saúde/clínicas
"""

import os
import json
import hashlib
import httpx
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ─────────────────────────────────────────────
# MEMÓRIA DE EVENTOS (evita repetição)
# ─────────────────────────────────────────────

MEMORIA_PATH = "data/eventos_enviados.json"

def carregar_memoria() -> set:
    """Carrega IDs de eventos já enviados."""
    try:
        with open(MEMORIA_PATH, "r") as f:
            data = json.load(f)
            return set(data.get("enviados", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def salvar_memoria(enviados: set):
    """Salva IDs de eventos enviados."""
    os.makedirs("data", exist_ok=True)
    with open(MEMORIA_PATH, "w") as f:
        json.dump({"enviados": list(enviados)}, f, indent=2)

def gerar_id_evento(url: str) -> str:
    """Gera ID único para um evento baseado na URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────
# TOOLS (OpenAI function calling)
# ─────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_eventos_web",
            "description": (
                "Busca eventos em João Pessoa via Tavily. "
                "Use queries específicas para cada categoria e plataforma. "
                "Exemplos de queries eficazes:\n"
                "- 'eventos tecnologia IA João Pessoa 2025 site:sympla.com.br'\n"
                "- 'workshop marketing digital João Pessoa abril 2025'\n"
                "- 'eventos odontologia clínicas João Pessoa 2025'\n"
                "- 'networking empreendedorismo João Pessoa 2025 eventbrite'\n"
                "Faça pelo menos 10-12 buscas cobrindo todas as categorias."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query de busca específica"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalizar_e_enviar",
            "description": (
                "Finaliza a pesquisa e envia os eventos encontrados via WhatsApp. "
                "Chame esta função quando tiver feito todas as buscas necessárias."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventos": {
                        "type": "array",
                        "description": "Lista de eventos encontrados",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome": {"type": "string", "description": "Nome do evento"},
                                "data": {"type": "string", "description": "Data e horário (ex: 15/05/2025 às 19h)"},
                                "local": {"type": "string", "description": "Local ou 'Online'"},
                                "resumo": {"type": "string", "description": "2-3 frases sobre o evento"},
                                "preco": {"type": "string", "description": "Gratuito / R$ XX / Sob consulta"},
                                "url": {"type": "string", "description": "Link direto para o evento"},
                                "categoria": {
                                    "type": "string",
                                    "enum": ["tecnologia_ia", "marketing", "negocios_empreend", "saude_clinicas", "outros"]
                                }
                            },
                            "required": ["nome", "resumo", "url", "categoria"]
                        }
                    }
                },
                "required": ["eventos"]
            }
        }
    }
]


# ─────────────────────────────────────────────
# EXECUTOR DE TOOLS
# ─────────────────────────────────────────────

def buscar_eventos_web(query: str) -> str:
    """Busca eventos usando Tavily API."""
    try:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return _mock_busca(query)

        response = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": 8,
                "include_answer": False,
            },
            timeout=20
        )
        data = response.json()
        resultados = data.get("results", [])

        if not resultados:
            return f"Sem resultados para: {query}"

        saida = []
        for r in resultados:
            saida.append(
                f"Título: {r.get('title', '')}\n"
                f"URL: {r.get('url', '')}\n"
                f"Conteúdo: {r.get('content', '')[:500]}\n"
            )
        return "\n---\n".join(saida)

    except Exception as e:
        return f"Erro na busca '{query}': {str(e)}"


def _mock_busca(query: str) -> str:
    return (
        f"[MODO TESTE — configure TAVILY_API_KEY para buscas reais]\n"
        f"Query: '{query}'\n\n"
        "Resultado simulado:\n"
        "Título: Tech Summit JP 2025\n"
        "URL: https://sympla.com.br/tech-summit-jp\n"
        "Conteúdo: Maior evento de tecnologia da Paraíba. Palestras sobre IA, "
        "startups e inovação. 20/05/2025 às 8h. Centro de Convenções JP. Gratuito.\n"
    )


def executar_tool(nome: str, args: dict) -> str:
    if nome == "buscar_eventos_web":
        return buscar_eventos_web(args["query"])
    return "Tool não encontrada."


# ─────────────────────────────────────────────
# WHATSAPP via Evolution API
# ─────────────────────────────────────────────

def enviar_whatsapp(mensagem: str) -> bool:
    """Envia mensagem via Evolution API."""
    base_url = os.environ.get("EVOLUTION_API_URL")       # ex: https://evolution.seusite.com
    api_key  = os.environ.get("EVOLUTION_API_KEY")
    instance = os.environ.get("EVOLUTION_INSTANCE")      # nome da instância criada
    numero   = os.environ.get("WHATSAPP_NUMERO_DESTINO") # ex: 5583999998888

    if not all([base_url, api_key, instance, numero]):
        print("⚠️  Variáveis do WhatsApp não configuradas. Mensagem salva em arquivo.")
        return False

    try:
        url = f"{base_url}/message/sendText/{instance}"
        headers = {"apikey": api_key, "Content-Type": "application/json"}
        payload = {
            "number": numero,
            "text": mensagem
        }
        r = httpx.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code in (200, 201):
            print("✅ WhatsApp enviado com sucesso!")
            return True
        else:
            print(f"❌ Erro Evolution API: {r.status_code} — {r.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Erro ao enviar WhatsApp: {e}")
        return False


# ─────────────────────────────────────────────
# FORMATAR MENSAGEM WHATSAPP
# ─────────────────────────────────────────────

EMOJI_CATEGORIA = {
    "tecnologia_ia":      "🤖",
    "marketing":          "📣",
    "negocios_empreend":  "💼",
    "saude_clinicas":     "🏥",
    "outros":             "📌",
}

def formatar_mensagem_wpp(eventos_novos: list, total_encontrados: int) -> str:
    """Formata a mensagem de WhatsApp com os eventos novos."""
    hoje = datetime.now().strftime("%d/%m/%Y")

    if not eventos_novos:
        return (
            f"📅 *Eventos JP — {hoje}*\n\n"
            "Nenhum evento novo encontrado hoje. "
            "Todos os eventos já foram enviados anteriormente! 👍"
        )

    linhas = [f"📅 *Eventos JP — {hoje}*"]
    linhas.append(f"_{len(eventos_novos)} novos de {total_encontrados} encontrados_\n")

    for i, ev in enumerate(eventos_novos, 1):
        emoji = EMOJI_CATEGORIA.get(ev.get("categoria", "outros"), "📌")
        nome    = ev.get("nome", "Sem nome")
        data    = ev.get("data", "Data a confirmar")
        local   = ev.get("local", "Local a confirmar")
        resumo  = ev.get("resumo", "")
        preco   = ev.get("preco", "A confirmar")
        url     = ev.get("url", "")

        linhas.append(f"{emoji} *{nome}*")
        if data  != "Data a confirmar":  linhas.append(f"📆 {data}")
        if local != "Local a confirmar": linhas.append(f"📍 {local}")
        linhas.append(f"💬 {resumo}")
        linhas.append(f"💰 {preco}")
        if url: linhas.append(f"🔗 {url}")
        linhas.append("")  # linha em branco entre eventos

    linhas.append("_Agente de Eventos JP 🤖_")
    return "\n".join(linhas)


# ─────────────────────────────────────────────
# LOOP DO AGENTE
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um agente especializado em descobrir eventos em João Pessoa, PB, Brasil.

Seu objetivo é encontrar eventos relevantes para:
1. Profissionais de tecnologia e IA
2. Profissionais de marketing digital
3. Empreendedores e donos de negócios
4. Profissionais da área de saúde (médicos, dentistas, esteticistas, donos de clínicas)

Categorias para buscar (faça buscas em TODAS):
🤖 Tecnologia e IA: eventos de IA, programação, tech, inovação, startups
📣 Marketing: marketing digital, social media, growth, copywriting
💼 Negócios: empreendedorismo, gestão, liderança, vendas, finanças
🏥 Saúde/Clínicas: odontologia, medicina estética, fisioterapia, clínicas em geral

Plataformas para buscar (use site: nas queries):
- site:sympla.com.br
- site:eventbrite.com.br
- site:even3.com.br
- site:doity.com.br
- site:ingresse.com
- Também busque sem filtro de site para pegar eventos em sites próprios

Faça no MÍNIMO 12 buscas cobrindo todas as combinações de categoria + plataforma.
Seja exaustivo. Prefira mais buscas a menos.

Para cada evento encontrado, extraia:
- Nome completo
- Data e horário (se disponível)
- Local (endereço ou 'Online')
- Resumo em 2-3 frases diretas
- Preço (Gratuito / valor / Sob consulta)
- URL direta do evento

Quando terminar todas as buscas, chame finalizar_e_enviar com a lista completa."""


def rodar_agente():
    hoje = datetime.now().strftime("%d/%m/%Y")
    print(f"\n{'='*50}")
    print(f"🤖 Agente de Eventos JP — {hoje}")
    print(f"{'='*50}\n")

    memoria = carregar_memoria()
    print(f"📂 Memória: {len(memoria)} eventos já enviados anteriormente\n")

    mensagens = [
        {
            "role": "user",
            "content": (
                f"Hoje é {hoje}. Busque TODOS os eventos em João Pessoa, PB "
                f"para os próximos 45 dias. "
                f"Cubra todas as categorias: tecnologia, IA, marketing, negócios, "
                f"empreendedorismo, saúde e clínicas. "
                f"Use queries específicas por categoria E por plataforma (sympla, eventbrite, etc). "
                f"Seja exaustivo."
            )
        }
    ]

    eventos_finais = []
    iteracoes = 0
    max_iteracoes = 20

    while iteracoes < max_iteracoes:
        iteracoes += 1

        resposta = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + mensagens,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )

        msg = resposta.choices[0].message
        mensagens.append(msg)

        # Terminou sem chamar tool
        if not msg.tool_calls:
            print("✅ Agente finalizou.")
            break

        # Processa tool calls
        for tc in msg.tool_calls:
            nome = tc.function.name
            args = json.loads(tc.function.arguments)

            if nome == "finalizar_e_enviar":
                eventos_finais = args.get("eventos", [])
                print(f"\n📋 Total encontrado: {len(eventos_finais)} eventos")

                # Filtra eventos já enviados
                eventos_novos = []
                for ev in eventos_finais:
                    url = ev.get("url", "")
                    ev_id = gerar_id_evento(url) if url else gerar_id_evento(ev.get("nome", ""))
                    if ev_id not in memoria:
                        ev["_id"] = ev_id
                        eventos_novos.append(ev)

                print(f"🆕 Eventos novos: {len(eventos_novos)}")

                # Formata e envia
                mensagem = formatar_mensagem_wpp(eventos_novos, len(eventos_finais))

                # Salva em arquivo sempre
                caminho = f"relatorio_{datetime.now().strftime('%Y-%m-%d')}.txt"
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(mensagem)
                print(f"💾 Salvo em: {caminho}")
                print("\n" + "─"*40)
                print(mensagem[:800])
                print("─"*40)

                # Envia WhatsApp
                enviado = enviar_whatsapp(mensagem)

                # Atualiza memória
                if enviado or True:  # salva na memória mesmo se WPP falhar
                    for ev in eventos_novos:
                        memoria.add(ev["_id"])
                    salvar_memoria(memoria)
                    print(f"📂 Memória atualizada: {len(memoria)} eventos registrados")

                # Retorna resultado para o modelo
                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Enviado. {len(eventos_novos)} eventos novos de {len(eventos_finais)} encontrados."
                })

                return  # encerra após enviar

            elif nome == "buscar_eventos_web":
                print(f"🔍 Buscando: {args.get('query', '')}")
                resultado = executar_tool(nome, args)
                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": resultado
                })


if __name__ == "__main__":
    rodar_agente()
