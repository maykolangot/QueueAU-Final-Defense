# utils/email_sender.py
from django.core.mail import EmailMessage, get_connection
from django.conf import settings
import itertools
import smtplib

account_cycle = itertools.cycle(settings.EMAIL_ACCOUNTS)

def send_rolling_email(subject, body, to_list, attachments=None):
    """
    Sends an email using Gmail SMTP, rotating between multiple accounts.
    Optionally attaches files (list of tuples: (filename, content_bytes, mimetype)).
    """
    for _ in range(len(settings.EMAIL_ACCOUNTS)):
        account = next(account_cycle)
        try:
            # Create a fresh SMTP connection for this account
            connection = get_connection(
                host=settings.EMAIL_HOST,
                port=settings.EMAIL_PORT,
                username=account["EMAIL_HOST_USER"],
                password=account["EMAIL_HOST_PASSWORD"],
                use_tls=settings.EMAIL_USE_TLS,
                fail_silently=False
            )

            email = EmailMessage(
                subject,
                body,
                account["EMAIL_HOST_USER"],
                to_list,
                connection=connection
            )

            # ✅ Add attachments if provided
            if attachments:
                for filename, data, mimetype in attachments:
                    email.attach(filename, data, mimetype)

            email.send()
            print(f"✅ Sent via {account['EMAIL_HOST_USER']}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ Auth failed for {account['EMAIL_HOST_USER']}: {e}")
        except smtplib.SMTPException as e:
            print(f"⚠️ SMTP error for {account['EMAIL_HOST_USER']}: {e}")
            continue

    print("❌ All accounts failed to send.")
    return False
