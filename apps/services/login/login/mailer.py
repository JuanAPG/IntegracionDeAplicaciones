"""
apps/services/login/login/mailer.py
Envio del correo de verificacion mediante el sendmail alojado en la
instancia (SMTP local, tipicamente localhost:25). No se usa POP ni IMAP
en ningun punto: solo se ENTREGA correo, nunca se lee un buzon.

Si el sendmail no responde, se informa al llamador con MailerError para
que el registro quede como "pendiente de verificacion" en lugar de
fingir un envio que no ocurrio.
"""
import logging
import smtplib
from email.message import EmailMessage

import config
from errors import MailerError

log = logging.getLogger("library.login")


def build_verification_message(to_email, full_name, verify_url):
    service = config.MAIL_SERVICE_NAME
    msg = EmailMessage()
    msg["Subject"] = f"{service}: verifique su correo"
    msg["From"] = config.SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Hola {full_name}:\n\n"
        f"Para activar su cuenta de {service}, abra este enlace:\n\n"
        f"{verify_url}\n\n"
        f"El enlace vence en {config.TOKEN_TTL_HOURS} horas. "
        "Si usted no solicito este registro, ignore el mensaje.\n"
    )
    return msg


def send_verification_email(to_email, full_name, verify_url):
    """Entrega el mensaje al sendmail local. Lanza MailerError si falla."""
    msg = build_verification_message(to_email, full_name, verify_url)
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT,
                           timeout=config.SMTP_TIMEOUT) as smtp:
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        log.error("sendmail %s:%s no acepto el correo para %s: %s",
                  config.SMTP_HOST, config.SMTP_PORT, to_email, exc)
        raise MailerError(
            "No se pudo enviar el correo de verificacion.",
            [f"sendmail en {config.SMTP_HOST}:{config.SMTP_PORT} no responde. "
             "Su cuenta quedo pendiente de verificacion; solicite el reenvio "
             "cuando el servicio de correo este disponible."]) from exc
    log.info("Correo de verificacion entregado a %s via %s:%s",
             to_email, config.SMTP_HOST, config.SMTP_PORT)
    return True
