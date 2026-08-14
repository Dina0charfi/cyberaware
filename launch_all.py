#!/usr/bin/env python3
"""
launch_all.py — lance les 4 projets (DarkWatch, NetScope, PhishHunter, Sentinel)
en une seule commande, chacun dans son propre venv/port, avec une page d'accueil
qui centralise les liens vers chaque dashboard.

Usage :
    python launch_all.py

Puis ouvre http://localhost:8000 (s'ouvre automatiquement dans le navigateur).
Ctrl+C pour tout arrêter proprement.
"""

import http.server
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
HOME_PORT = 8000
LOG_DIR = ROOT / "_launch_logs"
LOG_DIR.mkdir(exist_ok=True)

APPS = [
    {
        "name": "DarkWatch",
        "port": 8877,
        "home_path": "/",
        "cwd": ROOT / "darkwatch_project",
        "cmd": lambda: [sys.executable, "server.py"],
        "env_extra": {"DARKWATCH_PORT": "8877"},
        "desc": "Surveillance de fuites de données (dark web monitoring)",
        "accent": "7C5CFF",
        "initial": "D",
    },
    {
        "name": "NetScope",
        "port": 8001,
        "home_path": "/",
        "cwd": ROOT / "netscope_project",
        "cmd": lambda: [
            str(ROOT / "netscope_project" / "venv" / "Scripts" / "python.exe"),
            "-m", "uvicorn", "netscope_agent.api:app",
            "--app-dir", "src", "--port", "8001",
        ],
        "desc": "Détection de domaines DNS suspects",
        "accent": "0F6E56",
        "initial": "N",
    },
    {
        "name": "PhishHunter",
        "port": 8002,
        "home_path": "/dashboard/",
        "cwd": ROOT / "phishhunter_project",
        "cmd": lambda: [
            str(ROOT / "phishhunter_project" / "venv" / "Scripts" / "python.exe"),
            "-m", "uvicorn", "src.api.main:app", "--port", "8002",
        ],
        "desc": "Détection de phishing par email",
        "accent": "4338CA",
        "initial": "P",
    },
    {
        "name": "Sentinel",
        "port": 8003,
        "home_path": "/",
        "cwd": ROOT / "sentinel_project" / "backend",
        "cmd": lambda: [
            str(ROOT / "sentinel_project" / "backend" / "venv" / "Scripts" / "python.exe"),
            "-m", "uvicorn", "app:app", "--port", "8003",
        ],
        "desc": "Détection d'anomalies de connexion (insider threat)",
        "accent": "2563EB",
        "initial": "S",
    },
    {
        "name": "CrisisBot",
        "port": 8878,
        "home_path": "/",
        "cwd": ROOT / "crisisbot_project",
        "cmd": lambda: [sys.executable, "server.py"],
        "env_extra": {"CRISISBOT_PORT": "8878"},
        "desc": "Réponse à incident automatisée (runbook + notifications)",
        "accent": "DC2626",
        "initial": "C",
    },
]

processes = []


def start_app(app, simulate=False):
    log_path = LOG_DIR / f"{app['name'].lower()}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"  # évite les crashs UnicodeEncodeError (accents/emoji) quand stdout est redirigé vers un fichier sous Windows
    env["PYTHONUNBUFFERED"] = "1"  # sinon les print() restent bloqués dans un tampon et le .log reste vide tant que le process tourne (ou pire, en cas de crash, rien n'est jamais écrit)
    env.update(app.get("env_extra", {}))
    if simulate and app["name"] == "NetScope":
        # Cohérence avec PhishHunter/Sentinel : NetScope ne "vit" (scan auto +
        # notifications CrisisBot) qu'en mode démo --simulate, jamais par défaut.
        env["NETSCOPE_AUTO_SCAN"] = "1"
    if simulate and app["name"] == "DarkWatch":
        # Même logique : DarkWatch ne revérifie les comptes tout seul qu'en
        # mode démo --simulate, pour que les 4 agents réagissent de façon
        # cohérente sans commande séparée à lancer.
        env["DARKWATCH_AUTO_SCAN"] = "1"
    cmd = app["cmd"]()
    print(f"[launch_all] Démarrage de {app['name']} sur http://localhost:{app['port']}{app['home_path']}  (log: {log_path.name})")
    proc = subprocess.Popen(cmd, cwd=str(app["cwd"]), stdout=log_file, stderr=subprocess.STDOUT, env=env)
    processes.append({"name": app["name"], "proc": proc, "log_file": log_file})


def build_home_html():
    cards = "\n".join(
        f'''
        <a class="card" href="http://localhost:{a['port']}{a['home_path']}" target="_blank">
          <div class="icon" style="background:#{a['accent']}1A; color:#{a['accent']};">{a['initial']}</div>
          <h2>{a['name']}</h2>
          <p>{a['desc']}</p>
          <span class="port" style="color:#{a['accent']};">localhost:{a['port']}</span>
        </a>'''
        for a in APPS
    )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Accueil — Agents sécurité</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%2314181F'/><text x='50' y='68' font-size='56' text-anchor='middle'>🛡️</text></svg>">
<style>
  :root {{
    --bg: #F1F2F6; --card: #FFFFFF; --border: #E5E7EB; --border-strong: #D1D5DB;
    --text: #14181F; --text-dim: #5B6472; --text-faint: #9AA2AD;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); margin:0; padding: 56px 48px; }}
  .shell {{ max-width: 980px; margin: 0 auto; }}
  .eyebrow {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-faint); margin: 0 0 8px; }}
  h1 {{ font-weight: 600; font-size: 30px; margin: 0 0 6px; }}
  .sub {{ color: var(--text-dim); margin: 0 0 40px; font-size: 14.5px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap: 20px; }}
  .card {{
    display: block; background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 22px; text-decoration: none; color: inherit;
    box-shadow: 0 1px 2px rgba(20,24,31,0.04);
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  }}
  .card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(20,24,31,0.08); border-color: var(--border-strong); }}
  .icon {{
    width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 16px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    margin-bottom: 14px;
  }}
  .card h2 {{ margin: 0 0 6px; font-size: 16px; font-weight: 600; color: var(--text); }}
  .card p {{ margin: 0 0 16px; font-size: 13px; color: var(--text-dim); line-height: 1.45; }}
  .port {{ font-size: 12px; font-weight: 600; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
</style>
</head>
<body>
  <div class="shell">
    <p class="eyebrow">Console centrale</p>
    <h1>Accueil</h1>
    <p class="sub">Les 4 agents tournent en arrière-plan. Clique une carte pour ouvrir le projet (nouvel onglet).</p>
    <div class="grid">
      {cards}
    </div>
  </div>
</body>
</html>"""


class HomeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(build_home_html().encode("utf-8"))

    def log_message(self, format, *args):
        pass


def main():
    simulate = "--simulate" in sys.argv

    for app in APPS:
        start_app(app, simulate=simulate)

    print(f"\n[launch_all] Page d'accueil : http://localhost:{HOME_PORT}")
    print("[launch_all] (laisse quelques secondes aux modèles ML pour charger)")
    if simulate:
        print("[launch_all] --simulate actif : un flux d'événements factices va démarrer dans ~25s")
        print("[launch_all]   (laisse le temps à NetScope/PhishHunter de finir de charger leurs modèles)")
        print("[launch_all]   (PhishHunter + Sentinel + NetScope via event_simulator.py, NetScope + DarkWatch via leur auto-scan aussi)")
    else:
        print("[launch_all] Mode silencieux (par défaut) : aucun agent ne notifie CrisisBot tout seul.")
        print("[launch_all]   Relance avec --simulate pour voir les 4 agents réagir automatiquement.")
    print("[launch_all] Ctrl+C pour tout arrêter.\n")

    threading.Thread(
        target=lambda: (time.sleep(1.5), webbrowser.open(f"http://localhost:{HOME_PORT}")),
        daemon=True,
    ).start()

    simulator_stop = threading.Event()
    if simulate:
        def _start_simulator_delayed():
            # NetScope (modèle + SHAP) et PhishHunter (moteur de scoring + client Groq)
            # peuvent prendre plus de 10-15s à charger au premier démarrage sous Windows.
            # 8s ne suffisait pas : le simulateur tapait dessus avant que le port soit
            # prêt, d'où des "injoignable (status=0)" qui n'étaient pas de vraies pannes.
            time.sleep(25)
            try:
                from event_simulator import run_simulator
                run_simulator(stop_event=simulator_stop)
            except Exception as e:
                print(f"[launch_all] Simulateur d'événements indisponible : {e}")

        threading.Thread(target=_start_simulator_delayed, daemon=True).start()

    httpd = http.server.ThreadingHTTPServer(("", HOME_PORT), HomeHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        simulator_stop.set()
        print("\n[launch_all] Arrêt de tous les serveurs...")
        for p in processes:
            p["proc"].terminate()
        for p in processes:
            try:
                p["proc"].wait(timeout=5)
            except subprocess.TimeoutExpired:
                p["proc"].kill()
            p["log_file"].close()
        print("[launch_all] Terminé.")


if __name__ == "__main__":
    main()
