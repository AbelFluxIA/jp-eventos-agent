"""
painel.py
Painel web para visualizar eventos encontrados pelo agente.
Acesse: http://SEU-IP:10000/painel
"""

import os
import json
from datetime import datetime

MEMORIA_PATH = "data/eventos_enviados.json"
RELATORIOS_DIR = "."


def carregar_eventos_memoria() -> list:
    """Carrega IDs dos eventos enviados."""
    try:
        with open(MEMORIA_PATH, "r") as f:
            return json.load(f).get("enviados", [])
    except Exception:
        return []


def carregar_ultimo_relatorio() -> str:
    """Carrega o conteudo do relatorio mais recente."""
    try:
        arquivos = sorted([
            f for f in os.listdir(RELATORIOS_DIR)
            if f.startswith("relatorio_") and f.endswith(".txt")
        ], reverse=True)
        if not arquivos:
            return ""
        with open(os.path.join(RELATORIOS_DIR, arquivos[0]), "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def gerar_html_painel(ultimo_relatorio: str, total_enviados: int,
                      status_agente: dict) -> str:
    """Gera HTML completo do painel."""

    # Converte texto do relatorio para HTML
    linhas_html = []
    if ultimo_relatorio:
        for linha in ultimo_relatorio.split("\n"):
            linha = linha.strip()
            if not linha:
                linhas_html.append('<div class="spacer"></div>')
            elif linha.startswith("📅"):
                linhas_html.append(f'<div class="rel-titulo">{linha}</div>')
            elif linha.startswith("⚡"):
                linhas_html.append(f'<div class="rel-secao urgente">{linha}</div>')
            elif linha.startswith("🎤"):
                linhas_html.append(f'<div class="rel-secao palestra">{linha}</div>')
            elif linha.startswith("💼"):
                linhas_html.append(f'<div class="rel-secao negocio">{linha}</div>')
            elif linha.startswith("📋"):
                linhas_html.append(f'<div class="rel-secao outros">{linha}</div>')
            elif linha.startswith("─"):
                linhas_html.append('<hr class="rel-divider">')
            elif linha.startswith("🔗"):
                url = linha.replace("🔗 ", "")
                linhas_html.append(
                    f'<div class="rel-link">🔗 <a href="{url}" target="_blank">{url}</a></div>'
                )
            elif linha.startswith("📆") or linha.startswith("📍"):
                linhas_html.append(f'<div class="rel-meta">{linha}</div>')
            elif linha.startswith("💰"):
                linhas_html.append(f'<div class="rel-preco">{linha}</div>')
            elif linha.startswith("💬"):
                linhas_html.append(f'<div class="rel-resumo">{linha}</div>')
            elif linha.startswith("💡") or linha.startswith("🤝"):
                linhas_html.append(f'<div class="rel-insight">{linha}</div>')
            elif linha.startswith("_") and linha.endswith("_"):
                linhas_html.append(f'<div class="rel-footer">{linha}</div>')
            else:
                linhas_html.append(f'<div class="rel-linha">{linha}</div>')
    else:
        linhas_html.append('<div class="rel-vazio">Nenhum relatório gerado ainda. Clique em "Disparar Agente" para começar.</div>')

    relatorio_html = "\n".join(linhas_html)

    uptime = status_agente.get("uptime", "—")
    ultimo_disparo = status_agente.get("ultimo_disparo", "—")
    proximo = status_agente.get("proximo_disparo", "—")
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FluxIA — Painel de Eventos</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #080C14;
    --bg2: #0D1421;
    --bg3: #111827;
    --border: #1E2D45;
    --accent: #3B82F6;
    --accent2: #06B6D4;
    --green: #10B981;
    --yellow: #F59E0B;
    --red: #EF4444;
    --text: #E2E8F0;
    --text2: #94A3B8;
    --text3: #475569;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
  }}

  .grid-bg {{
    position: fixed; inset: 0;
    background-image:
      linear-gradient(rgba(59,130,246,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(59,130,246,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
  }}

  .header {{
    border-bottom: 1px solid var(--border);
    padding: 1.2rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky; top: 0;
    background: rgba(8,12,20,0.95);
    backdrop-filter: blur(12px);
    z-index: 100;
  }}

  .logo {{
    display: flex; align-items: center; gap: 12px;
  }}

  .logo-dot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 12px var(--green);
    animation: pulse 2s infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.6; transform: scale(0.85); }}
  }}

  .logo-text {{
    font-size: 1rem; font-weight: 700;
    letter-spacing: 0.05em;
    color: var(--text);
  }}

  .logo-sub {{
    font-size: 0.7rem; color: var(--text3);
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.1em;
  }}

  .header-right {{
    font-family: 'DM Mono', monospace;
    font-size: 0.75rem; color: var(--text3);
  }}

  .container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem;
  }}

  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 2rem;
  }}

  .stat {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem;
    position: relative;
    overflow: hidden;
  }}

  .stat::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
  }}

  .stat-val {{
    font-size: 2rem; font-weight: 800;
    color: var(--text);
    line-height: 1;
    margin-bottom: 6px;
  }}

  .stat-lbl {{
    font-size: 0.72rem;
    color: var(--text3);
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }}

  .main-grid {{
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 1.5rem;
  }}

  .card {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
  }}

  .card-header {{
    padding: 1rem 1.4rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .card-title {{
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text2);
    font-family: 'DM Mono', monospace;
  }}

  .card-body {{
    padding: 1.4rem;
  }}

  /* RELATORIO */
  .relatorio {{
    font-family: 'DM Mono', monospace;
    font-size: 0.82rem;
    line-height: 1.7;
    max-height: 600px;
    overflow-y: auto;
    padding-right: 8px;
  }}

  .relatorio::-webkit-scrollbar {{ width: 4px; }}
  .relatorio::-webkit-scrollbar-track {{ background: transparent; }}
  .relatorio::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}

  .rel-titulo {{
    font-size: 1rem; font-weight: 700;
    color: var(--text); margin-bottom: 8px;
    font-family: 'Syne', sans-serif;
  }}

  .rel-secao {{
    font-weight: 700; margin-top: 16px; margin-bottom: 4px;
    font-family: 'Syne', sans-serif; font-size: 0.85rem;
  }}

  .rel-secao.urgente {{ color: var(--yellow); }}
  .rel-secao.palestra {{ color: var(--accent2); }}
  .rel-secao.negocio {{ color: var(--green); }}
  .rel-secao.outros {{ color: var(--text2); }}

  .rel-divider {{ border: none; border-top: 1px solid var(--border); margin: 6px 0; }}
  .rel-meta {{ color: var(--text2); }}
  .rel-preco {{ color: var(--green); }}
  .rel-resumo {{ color: var(--text); }}
  .rel-insight {{ color: var(--accent); }}
  .rel-link a {{ color: var(--accent2); text-decoration: none; }}
  .rel-link a:hover {{ text-decoration: underline; }}
  .rel-footer {{ color: var(--text3); margin-top: 12px; font-size: 0.72rem; }}
  .rel-vazio {{ color: var(--text3); text-align: center; padding: 2rem; }}
  .spacer {{ height: 8px; }}

  /* SIDEBAR */
  .btn {{
    width: 100%;
    padding: 0.85rem;
    border-radius: 10px;
    border: none;
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    font-size: 0.85rem;
    cursor: pointer;
    letter-spacing: 0.04em;
    transition: all 0.2s;
    margin-bottom: 0.75rem;
  }}

  .btn-primary {{
    background: var(--accent);
    color: white;
  }}
  .btn-primary:hover {{ background: #2563EB; transform: translateY(-1px); }}

  .btn-secondary {{
    background: transparent;
    color: var(--text2);
    border: 1px solid var(--border);
  }}
  .btn-secondary:hover {{ border-color: var(--accent); color: var(--accent); }}

  .info-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.7rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.8rem;
  }}

  .info-row:last-child {{ border-bottom: none; }}

  .info-lbl {{ color: var(--text3); font-family: 'DM Mono', monospace; }}
  .info-val {{ color: var(--text); font-weight: 600; }}
  .info-val.green {{ color: var(--green); }}
  .info-val.yellow {{ color: var(--yellow); }}

  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-family: 'DM Mono', monospace;
    font-weight: 500;
  }}

  .badge.online {{
    background: rgba(16,185,129,0.15);
    color: var(--green);
    border: 1px solid rgba(16,185,129,0.3);
  }}

  .toast {{
    position: fixed;
    bottom: 2rem; right: 2rem;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.4rem;
    font-size: 0.85rem;
    display: none;
    z-index: 999;
    animation: slideIn 0.3s ease;
  }}

  @keyframes slideIn {{
    from {{ transform: translateY(20px); opacity: 0; }}
    to {{ transform: translateY(0); opacity: 1; }}
  }}

  @media (max-width: 768px) {{
    .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .main-grid {{ grid-template-columns: 1fr; }}
    .container {{ padding: 1rem; }}
  }}
</style>
</head>
<body>
<div class="grid-bg"></div>

<div class="header">
  <div class="logo">
    <div class="logo-dot"></div>
    <div>
      <div class="logo-text">FluxIA</div>
      <div class="logo-sub">PAINEL DE EVENTOS</div>
    </div>
  </div>
  <div class="header-right">Atualizado: {agora}</div>
</div>

<div class="container">

  <div class="stats-grid">
    <div class="stat">
      <div class="stat-val">{total_enviados}</div>
      <div class="stat-lbl">Eventos na memória</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="color:var(--green)">ON</div>
      <div class="stat-lbl">Status do agente</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="font-size:1.1rem">{ultimo_disparo}</div>
      <div class="stat-lbl">Último disparo</div>
    </div>
    <div class="stat">
      <div class="stat-val" style="font-size:1.1rem">{proximo}</div>
      <div class="stat-lbl">Próximo disparo</div>
    </div>
  </div>

  <div class="main-grid">

    <div class="card">
      <div class="card-header">
        <span class="card-title">Último Relatório de Eventos</span>
        <span class="badge online">
          <span style="width:6px;height:6px;border-radius:50%;background:var(--green);display:inline-block"></span>
          AO VIVO
        </span>
      </div>
      <div class="card-body">
        <div class="relatorio">
          {relatorio_html}
        </div>
      </div>
    </div>

    <div>
      <div class="card" style="margin-bottom:1rem">
        <div class="card-header">
          <span class="card-title">Controles</span>
        </div>
        <div class="card-body">
          <button class="btn btn-primary" onclick="disparar()">
            ⚡ Disparar Agente Agora
          </button>
          <button class="btn btn-secondary" onclick="location.reload()">
            ↻ Atualizar Painel
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Informações</span>
        </div>
        <div class="card-body">
          <div class="info-row">
            <span class="info-lbl">Status</span>
            <span class="info-val green">Online</span>
          </div>
          <div class="info-row">
            <span class="info-lbl">Uptime</span>
            <span class="info-val">{uptime}</span>
          </div>
          <div class="info-row">
            <span class="info-lbl">Memória</span>
            <span class="info-val">{total_enviados} eventos</span>
          </div>
          <div class="info-row">
            <span class="info-lbl">Último</span>
            <span class="info-val">{ultimo_disparo}</span>
          </div>
          <div class="info-row">
            <span class="info-lbl">Próximo</span>
            <span class="info-val yellow">{proximo}</span>
          </div>
          <div class="info-row">
            <span class="info-lbl">Cidades</span>
            <span class="info-val" style="font-size:0.72rem">JP · CG · Recife · Natal · FOR · Mac</span>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>

<div class="toast" id="toast"></div>

<script>
function mostrarToast(msg, cor) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  t.style.borderColor = cor || '#3B82F6';
  setTimeout(() => {{ t.style.display = 'none'; }}, 4000);
}}

function disparar() {{
  mostrarToast('⚡ Agente disparado! Acompanhe os logs...', '#10B981');
  fetch('/testar').then(r => r.text()).then(t => {{
    mostrarToast('✅ ' + t.substring(0, 60), '#10B981');
  }}).catch(() => {{
    mostrarToast('❌ Erro ao disparar', '#EF4444');
  }});
}}

// Auto-refresh a cada 60 segundos
setTimeout(() => location.reload(), 60000);
</script>
</body>
</html>"""


def get_painel_html(status_agente: dict) -> str:
    total = len(carregar_eventos_memoria())
    relatorio = carregar_ultimo_relatorio()
    return gerar_html_painel(relatorio, total, status_agente)
