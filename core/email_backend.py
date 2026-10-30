from django.core.mail.backends.smtp import EmailBackend
import ssl
import smtplib

class UnsafeEmailBackend(EmailBackend):
    """
    Backend de email que evita la verificación de certificado SSL.
    Se usa temporalmente mientras Resend renueva su certificado.
    """
    def open(self):
        if self.connection:
            return False
        try:
            connection = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            # ~ connection = smtplib.SMTP(self.host, self.port, timeout=10)
            context = ssl._create_unverified_context()
            connection.starttls(context=context)
            if self.username and self.password:
                connection.login(self.username, self.password)
            self.connection = connection
            return True
        except Exception:
            if not self.fail_silently:
                raise

    def close(self):
        try:
            if self.connection:
                self.connection.quit()
        except Exception:
            pass
        finally:
            self.connection = None
