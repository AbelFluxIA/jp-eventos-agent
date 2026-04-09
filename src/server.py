"""
Servidor web leve + agendador interno.
Roda de graca no Render como Web Service (nao Cron Job).
O agente executa todo dia no horario configurado automaticamente.
"""

import threading
import time
import os
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import sys
sys.path.insert(0, os.path.dirname(__file__))
from agent import rodar_agente


HORA_EXECUCAO = int(os.environ.get("HORA_EXECUCAO", "7"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")

        if self.path == "/testar":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"Disparando agente agora... ({agora})".encode())
            t = threading.Thread(target=self._rodar_agente_seguro, daemon=True)
            t.start()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"Agente JP rodando | proximo disparo: {HORA_EXECUCAO}h | agora: {agora}".encode())

    def _rodar_agente_seguro(self):
        try:
            print("Teste manual disparado via /testar")
            rodar_agente()
        except Exception as e:
            print(f"Erro no teste: {e}")

    def log_message(self, format, *args):
        pass


def iniciar_servidor():
    porta = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", porta), Handler)
    print(f"Servidor HTTP na porta {porta}")
    server.serve_forever()


def loop_agendador():
    print(f"Agendador iniciado - executara todo dia as {HORA_EXECUCAO}h")
    ultimo_dia_executado = None

    while True:
        agora = datetime.now()
        hoje = agora.date()

        if agora.hour == HORA_EXECUCAO and ultimo_dia_executado != hoje:
            print(f"Disparando agente - {agora.strftime('%d/%m/%Y %H:%M')}")
            try:
                rodar_agente()
                ultimo_dia_executado = hoje
                print("Agente concluido com sucesso.")
            except Exception as e:
                print(f"Erro no agente: {e}")

        time.sleep(60)


if __name__ == "__main__":
    t = threading.Thread(target=loop_agendador, daemon=True)
    t.start()
    iniciar_servidor()
