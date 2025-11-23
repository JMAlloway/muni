import smtplib
from email.mime.text import MIMEText

from app.core.settings import settings


def send_email(to_email: str, subject: str, html_body: str):
    """Send HTML email via Mailtrap (or local SMTP)."""
    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        try:
            # Attempt STARTTLS when supported; continue without if the server doesn't offer it.
            server.starttls()  # enable TLS (Mailtrap accepts STARTTLS on 2525)
        except smtplib.SMTPException:
            pass
        if getattr(settings, "SMTP_USERNAME", None) and getattr(settings, "SMTP_PASSWORD", None):
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM, [to_email], msg.as_string())
        print(f"Sent email to {to_email}")
