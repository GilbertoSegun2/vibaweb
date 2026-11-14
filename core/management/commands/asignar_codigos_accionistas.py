from django.core.management.base import BaseCommand
from core.models import Empresa

class Command(BaseCommand):
    help = 'Asigna códigos automáticos a los accionistas sin código'

    def handle(self, *args, **kwargs):
        empresas = Empresa.objects.all().order_by('id')
        contador = 1
        
        for empresa in empresas:
            if not empresa.codigo:
                codigo = f"{contador:03d}"
                while Empresa.objects.filter(codigo=codigo).exclude(id=empresa.id).exists():
                    contador += 1
                    codigo = f"{contador:03d}"
                
                empresa.codigo = codigo
                empresa.save()
                self.stdout.write(f"✅ {empresa.nombre} → {codigo}")
                contador += 1
            else:
                self.stdout.write(f"⏭️  {empresa.nombre} ya tiene código: {empresa.codigo}")
        
        self.stdout.write(self.style.SUCCESS(f"\n✅ Proceso completado."))
