"""
Agente de Eventos — João Pessoa, PB
- Busca diária com OpenAI GPT-4o
- Envia via WhatsApp (Evolution API)
- Memoria de eventos ja enviados (sem repeticao)
- Busca preco real acessando pagina do evento
- Filtra eventos fora de JP
"""

import os
import json
import hashlib
import httpx
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

MEMORIA_PATH = "data/eventos_enviados.json"

# --------------------------------------------------
# MEMORIA
# --------------------------------------------------

def carregar_memoria() -> set:
    try:
        with open(MEMORIA_PATH, "r") as f:
            data = json.load(f)
            return set(data.get("enviados", []))
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
            "description": (
                "Busca eventos em Joao Pessoa via Tavily. "
                "Use queries CIRURGICAS e VARIADAS. Faca no minimo 20 buscas cobrindo:\n"
                "PLATAFORMAS: sympla.com.br, eventbrite.com.br, even3.com.br, doity.com.br, ingresse.com, meetup.com\n"
                "CATEGORIAS: tecnologia, IA, inteligencia artificial, programacao, startups, "
                "marketing digital, growth hacking, redes sociais, empreendedorismo, negocios, "
                "vendas, gestao, lideranca, odontologia, estetica, medicina, clinicas, fisioterapia, nutricao\n"
                "EXEMPLOS de queries boas:\n"
                "- 'eventos Joao Pessoa abril 2026 site:sympla.com.br'\n"
                "- 'workshop inteligencia artificial Joao Pessoa 2026'\n"
                "- 'congresso odontologia Paraiba 2026'\n"
                "- 'meetup tecnologia Joao Pessoa site:meetup.com'\n"
                "- 'curso marketing digital Joao Pessoa presencial 2026'\n"
                "- 'evento estetica clinicas Joao Pessoa 2026'\n"
                "- 'networking empreendedores Joao Pessoa 2026'\n"
                "Varie as queries. Nao repita os mesmos termos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query de busca"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "acessar_pagina_evento",
            "description": (
                "Acessa a pagina de um evento para extrair informacoes detalhadas: "
                "preco exato, data completa, local com endereco, descricao completa. "
                "Use quando os dados da busca estiverem incompletos, especialmente para preco."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL da pagina do evento"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalizar_e_enviar",
            "description": (
                "Finaliza a pesquisa e envia os eventos encontrados via WhatsApp. "
                "Chame SOMENTE apos ter feito todas as buscas (minimo 20) e acessado "
                "as paginas dos eventos para confirmar preco e detalhes. "
                "IMPORTANTE: inclua APENAS eventos que acontecem em Joao Pessoa ou Paraiba. "
                "Exclua eventos de outros estados."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "eventos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nome":      {"type": "string"},
                                "data":      {"type": "string", "description": "Ex: 28/04/2026 as 9h"},
                                "local":     {"type": "string", "description": "Endereco completo ou Online"},
                                "resumo":    {"type": "string", "description": "2-3 frases diretas sobre o evento"},
                                "preco":     {"type": "string", "description": "Gratuito / R$ XX,00 / Sob consulta"},
                                "url":       {"type": "string"},
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


# --------------------------------------------------
# EXECUTORES
# --------------------------------------------------

def buscar_eventos_web(query: str) -> str:
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
        texto = r.text

        # Extrai texto relevante removendo HTML de forma simples
        import re
        texto = re.sub(r"<style[^>]*>.*?</style>", " ", texto, flags=re.DOTALL)
        texto = re.sub(r"<script[^>]*>.*?</script>", " ", texto, flags=re.DOTALL)
        texto = re.sub(r"<[^>]+>", " ", texto)
        texto = re.sub(r"\s+", " ", texto).strip()

        # Retorna os primeiros 2000 chars que costumam ter as infos principais
        return texto[:1000]

    except Exception as e:
        return f"Nao foi possivel acessar a pagina: {e}"


def executar_tool(nome: str, args: dict) -> str:
    if nome == "buscar_eventos_web":
        return buscar_eventos_web(args["query"])
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
        print("WhatsApp nao configurado — salvo so em arquivo.")
        return False

    try:
        url = f"{base_url}/message/sendText/{instance}"
        r = httpx.post(
            url,
            json={"number": numero, "text": mensagem},
            headers={"apikey": api_key, "Content-Type": "application/json"},
            timeout=15
        )
        if r.status_code in (200, 201):
            print("WhatsApp enviado com sucesso!")
            return True
        print(f"Erro Evolution API: {r.status_code} — {r.text[:300]}")
        return False
    except Exception as e:
        print(f"Erro ao enviar WhatsApp: {e}")
        return False


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

def formatar_mensagem(eventos_novos: list, total: int) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")

    if not eventos_novos:
        return (
            f"📅 *Eventos JP — {hoje}*\n\n"
            "Nenhum evento novo encontrado hoje.\n"
            "Todos os eventos conhecidos ja foram enviados! 👍"
        )

    linhas = [f"📅 *Eventos JP — {hoje}*"]
    linhas.append(f"_{len(eventos_novos)} novos de {total} encontrados_\n")

    for ev in eventos_novos:
        emoji = EMOJI_CAT.get(ev.get("categoria", "outros"), "📌")
        linhas.append(f"{emoji} *{ev.get('nome', '')}*")

        data  = ev.get("data", "")
        local = ev.get("local", "")
        preco = ev.get("preco", "A confirmar")
        url   = ev.get("url", "")

        if data:  linhas.append(f"📆 {data}")
        if local: linhas.append(f"📍 {local}")
        linhas.append(f"💬 {ev.get('resumo', '')}")
        linhas.append(f"💰 {preco}")
        if url: linhas.append(f"🔗 {url}")
        linhas.append("")

    linhas.append("_Agente de Eventos JP 🤖_")
    return "\n".join(linhas)


# --------------------------------------------------
# SYSTEM PROMPT
# --------------------------------------------------

SYSTEM_PROMPT = """Voce e um agente especializado em descobrir eventos em Joao Pessoa, PB, Brasil.

REGRAS ABSOLUTAS:
1. Inclua APENAS eventos em Joao Pessoa ou Paraiba. Descarte qualquer evento de outros estados.
2. Faca NO MINIMO 20 buscas antes de finalizar. Seja exaustivo.
3. Para cada evento encontrado, tente acessar a pagina para confirmar preco e detalhes.
4. Prefira preco real (Gratuito / R$ valor) a "Sob consulta".

CATEGORIAS (cubra TODAS nas buscas):
- Tecnologia, IA, programacao, inovacao, startups
- Marketing digital, redes sociais, growth, copywriting, criacao de conteudo
- Empreendedorismo, negocios, vendas, gestao, financas, lideranca
- Saude: odontologia, medicina estetica, fisioterapia, nutricao, clinicas

PLATAFORMAS (faca buscas em TODAS):
sympla.com.br, eventbrite.com.br, even3.com.br, doity.com.br, ingresse.com, meetup.com

ESTRATEGIA DE BUSCA:
- Combine categoria + cidade: "workshop IA Joao Pessoa 2026"
- Combine categoria + plataforma: "eventos empreendedorismo JP site:sympla.com.br"  
- Busque por mes: "eventos Joao Pessoa maio 2026"
- Busque termos especificos do publico: "congresso odontologia Paraiba", "curso gestor clinica JP"
- Busque eventos nacionais com edicao em JP: "evento nacional marketing Joao Pessoa"

Apos todas as buscas, acesse as paginas dos eventos mais promissores para pegar preco e detalhes.
So entao chame finalizar_e_enviar."""


# --------------------------------------------------
# LOOP PRINCIPAL
# --------------------------------------------------

def rodar_agente():
    hoje = datetime.now().strftime("%d/%m/%Y")
    print("=" * 50)
    print(f"Agente de Eventos JP — {hoje}")
    print("=" * 50)

    memoria = carregar_memoria()
    print(f"Memoria: {len(memoria)} eventos ja enviados\n")

    mensagens = [{
        "role": "user",
        "content": (
            f"Hoje e {hoje}. Busque TODOS os eventos em Joao Pessoa, PB "
            f"para os proximos 60 dias. "
            f"Faca no minimo 20 buscas cobrindo todas as categorias e plataformas. "
            f"Acesse as paginas dos eventos para confirmar preco e detalhes. "
            f"Inclua APENAS eventos em JP ou Paraiba."
        )
    }]

    iteracoes = 0

    while iteracoes < 30:
        iteracoes += 1

        resposta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + mensagens,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
        )

        msg = resposta.choices[0].message
        mensagens.append(msg)

        if not msg.tool_calls:
            print("Agente finalizou sem chamar ferramentas.")
            break

        for tc in msg.tool_calls:
            nome = tc.function.name
            args = json.loads(tc.function.arguments)

            if nome == "finalizar_e_enviar":
                eventos = args.get("eventos", [])
                print(f"\nTotal encontrado: {len(eventos)} eventos")

                # Filtra ja enviados
                novos = []
                for ev in eventos:
                    url = ev.get("url", "") or ev.get("nome", "")
                    ev_id = gerar_id_evento(url)
                    if ev_id not in memoria:
                        ev["_id"] = ev_id
                        novos.append(ev)

                print(f"Eventos novos: {len(novos)}")

                mensagem = formatar_mensagem(novos, len(eventos))

                # Salva arquivo
                caminho = f"relatorio_{datetime.now().strftime('%Y-%m-%d')}.txt"
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(mensagem)
                print(f"Salvo em: {caminho}")
                print(mensagem[:1000])

                # Envia WhatsApp
                enviar_whatsapp(mensagem)

                # Atualiza memoria
                for ev in novos:
                    memoria.add(ev["_id"])
                salvar_memoria(memoria)
                print(f"Memoria atualizada: {len(memoria)} eventos registrados")

                mensagens.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Enviado. {len(novos)} novos de {len(eventos)}."
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
