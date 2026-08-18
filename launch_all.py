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
    {
        "name": "Serious Game",
        "port": 8880,
        "home_path": "/",
        "cwd": ROOT / "serious_game_project",
        "cmd": lambda: [sys.executable, "server.py"],
        "env_extra": {"SERIOUSGAME_PORT": "8880"},
        "desc": "Simulateur pédagogique d'ingénierie sociale (\"dans la peau de l'attaquant\")",
        "accent": "EA580C",
        "initial": "G",
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
    if simulate and app["name"] == "Serious Game":
        # Même logique encore : sans --simulate, personne ne joue tout seul —
        # une vraie personne doit choisir une cible/un vecteur dans le
        # dashboard. En mode démo, cette variable démarre une boucle qui joue
        # à sa place (voir serious_game_project/auto_simulate.py).
        env["SERIOUSGAME_AUTO_SIMULATE"] = "1"
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
    agent_submenu = "\n".join(
        f'          <a class="nav-subitem" href="http://localhost:{a["port"]}{a["home_path"]}" target="_blank">'
        f'<span class="dot" style="background:#{a["accent"]};"></span> {a["name"]}</a>'
        for a in APPS if a["name"] != "Serious Game"
    )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Accueil — Agents sécurité</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='22' fill='%2314181F'/><text x='50' y='68' font-size='56' text-anchor='middle'>🛡️</text></svg>">
<style>
  :root {{
    --sidebar-bg: #14181F; --sidebar-border: #262b35; --sidebar-text: #C7CCD6; --sidebar-text-dim: #7A8296;
    --sidebar-active-bg: #1E2530;
    --bg: #F1F2F6; --card: #FFFFFF; --border: #E5E7EB; --border-strong: #D1D5DB;
    --text: #14181F; --text-dim: #5B6472; --text-faint: #9AA2AD; --accent: #2563EB;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); margin: 0; display: flex; min-height: 100vh;
  }}

  .sidebar {{
    width: 260px; flex-shrink: 0; background: var(--sidebar-bg); color: var(--sidebar-text);
    display: flex; flex-direction: column; height: 100vh; position: sticky; top: 0;
    border-right: 1px solid var(--sidebar-border);
  }}
  .sidebar-scroll {{ flex: 1; overflow-y: auto; padding-bottom: 12px; }}
  .brand {{ display: flex; align-items: center; gap: 10px; padding: 20px 18px 16px; border-bottom: 1px solid var(--sidebar-border); }}
  .brand .logo {{
    width: 34px; height: 34px; border-radius: 9px; background: #2563EB; color: white; display: flex;
    align-items: center; justify-content: center; font-weight: 700; font-size: 13px;
    font-family: ui-monospace, Menlo, monospace;
  }}
  .brand .name {{ font-weight: 700; font-size: 14.5px; color: #fff; line-height: 1.2; }}
  .brand .by {{ font-size: 10.5px; color: var(--sidebar-text-dim); }}

  .client-box {{ padding: 14px 18px; border-bottom: 1px solid var(--sidebar-border); }}
  .client-box .eyebrow {{ font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--sidebar-text-dim); margin: 0 0 8px; }}
  .client-chip {{ display: flex; align-items: center; gap: 8px; }}
  .client-chip .avatar {{ width: 26px; height: 26px; border-radius: 7px; background: #0F6E56; color: #fff; font-size: 11.5px;
    font-weight: 700; display: flex; align-items: center; justify-content: center; }}
  .client-chip span {{ font-size: 13.5px; font-weight: 600; color: #fff; }}

  .incident-btn {{
    width: 100%; background: #3a1414; border: 1px solid #5c1f1f; color: #ff8a8a; border-radius: 9px;
    padding: 10px 12px; font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px;
    cursor: pointer; text-decoration: none;
  }}

  .nav-section {{ padding: 16px 10px 6px; }}
  .nav-eyebrow {{
    font-size: 10px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--sidebar-text-dim);
    padding: 0 10px; margin: 0 0 6px; font-weight: 600;
  }}
  .nav-item {{
    display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 8px;
    font-size: 13.5px; color: var(--sidebar-text); text-decoration: none; margin-bottom: 2px; cursor: pointer;
  }}
  .nav-item:hover {{ background: #1a1f29; color: #fff; }}
  .nav-item.active {{ background: var(--sidebar-active-bg); color: #fff; font-weight: 600; }}
  .nav-item .dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
  .nav-toggle {{
    display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 10px;
    border-radius: 8px; font-size: 13.5px; color: var(--sidebar-text); cursor: pointer; margin-bottom: 2px;
    user-select: none;
  }}
  .nav-toggle:hover {{ background: #1a1f29; color: #fff; }}
  .nav-toggle-label {{ display: flex; align-items: center; gap: 10px; }}
  .nav-chevron {{ transition: transform 0.15s ease; font-size: 10px; color: var(--sidebar-text-dim); }}
  .nav-toggle.open .nav-chevron {{ transform: rotate(90deg); }}
  .nav-submenu {{
    max-height: 0; overflow: hidden; transition: max-height 0.18s ease; margin-left: 8px;
    border-left: 1px solid var(--sidebar-border); padding-left: 8px;
  }}
  .nav-submenu.open {{ max-height: 400px; }}
  .nav-subitem {{
    display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 8px;
    font-size: 13px; color: var(--sidebar-text); text-decoration: none; margin-bottom: 1px;
  }}
  .nav-subitem:hover {{ background: #1a1f29; color: #fff; }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}

  .sidebar-footer {{ border-top: 1px solid var(--sidebar-border); padding: 14px 16px; margin-top: auto; font-size: 11.5px; color: var(--sidebar-text-dim); }}

  .main {{ flex: 1; padding: 48px 48px; max-width: 1080px; }}
  .eyebrow {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--text-faint); margin: 0 0 8px;
  }}
  h1 {{ font-weight: 700; font-size: 30px; margin: 0 0 6px; color: #1e293b; }}
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
  .card h2 {{ margin: 0 0 6px; font-size: 16px; font-weight: 700; color: #1e293b; }}
  .card p {{ margin: 0 0 16px; font-size: 13px; color: var(--text-dim); line-height: 1.45; }}
  .port {{ font-size: 12px; font-weight: 600; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  .note {{
    margin-top: 28px; background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px; padding: 14px 18px;
    font-size: 13px; color: #1e40af; line-height: 1.6;
  }}

  .head-right {{ display: flex; align-items: center; gap: 14px; color: var(--text-dim); font-size: 13.5px; }}
  .page-head {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }}
  .scorm-btn {{ background: var(--card); border: 1px solid var(--border); border-radius: 9px; padding: 9px 14px;
    font-size: 13px; color: var(--text); font-weight: 600; cursor: pointer; }}
  .trophy-bar {{
    background: #14181F; color: #fff; border-radius: 12px; padding: 14px 20px; display: flex; align-items: center;
    justify-content: space-between; margin-bottom: 26px; font-size: 14px;
  }}
  .trophy-bar b {{ font-weight: 700; }}
  .trophy-bar a {{ color: #7dd3fc; text-decoration: none; font-weight: 600; font-size: 13px; }}
  .mod-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
  .mod-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 20px; cursor: pointer; }}
  .mod-icon {{ width: 38px; height: 38px; border-radius: 9px; display: flex; align-items: center; justify-content: center;
    font-size: 18px; margin-bottom: 14px; }}
  .mod-card h3 {{ margin: 0 0 4px; font-size: 15.5px; font-weight: 700; color: #1e293b; }}
  .mod-card .duration {{ font-size: 12px; color: var(--text-faint); margin-bottom: 14px; }}
  .progress-track {{ background: #EEF0F4; border-radius: 999px; height: 7px; overflow: hidden; margin-bottom: 10px; }}
  .progress-fill {{ height: 100%; border-radius: 999px; background: #10B981; }}
  .mod-foot {{ display: flex; justify-content: space-between; align-items: center; font-size: 12.5px; color: var(--text-dim); }}

  .back-link {{ display: inline-flex; align-items: center; gap: 6px; color: var(--text-dim); font-size: 13px;
    text-decoration: none; cursor: pointer; margin-bottom: 14px; }}
  .back-link:hover {{ color: var(--text); }}
  .lesson-title {{ font-size: 26px; font-weight: 700; color: #1e293b; margin: 0 0 22px; }}
  .lesson-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 24px; max-width: 830px; }}
  .lesson-section-title {{ font-size: 14px; font-weight: 700; color: #1e293b; margin: 0 0 14px; display: flex; align-items: center; gap: 6px; }}
  .video-box {{ background: #0B0B0F; border-radius: 12px; aspect-ratio: 16/9; position: relative; margin-bottom: 22px;
    display: flex; align-items: center; justify-content: center; overflow: hidden; }}
  .video-box video {{ width: 100%; height: 100%; display: block; background: #000; }}
  .video-box .avatar-ph {{ width: 120px; height: 120px; border-radius: 50%; background: #4B5563; display:flex;
    align-items:center; justify-content:center; font-size: 44px; }}
  .video-controls {{ position: absolute; bottom: 0; left: 0; right: 0; padding: 10px 14px; background: linear-gradient(transparent, rgba(0,0,0,0.55));
    display: flex; align-items: center; gap: 10px; color: #fff; font-size: 12.5px; }}
  .video-controls .track {{ flex: 1; height: 3px; background: rgba(255,255,255,0.35); border-radius: 999px; }}
  .key-points {{ list-style: none; margin: 0 0 22px; padding: 0; }}
  .key-points li {{ display: flex; gap: 10px; align-items: flex-start; font-size: 14px; color: var(--text); line-height: 1.55; margin-bottom: 12px; }}
  .key-points li::before {{ content: "•"; color: var(--accent); font-weight: 700; margin-top: -1px; }}
  .lesson-cta {{ width: 100%; background: #93A9F8; color: #fff; border: none; border-radius: 10px; padding: 13px;
    font-size: 14.5px; font-weight: 700; cursor: not-allowed; margin-bottom: 10px; }}
  .lesson-hint {{ font-size: 12px; color: var(--text-faint); text-align: center; margin: 0; }}
</style>
</head>
<body>
  <div class="sidebar">
    <div class="sidebar-scroll">
      <div class="brand">
        <div class="logo">CA</div>
        <div>
          <div class="name">CYBERAWARE</div>
          <div class="by">by Hydatis</div>
        </div>
      </div>

      <div class="client-box">
        <p class="eyebrow">Espace client</p>
        <div class="client-chip">
          <div class="avatar">BA</div>
          <span>Banque ABC</span>
        </div>
      </div>

      <div class="nav-section">
        <p class="nav-eyebrow">Pilotage</p>
        <a class="nav-item active" data-page="agents">
          <span class="dot" style="background:#fff;"></span> Accueil
        </a>
        <a class="nav-item" data-page="formation">
          <span class="dot" style="background:#60A5FA;"></span> Formation à la cybersécurité
        </a>
        <a class="nav-item" href="http://localhost:8880/" target="_blank">
          <span class="dot" style="background:#EA580C;"></span> Serious Game
        </a>
        <div class="nav-toggle" id="agentsToggle">
          <span class="nav-toggle-label"><span class="dot" style="background:#94A3B8;"></span> Agents</span>
          <span class="nav-chevron">▶</span>
        </div>
        <div class="nav-submenu" id="agentsSubmenu">
{agent_submenu}
        </div>
      </div>
    </div>

    <div class="sidebar-footer">
      <button class="incident-btn">🚩 Signaler un incident</button>
    </div>
  </div>

  <div class="main">
    <div id="page-agents">
      <p class="eyebrow">Console centrale</p>
      <h1>Agents</h1>
      <p class="sub">Les 6 agents tournent en arrière-plan. Clique une carte pour ouvrir le projet (nouvel onglet).</p>
      <div class="grid">
        {cards}
      </div>
    </div>

    <div id="page-formation" style="display:none;">
      <p class="eyebrow">Mon parcours</p>
      <div class="page-head">
        <h1>Formation à la cybersécurité</h1>
        <div class="head-right">
          <span id="modulesCompletedCount">0/9 modules complétés</span>
        </div>
      </div>

      <div class="trophy-bar">
        <span>🏆 <b id="trophyPoints">0 point</b> · Niveau — · Rang —</span>
        <a href="#">Voir le classement →</a>
      </div>

      <div class="mod-grid">
        <div class="mod-card" data-key="phishing" onclick="openLesson('phishing')">
          <div class="mod-icon" style="background:#EEF2FF;">📧</div>
          <h3>Reconnaître le phishing</h3>
          <div class="duration">5 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="passwords" onclick="openLesson('passwords')">
          <div class="mod-icon" style="background:#FEF3C7;">🔑</div>
          <h3>Mots de passe robustes</h3>
          <div class="duration">4 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="ceofraud" onclick="openLesson('ceofraud')">
          <div class="mod-icon" style="background:#DCFCE7;">💳</div>
          <h3>Fraude au virement (CEO fraud)</h3>
          <div class="duration">6 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="guichet" onclick="openLesson('guichet')">
          <div class="mod-icon" style="background:#DBEAFE;">🏦</div>
          <h3>Ingénierie sociale au guichet</h3>
          <div class="duration">5 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="mobilemoney" onclick="openLesson('mobilemoney')">
          <div class="mod-icon" style="background:#EDE9FE;">📱</div>
          <h3>Fraude Mobile Money</h3>
          <div class="duration">5 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="dataprotection" onclick="openLesson('dataprotection')">
          <div class="mod-icon" style="background:#FFEDD5;">🔒</div>
          <h3>Protection des données clients</h3>
          <div class="duration">4 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="ransomware" onclick="openLesson('ransomware')">
          <div class="mod-icon" style="background:#DCFCE7;">🦠</div>
          <h3>Rançongiciel (ransomware)</h3>
          <div class="duration">5 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="pcidss" onclick="openLesson('pcidss')">
          <div class="mod-icon" style="background:#DBEAFE;">💳</div>
          <h3>Sensibilisation PCI DSS</h3>
          <div class="duration">6 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
        <div class="mod-card" data-key="swiftcsp" onclick="openLesson('swiftcsp')">
          <div class="mod-icon" style="background:#F1F5F9;">🏛️</div>
          <h3>Sensibilisation SWIFT CSP</h3>
          <div class="duration">6 min</div>
          <div class="progress-track"><div class="progress-fill" style="width:0%;"></div></div>
          <div class="mod-foot"><span class="mod-pct">0% complété</span><span class="mod-score"></span></div>
        </div>
      </div>

      <div class="note">
        💡 Contenu de formation local (mêmes modules que l'app CYBERAWARE). La progression avance en regardant la
        vraie vidéo (uniquement pour les 5 modules qui en ont une pour l'instant — phishing, mots de passe, virement,
        Mobile Money, ingénierie sociale au guichet)
        et passe à 100% quand la vidéo est terminée ; les autres modules restent à 0% tant qu'aucune vidéo n'est
        fournie. Sauvegardée dans ce navigateur (pas encore reliée à un vrai compte utilisateur).
      </div>
    </div>

    <div id="page-lesson" style="display:none;">
      <a class="back-link" onclick="showPage('formation')">← Retour à la formation</a>
      <h1 class="lesson-title" id="lessonTitle">—</h1>

      <div class="lesson-card">
        <p class="lesson-section-title">🎬 Leçon vidéo</p>
        <div class="video-box" id="lessonVideoBox">
          <div class="avatar-ph">🧑‍💼</div>
          <div class="video-controls">
            <span>▶</span><span id="lessonDuration">0:00 / 0:00</span>
            <div class="track"></div>
            <span>🔊</span><span>⛶</span><span>⋮</span>
          </div>
        </div>

        <p class="lesson-section-title">📌 Points clés à retenir</p>
        <ul class="key-points" id="lessonPoints"></ul>

        <button class="lesson-cta" disabled>Continuer vers la mise en situation →</button>
        <p class="lesson-hint">Visionnez la vidéo pour continuer (suivi de complétion type SCORM).</p>
      </div>
    </div>
  </div>

  <script>
    const LESSONS = {{
      phishing: {{
        title: "Reconnaître le phishing", duration: "0:00 / 0:53", video: "/videos/phishing.mp4",
        points: [
          "Un email de phishing crée toujours un sentiment d'urgence ou de peur pour pousser à agir vite.",
          "Vérifiez l'adresse de l'expéditeur en entier, pas seulement le nom affiché.",
          "Survolez un lien (sans cliquer) pour voir la véritable URL de destination avant d'y accéder.",
          "En cas de doute, contactez l'expéditeur supposé par un canal indépendant (téléphone, autre email connu).",
        ],
      }},
      passwords: {{
        title: "Mots de passe robustes", duration: "0:00 / 0:47", video: "/videos/mdpvideo.mp4",
        points: [
          "Utilisez un mot de passe unique par compte, jamais réutilisé ailleurs.",
          "Préférez une phrase de passe longue (12+ caractères) à un mot de passe complexe mais court.",
          "Activez la double authentification (MFA) partout où c'est possible.",
          "Ne partagez jamais votre mot de passe, même avec un collègue ou le support IT — personne légitime ne le demande.",
        ],
      }},
      ceofraud: {{
        title: "Fraude au virement (CEO fraud)", duration: "0:00 / 1:02", video: "/videos/virementvideo.mp4",
        points: [
          "Une demande de virement urgente et confidentielle de la « direction » doit toujours être vérifiée par un second canal (appel au numéro connu).",
          "Méfiez-vous des demandes qui contournent la procédure habituelle de validation à deux signatures.",
          "Vérifiez l'adresse email exacte de l'expéditeur — les fraudeurs imitent souvent un nom de domaine très proche.",
          "En cas de doute, ne validez rien avant confirmation explicite en personne ou par téléphone au numéro déjà connu.",
        ],
      }},
      guichet: {{
        title: "Ingénierie sociale au guichet", duration: "0:00 / 0:55", video: "/videos/socialmanipulate.mp4",
        points: [
          "Vérifiez toujours l'identité du client avec une pièce d'identité officielle avant toute opération sensible.",
          "Restez vigilant face à la pression sociale (urgence, autorité prétendue, flatterie) utilisée pour contourner les procédures.",
          "Ne donnez jamais d'information sur un autre client, même si l'interlocuteur semble bien informé.",
          "En cas de doute sur une demande inhabituelle, appliquez la procédure d'escalade vers un responsable.",
        ],
      }},
      mobilemoney: {{
        title: "Fraude Mobile Money", duration: "0:00 / 0:50", video: "/videos/fraudemobile.mp4",
        points: [
          "Vérifiez systématiquement l'identité du bénéficiaire avant de valider un transfert Mobile Money.",
          "Méfiez-vous des messages annonçant un gain, un remboursement ou un blocage de compte demandant une action immédiate.",
          "Ne communiquez jamais un code de confirmation reçu par SMS à un tiers, même s'il se présente comme un agent.",
          "Rappelez au client qu'aucune institution légitime ne demande de code secret par téléphone.",
        ],
      }},
      dataprotection: {{
        title: "Protection des données clients", duration: "0:00 / 0:44",
        points: [
          "N'accédez qu'aux dossiers clients nécessaires à votre tâche en cours (principe du besoin d'en connaître).",
          "Ne transférez jamais de données clients vers une messagerie personnelle ou un support USB non chiffré.",
          "Verrouillez votre poste dès que vous vous en éloignez, même quelques minutes.",
          "Signalez immédiatement toute perte ou tout accès suspect à un dossier client.",
        ],
      }},
      ransomware: {{
        title: "Rançongiciel (ransomware)", duration: "0:00 / 0:58",
        points: [
          "N'ouvrez jamais une pièce jointe ou un lien inattendu, même s'il semble venir d'un collègue.",
          "Un ralentissement soudain du poste ou des fichiers qui deviennent illisibles doivent être signalés immédiatement, sans attendre.",
          "Débranchez le réseau (câble/Wi-Fi) dès le moindre soupçon, avant de contacter le support IT.",
          "Ne payez jamais une rançon vous-même — c'est une décision qui remonte à la direction et à la sécurité informatique.",
        ],
      }},
      pcidss: {{
        title: "Sensibilisation PCI DSS", duration: "0:00 / 1:05",
        points: [
          "Ne notez ni ne stockez jamais un numéro de carte complet en dehors des systèmes autorisés.",
          "Masquez systématiquement les numéros de carte affichés sur les reçus et écrans.",
          "N'envoyez jamais de données de carte par email ou messagerie instantanée, même en interne.",
          "Signalez toute anomalie sur un terminal de paiement (autocollant suspect, appareil ajouté) au responsable sécurité.",
        ],
      }},
      swiftcsp: {{
        title: "Sensibilisation SWIFT CSP", duration: "0:00 / 1:08",
        points: [
          "Respectez strictement la séparation des rôles entre initiation et validation d'un message SWIFT.",
          "Ne partagez jamais vos identifiants d'accès aux systèmes de paiement, même temporairement.",
          "Vérifiez que chaque poste ayant accès à l'environnement SWIFT reste isolé et à jour des correctifs de sécurité.",
          "Signalez immédiatement tout message SWIFT sortant non reconnu ou toute tentative de connexion suspecte.",
        ],
      }},
    }};

    const TOTAL_MODULES = document.querySelectorAll('.mod-card').length;
    const PROGRESS_KEY = 'cw_module_progress';

    function loadProgress() {{
      try {{
        return JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {{}};
      }} catch (e) {{
        return {{}};
      }}
    }}

    function setModuleProgress(key, pct) {{
      const progress = loadProgress();
      const clamped = Math.max(0, Math.min(100, Math.round(pct)));
      // ne jamais faire redescendre une progression déjà enregistrée (ex: on rembobine la vidéo)
      if ((progress[key] || 0) >= clamped) return;
      progress[key] = clamped;
      localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
      applyProgressToCards();
    }}

    function applyProgressToCards() {{
      const progress = loadProgress();
      let completed = 0;
      document.querySelectorAll('.mod-card').forEach(card => {{
        const key = card.getAttribute('data-key');
        const pct = progress[key] || 0;
        card.querySelector('.progress-fill').style.width = pct + '%';
        card.querySelector('.mod-pct').textContent = pct + '% complété';
        if (pct >= 100) completed += 1;
      }});
      const countEl = document.getElementById('modulesCompletedCount');
      if (countEl) countEl.textContent = `${{completed}}/${{TOTAL_MODULES}} modules complétés`;
      const pointsEl = document.getElementById('trophyPoints');
      if (pointsEl) pointsEl.textContent = `${{completed * 100}} point${{completed === 1 ? '' : 's'}}`;
    }}

    function openLesson(key) {{
      const lesson = LESSONS[key];
      if (!lesson) return;
      document.getElementById('lessonTitle').textContent = lesson.title;
      document.getElementById('lessonPoints').innerHTML = lesson.points.map(p => `<li>${{p}}</li>`).join('');

      const videoBox = document.getElementById('lessonVideoBox');
      if (lesson.video) {{
        videoBox.innerHTML = `<video controls preload="metadata" src="${{lesson.video}}"></video>`;
        const videoEl = videoBox.querySelector('video');
        videoEl.addEventListener('timeupdate', () => {{
          if (videoEl.duration) {{
            setModuleProgress(key, (videoEl.currentTime / videoEl.duration) * 100);
          }}
        }});
        videoEl.addEventListener('ended', () => setModuleProgress(key, 100));
      }} else {{
        videoBox.innerHTML = `
          <div class="avatar-ph">🧑‍💼</div>
          <div class="video-controls">
            <span>▶</span><span>${{lesson.duration}}</span>
            <div class="track"></div>
            <span>🔊</span><span>⛶</span><span>⋮</span>
          </div>`;
      }}
      showPage('lesson');
    }}

    function showPage(page) {{
      document.getElementById('page-agents').style.display = page === 'agents' ? '' : 'none';
      document.getElementById('page-formation').style.display = page === 'formation' ? '' : 'none';
      document.getElementById('page-lesson').style.display = page === 'lesson' ? '' : 'none';
      document.querySelectorAll('.nav-item[data-page]').forEach(i => i.classList.remove('active'));
      const navKey = page === 'lesson' ? 'formation' : page;
      const navItem = document.querySelector(`.nav-item[data-page="${{navKey}}"]`);
      if (navItem) navItem.classList.add('active');
    }}

    document.querySelectorAll('.nav-item[data-page]').forEach(item => {{
      item.addEventListener('click', () => showPage(item.getAttribute('data-page')));
    }});

    const agentsToggle = document.getElementById('agentsToggle');
    const agentsSubmenu = document.getElementById('agentsSubmenu');
    if (agentsToggle && agentsSubmenu) {{
      agentsToggle.addEventListener('click', () => {{
        agentsToggle.classList.toggle('open');
        agentsSubmenu.classList.toggle('open');
      }});
    }}

    if (window.location.hash === '#formation') {{
      showPage('formation');
    }}

    applyProgressToCards();
  </script>
</body>
</html>"""


# Vidéos de leçon réelles pour la page "Formation à la cybersécurité" — déposées à la
# racine du projet (à côté de launch_all.py) par l'utilisateur. Seuls ces 3 noms de
# fichiers précis sont servables (whitelist), pour ne jamais exposer le reste du disque
# via /videos/<n'importe quoi>.
VIDEOS_DIR = ROOT / "videos"

LESSON_VIDEOS = {
    "phishing.mp4": VIDEOS_DIR / "phishing.mp4",
    "mdpvideo.mp4": VIDEOS_DIR / "mdpvideo.mp4",
    "virementvideo.mp4": VIDEOS_DIR / "virementvideo.mp4",
    "fraudemobile.mp4": VIDEOS_DIR / "fraudemobile.mp4",
    "socialmanipulate.mp4": VIDEOS_DIR / "socialmanipulate.mp4",
}


class HomeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/videos/"):
            self._serve_video(self.path.removeprefix("/videos/"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(build_home_html().encode("utf-8"))

    def _serve_video(self, filename):
        """
        Diffuse un fichier .mp4 de leçon, avec support des requêtes Range (obligatoire
        pour que le curseur de la balise <video> du navigateur puisse avancer/reculer
        sans tout retélécharger depuis le début).
        """
        path = LESSON_VIDEOS.get(filename)
        if path is None or not path.exists():
            self.send_response(404)
            self.end_headers()
            return

        file_size = path.stat().st_size
        range_header = self.headers.get("Range")

        try:
            with open(path, "rb") as f:
                if range_header:
                    start, end = 0, file_size - 1
                    try:
                        range_spec = range_header.strip().split("=", 1)[1]
                        start_str, end_str = range_spec.split("-", 1)
                        start = int(start_str) if start_str else 0
                        end = int(end_str) if end_str else file_size - 1
                    except (IndexError, ValueError):
                        pass
                    end = min(end, file_size - 1)
                    length = max(0, end - start + 1)

                    self.send_response(206)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    self.end_headers()

                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(file_size))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Le navigateur a coupé/relancé la requête (normal en cas de seek dans la
            # vidéo) — rien à faire, juste ne pas laisser planter le serveur.
            pass

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
        print("[launch_all]   (Serious Game joue aussi tout seul, une tentative toutes les ~20s — voir auto_simulate.py)")
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
