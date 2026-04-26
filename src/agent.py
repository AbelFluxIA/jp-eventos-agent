"""
Agente de Eventos — Joao Pessoa + Cidades do Nordeste
- Sem repeticao de eventos (memoria persistente)
- Sem eventos passados (filtro por data no codigo)
- Alerta para eventos proximos (menos de 7 dias)
- Todas as cidades tratadas igual JP
- Fallback entre 3 chaves Tavily com alerta WhatsApp
"""

import os, json, hashlib, httpx, re, time
from datetime import datetime, date, timedelta
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODELO = os.environ.get("MODELO_IA", "gpt-4o-mini")
MEMORIA_PATH = "data/eventos_enviados.json"

PERFIL = """
Abel — dono da FluxIA (agencia de IA no Nordeste)
Cria: agentes de atendimento, sistemas SaaS, APIs, automacoes para clinicas
Quer: palestrar, networking, vender IA para clinicas e empresas
Publico-alvo: donos de clinicas, empreendedores, profissionais de saude
Tema: IA aplicada a negocios, automacao, agentes de atendimento
"""

# Cidades — todas tratadas com mesma prioridade
CIDADES = [
    "Joao Pessoa PB",
    "Campina Grande PB",
    "Recife PE",
    "Natal RN",
    "Fortaleza CE",
    "Maceio AL",
]

QUERIES_EVENTOS = []
for cidade in CIDADES:
    QUERIES_EVENTOS += [
        f"eventos {cidade} 2026 site:sympla.com.br",
        f"eventos {cidade} 2026 site:even3.com.br",
        f"evento tecnologia IA {cidade} 2026",
        f"evento empreendedorismo negocios {cidade} 2026",
        f"congresso saude clinicas {cidade} 2026",
        f"evento marketing digital {cidade} 2026",
    ]

# Queries extras para JP (cidade principal)
QUERIES_EVENTOS += [
    "eventos Joao Pessoa 2026 site:doity.com.br",
    "eventos Joao Pessoa 2026 site:eventbrite.com.br",
    "evento SEBRAE Paraiba 2026",
    "evento CRO CRM Paraiba 2026",
    "startup PB inovacao evento 2026",
    "evento SENAC ACIPB CDL Joao Pessoa 2026",
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
# TAVILY — fallback entre multiplas chaves
# --------------------------------------------------

def _get_tavily_keys() -> list:
    chaves = []
    for var in ["TAVILY_API_KEY", "TAVILY_API_KEY_2", "TAVILY_API_KEY_3"]:
        k = os.environ.get(var)
        if k:
            chaves.append(k)
    return chaves

def _alertar_admin(msg: str):
    base = os.environ.get("EVOLUTION_API_URL","").rstrip("/manager").rstrip("/")
    key  = os.environ.get("EVOLUTION_API_KEY","")
    inst = os.environ.get("EVOLUTION_INSTANCE","")
    num  = os.environ.get("WHATSAPP_ADMIN", os.environ.get("WHATSAPP_NUMERO_DESTINO",""))
    if not all([base, key, inst, num]):
        return
    try:
        httpx.post(f"{base}/message/sendText/{inst}",
            json={"number": num, "text": f"🚨 ALERTA AGENTE: {msg}"},
            headers={"apikey": key, "Content-Type": "application/json"}, timeout=10)
    except Exception:
        pass

def buscar_tavily(query: str, max_results: int = 5) -> list:
    chaves = _get_tavily_keys()
    if not chaves:
        print("  Nenhuma TAVILY_API_KEY configurada")
        return []

    for i, api_key in enumerate(chaves):
        try:
            r = httpx.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query,
                      "search_depth": "basic", "max_results": max_results},
                timeout=15
            )
            data = r.json()
            if r.status_code == 429 or "quota" in str(data).lower() or "limit" in str(data).lower():
                print(f"  Chave Tavily {i+1} com limite — tentando proxima...")
                if i == len(chaves) - 1:
                    _alertar_admin(
                        "Todas as chaves Tavily atingiram o limite! "
                        "Agente de eventos sem busca. Renove os creditos em tavily.com"
                    )
                continue
            return data.get("results", [])
        except Exception as e:
            print(f"  Erro Tavily chave {i+1}: {e}")
            continue
    return []


# --------------------------------------------------
# FILTRO DE DATA — robusto, no codigo (nao so no prompt)
# --------------------------------------------------

def extrair_data(texto: str):
    """Tenta extrair data do texto. Retorna objeto date ou None."""
    if not texto:
        return None
    # Formato DD/MM/AAAA
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    # Formato AAAA-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", texto)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None

def filtrar_eventos_validos(eventos: list, hoje: date) -> tuple:
    """
    Retorna (futuros, proximos_7_dias, passados)
    proximos_7_dias = eventos nos proximos 7 dias (alerta urgente)
    """
    futuros = []
    proximos = []
    passados = []

    for ev in eventos:
        data_ev = extrair_data(ev.get("data", ""))

        if data_ev is None:
            # Sem data definida — inclui mas sem alerta
            futuros.append(ev)
            continue

        if data_ev < hoje:
            passados.append(ev)
            print(f"  Descartado (passado): {ev.get('nome','')} — {ev.get('data','')}")
        else:
            futuros.append(ev)
            # Verifica se e nos proximos 7 dias
            if data_ev <= hoje + timedelta(days=7):
                proximos.append(ev)

    return futuros, proximos, passados


# --------------------------------------------------
# WHATSAPP
# --------------------------------------------------

def enviar_whatsapp(mensagem: str) -> bool:
    base_url = os.environ.get("EVOLUTION_API_URL","").rstrip("/manager").rstrip("/")
    api_key  = os.environ.get("EVOLUTION_API_KEY")
    instance = os.environ.get("EVOLUTION_INSTANCE")
    numero   = os.environ.get("WHATSAPP_NUMERO_DESTINO")

    if not all([base_url, api_key, instance, numero]):
        print("WhatsApp nao configurado.")
        return False

    partes = _dividir_mensagem(mensagem)
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

def _dividir_mensagem(texto: str, limite: int = 3500) -> list:
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
# FASE 1 — BUSCA
# --------------------------------------------------

def buscar_todos_eventos() -> list:
    print(f"Fazendo {len(QUERIES_EVENTOS)} buscas...")
    todos = []
    for i, query in enumerate(QUERIES_EVENTOS):
        print(f"  [{i+1}/{len(QUERIES_EVENTOS)}] {query[:65]}")
        resultados = buscar_tavily(query, max_results=5)
        for res in resultados:
            todos.append({
                "titulo": res.get("title","")[:100],
                "url":    res.get("url",""),
                "resumo": res.get("content","")[:180],
            })
        time.sleep(0.3)
    print(f"Total bruto: {len(todos)} resultados")
    return todos


# --------------------------------------------------
# FASE 2 — EXTRAIR EVENTOS COM IA
# --------------------------------------------------

SYSTEM_EXTRAIR = f"""Voce e um agente que extrai eventos de resultados de busca.

PERFIL DE QUEM VAI RECEBER:
{PERFIL}

REGRAS:
1. Extraia APENAS eventos com data futura confirmada ou provavelmente futura
2. Inclua eventos de: Joao Pessoa, Campina Grande, Recife, Natal, Fortaleza, Maceio
3. Descarte noticias, cursos online permanentes, resultados sem data
4. Inclua todos os tipos relevantes: tech, IA, marketing, negocios, saude, clinicas
5. Para palestra: avalie se Abel pode palestrar (alta/media/baixa/nenhuma)
6. Para negocio: avalie se e oportunidade de venda de IA

Retorne APENAS JSON valido sem markdown:
[
  {{
    "nome": "nome completo",
    "data": "DD/MM/AAAA ou vazio",
    "local": "local ou Online",
    "cidade": "nome da cidade",
    "resumo": "2 frases diretas",
    "preco": "Gratuito|R$ valor|A confirmar",
    "url": "url exata",
    "categoria": "tecnologia_ia|marketing|negocios_empreend|saude_clinicas|outros",
    "palestra": "alta|media|baixa|nenhuma",
    "motivo_palestra": "por que e ou nao oportunidade",
    "negocio": "alto|medio|baixo",
    "motivo_negocio": "quem estara e por que Abel pode vender"
  }}
]"""

def extrair_eventos(resultados_brutos: list, hoje: str) -> list:
    if not resultados_brutos:
        return []

    contexto = "\n".join([
        f"- {r['titulo']} | {r['url']} | {r['resumo'][:120]}"
        for r in resultados_brutos[:80]
    ])

    prompt = f"Hoje e {hoje}. Extraia eventos futuros relevantes desses resultados:\n\n{contexto}"

    try:
        r = client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": SYSTEM_EXTRAIR},
                {"role": "user", "content": prompt}
            ],
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
# FORMATAR MENSAGEM
# --------------------------------------------------

EMOJI_CAT = {
    "tecnologia_ia":     "🤖",
    "marketing":         "📣",
    "negocios_empreend": "💼",
    "saude_clinicas":    "🏥",
    "outros":            "📌",
}

def formatar_mensagem(novos: list, proximos_urgentes: list, hoje: str) -> str:
    if not novos:
        return f"📅 *Eventos — {hoje}*\n\nNenhum evento novo hoje! Todos ja foram enviados. 👍"

    palestras = [e for e in novos if e.get("palestra") in ("alta","media")]
    negocios  = [e for e in novos if e.get("negocio") == "alto"]

    linhas = [f"📅 *Agenda de Eventos — {hoje}*"]
    linhas.append(f"_{len(novos)} novos eventos encontrados_\n")

    # ALERTA URGENTE — eventos em menos de 7 dias
    if proximos_urgentes:
        linhas.append("⚡ *ACONTECE EM MENOS DE 7 DIAS*")
        linhas.append("─────────────────────")
        for ev in proximos_urgentes:
            emoji = EMOJI_CAT.get(ev.get("categoria","outros"),"📌")
            linhas.append(f"{emoji} *{ev.get('nome','')}*")
            linhas.append(f"📆 {ev.get('data','')} — ⚠️ URGENTE")
            if ev.get("local"): linhas.append(f"📍 {ev.get('local','')} | {ev.get('cidade','')}")
            linhas.append(f"💬 {ev.get('resumo','')}")
            linhas.append(f"💰 {ev.get('preco','A confirmar')}")
            linhas.append(f"🔗 {ev.get('url','')}")
            linhas.append("")

    # OPORTUNIDADES DE PALESTRA
    # Filtra urgentes para nao repetir
    ids_urgentes = {e.get("url") for e in proximos_urgentes}
    palestras_nao_urgentes = [e for e in palestras if e.get("url") not in ids_urgentes]

    if palestras_nao_urgentes:
        linhas.append("🎤 *OPORTUNIDADES PARA PALESTRAR*")
        linhas.append("─────────────────────")
        for ev in palestras_nao_urgentes[:5]:
            emoji = EMOJI_CAT.get(ev.get("categoria","outros"),"📌")
            linhas.append(f"🎤 *{ev.get('nome','')}*")
            if ev.get("data"): linhas.append(f"📆 {ev.get('data','')} | {ev.get('cidade','')}")
            if ev.get("local"): linhas.append(f"📍 {ev.get('local','')}")
            linhas.append(f"💡 {ev.get('motivo_palestra','')}")
            linhas.append(f"🔗 {ev.get('url','')}")
            linhas.append("")

    # OPORTUNIDADES DE NEGOCIO
    negocios_novos = [e for e in negocios
                      if e.get("url") not in ids_urgentes
                      and e not in palestras_nao_urgentes]
    if negocios_novos:
        linhas.append("💼 *OPORTUNIDADES DE NEGOCIO*")
        linhas.append("─────────────────────")
        for ev in negocios_novos[:5]:
            emoji = EMOJI_CAT.get(ev.get("categoria","outros"),"📌")
            linhas.append(f"{emoji} *{ev.get('nome','')}*")
            if ev.get("data"): linhas.append(f"📆 {ev.get('data','')} | {ev.get('cidade','')}")
            linhas.append(f"🤝 {ev.get('motivo_negocio','')}")
            linhas.append(f"🔗 {ev.get('url','')}")
            linhas.append("")

    # DEMAIS EVENTOS
    ids_ja_listados = ids_urgentes | {e.get("url") for e in palestras_nao_urgentes} | {e.get("url") for e in negocios_novos}
    demais = [e for e in novos if e.get("url") not in ids_ja_listados]

    if demais:
        linhas.append("📋 *OUTROS EVENTOS*")
        linhas.append("─────────────────────")
        for ev in demais[:10]:
            emoji = EMOJI_CAT.get(ev.get("categoria","outros"),"📌")
            cidade = ev.get("cidade","")
            linhas.append(f"{emoji} *{ev.get('nome','')}*" + (f" | {cidade}" if cidade else ""))
            if ev.get("data"): linhas.append(f"📆 {ev.get('data','')}")
            if ev.get("local"): linhas.append(f"📍 {ev.get('local','')}")
            linhas.append(f"💬 {ev.get('resumo','')}")
            linhas.append(f"💰 {ev.get('preco','A confirmar')}")
            linhas.append(f"🔗 {ev.get('url','')}")
            linhas.append("")

    linhas.append("_Agente de Eventos FluxIA 🤖_")
    return "\n".join(linhas)


# --------------------------------------------------
# PRINCIPAL
# --------------------------------------------------

def rodar_agente():
    hoje_dt  = date.today()
    hoje_str = hoje_dt.strftime("%d/%m/%Y")

    print("=" * 50)
    print(f"Agente de Eventos — {hoje_str}")
    print("=" * 50)

    memoria = carregar_memoria()
    print(f"Memoria: {len(memoria)} eventos ja enviados\n")

    # FASE 1 — busca
    print("FASE 1: Buscando eventos...")
    resultados_brutos = buscar_todos_eventos()

    if not resultados_brutos:
        print("Sem resultados. Verifique TAVILY_API_KEY.")
        _alertar_admin("Agente de eventos: zero resultados de busca. Verifique Tavily.")
        return

    # FASE 2 — extrai com IA
    print("\nFASE 2: Extraindo eventos com IA...")
    eventos = extrair_eventos(resultados_brutos, hoje_str)
    print(f"Extraidos: {len(eventos)}")

    if not eventos:
        print("Nenhum evento valido.")
        return

    # FASE 3 — filtra passados (no codigo, nao so no prompt)
    print("\nFASE 3: Filtrando eventos passados...")
    futuros, proximos_urgentes, passados = filtrar_eventos_validos(eventos, hoje_dt)
    print(f"Futuros: {len(futuros)} | Proximos 7 dias: {len(proximos_urgentes)} | Passados descartados: {len(passados)}")

    # FASE 4 — filtra ja enviados (memoria)
    print("\nFASE 4: Filtrando ja enviados...")
    novos = []
    for ev in futuros:
        ev_id = gerar_id(ev.get("url","") or ev.get("nome",""))
        if ev_id not in memoria:
            ev["_id"] = ev_id
            novos.append(ev)

    # Proximos urgentes novos (para destaque)
    ids_novos = {e.get("url") for e in novos}
    proximos_novos = [e for e in proximos_urgentes if e.get("url") in ids_novos]

    print(f"Novos: {len(novos)} | Urgentes (7 dias): {len(proximos_novos)}")

    if not novos:
        enviar_whatsapp(f"📅 *Eventos — {hoje_str}*\n\nNenhum evento novo hoje! Todos ja foram enviados. 👍")
        return

    # FASE 5 — formata e envia
    mensagem = formatar_mensagem(novos, proximos_novos, hoje_str)

    caminho = f"relatorio_{hoje_dt.strftime('%Y-%m-%d')}.txt"
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(mensagem)
    print(f"\nSalvo: {caminho}")
    print(mensagem[:600])

    enviado = enviar_whatsapp(mensagem)

    # Atualiza memoria
    for ev in novos:
        memoria.add(ev["_id"])
    salvar_memoria(memoria)
    print(f"Memoria: {len(memoria)} eventos registrados")

    if not enviado:
        print("AVISO: WhatsApp nao enviado.")


if __name__ == "__main__":
    rodar_agente()
