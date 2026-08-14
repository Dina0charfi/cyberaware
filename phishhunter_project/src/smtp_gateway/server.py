"""
PhishHunter — Passerelle SMTP (prototype)
Lancer séparément : python -m src.smtp_gateway.server
Écoute sur le port 8025 (test local).
"""
import asyncio
import email
from email.message import Message
import requests
from aiosmtpd.controller import Controller

PHISHHUNTER_API_URL = "http://127.0.0.1:8000/webhook/email"


def extract_body(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(errors="ignore")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="ignore") if payload else str(msg.get_payload())


class PhishHunterSMTPHandler:
    async def handle_DATA(self, server, session, envelope):
        try:
            msg = email.message_from_bytes(envelope.content)
            sender = msg.get("From", envelope.mail_from)
            subject = msg.get("Subject", "")
            body = extract_body(msg)

            print(f"[SMTP] Email reçu — de {sender} — sujet: {subject}")

            response = requests.post(
                PHISHHUNTER_API_URL,
                json={"sender": sender, "subject": subject, "body": body},
                timeout=15,
            )

            if response.ok:
                result = response.json()
                print(f"[SMTP] Analysé — score {result.get('risk_score')}/100")
            else:
                print(f"[SMTP] Erreur d'analyse : {response.status_code}")

        except Exception as e:
            print(f"[SMTP] Erreur de traitement : {e}")

        return "250 Message accepté pour analyse"


def run(host="127.0.0.1", port=8025):
    controller = Controller(PhishHunterSMTPHandler(), hostname=host, port=port)
    controller.start()
    print(f"[SMTP] Passerelle PhishHunter en écoute sur {host}:{port}")
    print("[SMTP] Ctrl+C pour arrêter")
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        controller.stop()


if __name__ == "__main__":
    run()