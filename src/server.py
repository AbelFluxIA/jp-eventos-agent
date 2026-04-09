"""
Servidor web leve + agendador interno.
Roda de graça no Render como Web Service (não Cron Job).
O agente executa todo dia às 7h automaticamente.
"""

import threading
import time
import os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# Importa o agente principal
import sys
sys.path.insert(0, os.path.dirname(__file__))
from agent import rodar_agente


# ─────────────────────────────────────────────
# SERVIDOR HTTP (só para o Render não matar o processo)
# ─────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.wfile.write(f"✅ Agente JP rodando | {agora}".encode())

    def log_message(self, format, *args):
        pass  # silencia logs de request


def iniciar_servidor():
    porta = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", porta), Handler)
    print(f"🌐 Servidor HTTP na porta {porta}")
    server.serve_forever()


# ─────────────────────────────────────────────
# AGENDADOR (roda o agente todo dia às 7h)
# ─────────────────────────────────────────────

HORA_EXECUCAO = int(os.environ.get("HORA_EXECUCAO", "7"))   # padrão: 7h da manhã

def loop_agendador():
    print(f"⏰ Agendador iniciado — executará todo dia às {HORA_EXECUCAO}h")
    ultimo_dia_executado = None

    while True:
        agora = datetime.now()
        hoje = agora.date()

        if agora.hour == HORA_EXECUCAO and ultimo_dia_executado != hoje:
            print(f"\n🚀 Disparando agente — {agora.strftime('%d/%m/%Y %H:%M')}")
            try:
                rodar_agente()
                ultimo_dia_executado = hoje
                print("✅ Agente concluído com sucesso.")
            except Exception as e:
                print(f"❌ Erro no agente: {e}")

        time.sleep(60)  # verifica a cada 1 minuto


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Roda o agendador em background
    t = threading.Thread(target=loop_agendador, daemon=True)
    t.start()

    # Sobe o servidor HTTP na thread principal (Render exige isso)
    iniciar_servidor()
