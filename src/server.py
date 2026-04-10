import threading
import time
import os
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

print("=== server.py iniciando ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"Diretorio: {os.getcwd()}", flush=True)
print(f"Arquivos src: {os.listdir(os.path.dirname(__file__))}", flush=True)

sys.path.insert(0, os.path.dirname(__file__))

print("Importando agent...", flush=True)
try:
    from agent import rodar_agente
    print("agent.py importado com sucesso!", flush=True)
except Exception as e:
    print(f"ERRO ao importar agent: {e}", flush=True)
    rodar_agente = None

HORA_EXECUCAO = int(os.environ.get("HORA_EXECUCAO", "7"))
print(f"Hora de execucao configurada: {HORA_EXECUCAO}h", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        agora = datetime.now().strftime("%d/%m/%Y %H:%M")

        if self.path == "/testar":
            self.send_response(200)
            self.end_headers()
            if rodar_agente is None:
                self.wfile.write(b"ERRO: agent.py nao carregou. Veja os logs do Render.")
                return
            self.wfile.write(f"Disparando agente agora... ({agora})".encode())
            print("=== /testar chamado - iniciando agente ===", flush=True)
            t = threading.Thread(target=self._rodar_seguro, daemon=True)
            t.start()
        else:
            self.send_response(200)
            self.end_headers()
            status = "OK" if rodar_agente else "ERRO - agent nao carregado"
            self.wfile.write(f"Agente JP | {status} | {agora} | disparo: {HORA_EXECUCAO}h".encode())

    def _rodar_seguro(self):
        try:
            print("Agente iniciado via /testar", flush=True)
            rodar_agente()
            print("Agente finalizado com sucesso!", flush=True)
        except Exception as e:
            print(f"ERRO no agente: {e}", flush=True)
            import traceback
            traceback.print_exc()

    def log_message(self, format, *args):
        pass


def iniciar_servidor():
    porta = int(os.environ.get("PORT", 10000))
    print(f"Subindo servidor na porta {porta}...", flush=True)
    server = HTTPServer(("0.0.0.0", porta), Handler)
    print(f"Servidor rodando na porta {porta}", flush=True)
    server.serve_forever()


def loop_agendador():
    print(f"Agendador rodando - dispara todo dia as {HORA_EXECUCAO}h", flush=True)
    ultimo_dia = None
    while True:
        agora = datetime.now()
        if agora.hour == HORA_EXECUCAO and ultimo_dia != agora.date():
            print(f"Disparando agente automatico - {agora.strftime('%d/%m/%Y %H:%M')}", flush=True)
            try:
                rodar_agente()
                ultimo_dia = agora.date()
            except Exception as e:
                print(f"ERRO no agente automatico: {e}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    t = threading.Thread(target=loop_agendador, daemon=True)
    t.start()
    iniciar_servidor()
