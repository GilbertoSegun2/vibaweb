from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from core.models import Suscripcion

class Command(BaseCommand):
    help = 'Revisa suscripciones por vencer y envía alertas'

    def handle(self, *args, **kwargs):
        hoy = timezone.now().date()
        
        # 1. Empresas que vencen en 5 días
        alerta = Suscripcion.objects.filter(
            fecha_vencimiento=hoy + timedelta(days=5),
            activa=True
        )
        
        # 2. Empresas vencidas hoy
        vencidas_hoy = Suscripcion.objects.filter(
            fecha_vencimiento=hoy,
            activa=True
        )

        if alerta or vencidas_hoy:
            mensaje = "🔔 REPORTE DE SUSCRIPCIONES VIBA-WEB\n\n"
            if alerta:
                mensaje += "⚠️ PRÓXIMAS A VENCER (en 5 días):\n"
                for sub in alerta:
                    mensaje += f" - {sub.empresa.nombre} (Vence: {sub.fecha_vencimiento})\n"
            if vencidas_hoy:
                mensaje += "\n🔴 VENCEN HOY:\n"
                for sub in vencidas_hoy:
                    mensaje += f" - {sub.empresa.nombre}\n"

            # Enviar correo al administrador maestro
            send_mail(
                'Alerta de Suscripciones Viba-Web',
                mensaje,
                'sistema@boletoexpreso.com',
                ['semuyvaliente@gmail.com'], # Tu correo maestro
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('Alertas enviadas correctamente.'))
        else:
            self.stdout.write(self.style.SUCCESS('No hay suscripciones por vencer hoy.'))
