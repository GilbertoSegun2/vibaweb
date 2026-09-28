"""
Comando para actualizar la tasa BCV del día.

Uso:
    python manage.py actualizar_bcv
    python manage.py actualizar_bcv --manual 36.50
"""
import re
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Parametro


class Command(BaseCommand):
    help = 'Actualiza la tasa BCV del día desde la página oficial'

    def add_arguments(self, parser):
        parser.add_argument(
            '--manual',
            type=str,
            help='Establece la tasa manualmente (ej: 36.50)',
        )

    def handle(self, *args, **options):
        # Si se pasó --manual, usar ese valor
        if options['manual']:
            try:
                tasa = float(options['manual'].replace(',', '.'))
                self.guardar_tasa(tasa)
                self.stdout.write(self.style.SUCCESS(f'✓ Tasa actualizada manualmente: {tasa} Bs/USD'))
                return
            except ValueError:
                self.stdout.write(self.style.ERROR('Valor manual inválido.'))
                return

        # Si no, obtener desde el BCV
        try:
            self.stdout.write('Consultando tasa del BCV...')
            
            url = "https://www.bcv.org.ve/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, verify=False, timeout=15)
            
            if response.status_code != 200:
                self.stdout.write(self.style.ERROR(f'Error HTTP: {response.status_code}'))
                return
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscar el div con id="dolar" y su <strong>
            valor_elemento = soup.select_one('div#dolar strong')
            
            if not valor_elemento:
                self.stdout.write(self.style.ERROR('No se encontró el elemento con la tasa.'))
                self.stdout.write('Puede ser que el BCV haya cambiado su página. Verifica manualmente.')
                return
            
            valor_texto = valor_elemento.text.strip()
            # BCV usa coma como separador decimal: "36,5432"
            valor_limpio = valor_texto.replace(',', '.')
            
            # Validar que sea un número
            if not re.match(r'^\d+\.?\d*$', valor_limpio):
                self.stdout.write(self.style.ERROR(f'Valor no válido: {valor_texto}'))
                return
            
            tasa = float(valor_limpio)
            
            self.guardar_tasa(tasa)
            self.stdout.write(self.style.SUCCESS(f'✓ Tasa actualizada: {tasa} Bs/USD'))
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error de conexión: {e}'))
            self.stdout.write('Se mantiene la última tasa conocida.')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error inesperado: {e}'))

    def guardar_tasa(self, tasa):
        """Guarda la tasa en el parámetro 107 y la fecha en el 108"""
        # Actualizar parámetro 107 (tasa)
        parametro, created = Parametro.objects.get_or_create(
            codigo='107',
            defaults={
                'descripcion': 'Tasa BCV del día (Bs. por USD)',
                'tipo': 'numero',
                'activo': True,
            }
        )
        parametro.valor_numerico = tasa
        parametro.save()
        
        # Actualizar parámetro 108 (fecha de actualización)
        param_fecha, created = Parametro.objects.get_or_create(
            codigo='108',
            defaults={
                'descripcion': 'Fecha de última actualización de la tasa BCV',
                'tipo': 'texto',
                'activo': True,
            }
        )
        param_fecha.valor_texto = timezone.now().strftime('%Y-%m-%d %H:%M')
        param_fecha.save()
