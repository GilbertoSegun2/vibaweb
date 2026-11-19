"""
Comando para actualizar la tasa BCV del día.
...
"""
import re

# Silenciar el warning de certificado SSL del BCV
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
                self.stdout.write(self.style.SUCCESS(f'OK Tasa actualizada manualmente: {tasa} Bs/USD'))
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
            self.stdout.write(self.style.SUCCESS(f'OK Tasa actualizada: {tasa} Bs/USD'))
            
        except requests.exceptions.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error de conexión: {e}'))
            self.stdout.write('Se mantiene la última tasa conocida.')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error inesperado: {e}'))

    def guardar_tasa(self, tasa):
        """
        Guarda la tasa obtenida del BCV:
        - Si se actualiza antes de las 4 PM, se aplica como tasa vigente de hoy.
        - Si se actualiza a las 4 PM o más tarde, se guarda como 'tasa programada' 
          para el día siguiente, respetando que el día en curso siga usando su tasa hasta las 12:00 AM.
        """
        from datetime import timedelta
        ahora_ve = timezone.localtime(timezone.now())
        hoy = ahora_ve.date()
        
        # A partir de las 4 PM (16:00), la tasa del BCV publicada es para el día siguiente
        if ahora_ve.hour >= 16:
            fecha_vigencia = hoy + timedelta(days=1)
        else:
            fecha_vigencia = hoy
            
        fecha_vigencia_str = fecha_vigencia.strftime('%Y-%m-%d')
        
        if fecha_vigencia > hoy:
            # Guardar como tasa programada (Parámetro 109 y 110) para que entre en vigor a las 00:00
            param_prog, _ = Parametro.objects.get_or_create(
                codigo='109',
                defaults={
                    'descripcion': 'Tasa BCV programada para el día siguiente',
                    'tipo': 'numero',
                    'activo': True,
                }
            )
            param_prog.valor_numerico = tasa
            param_prog.save()
            
            param_prog_f, _ = Parametro.objects.get_or_create(
                codigo='110',
                defaults={
                    'descripcion': 'Fecha de vigencia de la tasa programada',
                    'tipo': 'texto',
                    'activo': True,
                }
            )
            param_prog_f.valor_texto = fecha_vigencia_str
            param_prog_f.save()
            
            self.stdout.write(self.style.SUCCESS(
                f'OK Tasa para {fecha_vigencia_str} guardada como programada: {tasa} Bs/USD (se activará a las 00:00)'
            ))
        else:
            # Si es para hoy mismo, actualizar directamente la tasa vigente (Parámetro 107 y 108)
            parametro, _ = Parametro.objects.get_or_create(
                codigo='107',
                defaults={
                    'descripcion': 'Tasa BCV del día (Bs. por USD)',
                    'tipo': 'numero',
                    'activo': True,
                }
            )
            parametro.valor_numerico = tasa
            parametro.save()
            
            param_fecha, _ = Parametro.objects.get_or_create(
                codigo='108',
                defaults={
                    'descripcion': 'Fecha a la que corresponde la tasa BCV',
                    'tipo': 'texto',
                    'activo': True,
                }
            )
            param_fecha.valor_texto = fecha_vigencia_str
            param_fecha.save()
            
            self.stdout.write(self.style.SUCCESS(
                f'OK Tasa vigente para hoy ({fecha_vigencia_str}) actualizada: {tasa} Bs/USD'
            ))
