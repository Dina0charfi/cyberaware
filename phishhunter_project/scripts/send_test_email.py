"""
Envoie un email de test à la passerelle SMTP locale.
Lancer : python scripts/send_test_email.py
"""
import smtplib
from email.mime.text import MIMEText

msg = MIMEText("Cliquez ici immediatement pour confirmer votre mot de passe avant expiration de votre compte.")
msg["From"] = "support@banque-partenere-secure.com"
msg["To"] = "employe@banque.example"
msg["Subject"] = "URGENT - Mise a jour de vos identifiants sous 24h"

with smtplib.SMTP("127.0.0.1", 8025) as server:
    server.sendmail(msg["From"], [msg["To"]], msg.as_string())

print("Email de test envoyé.")
