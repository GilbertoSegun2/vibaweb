"""Comando para cargar las plantillas de buses iniciales"""
from django.core.management.base import BaseCommand
from core.models import PlantillaBus, PlantillaAsiento


# ============================================================
# PLANTILLA: YUTONG (52 puestos, 1 piso, 15 filas)
# ============================================================
YUTONG_52 = {
    'nombre': 'Yutong 52 puestos',
    'tipo': 'yutong',
    'capacidad': 52,
    'pisos': 1,
    'posiciones': []
}

YUTONG_MAPA = [
    # Fila 1
    ('01', 1, 1, 'ventana'), ('02', 1, 2, 'pasillo'),
    ('04', 1, 3, 'pasillo'), ('03', 1, 4, 'ventana'),
    # Fila 2 - Escaleras en columnas 3 y 4
    ('05', 2, 1, 'ventana'), ('06', 2, 2, 'pasillo'),
    # Fila 3
    ('09', 3, 1, 'ventana'), ('10', 3, 2, 'pasillo'),
    ('08', 3, 3, 'pasillo'), ('07', 3, 4, 'ventana'),
    # Fila 4
    ('13', 4, 1, 'ventana'), ('14', 4, 2, 'pasillo'),
    ('12', 4, 3, 'pasillo'), ('11', 4, 4, 'ventana'),
    # Fila 5
    ('17', 5, 1, 'ventana'), ('18', 5, 2, 'pasillo'),
    ('16', 5, 3, 'pasillo'), ('15', 5, 4, 'ventana'),
    # Fila 6
    ('21', 6, 1, 'ventana'), ('22', 6, 2, 'pasillo'),
    ('20', 6, 3, 'pasillo'), ('19', 6, 4, 'ventana'),
    # Fila 7
    ('25', 7, 1, 'ventana'), ('26', 7, 2, 'pasillo'),
    ('24', 7, 3, 'pasillo'), ('23', 7, 4, 'ventana'),
    # Fila 8 - Escaleras en columnas 3 y 4
    ('27', 8, 1, 'ventana'), ('28', 8, 2, 'pasillo'),
    # Fila 9
    ('31', 9, 1, 'ventana'), ('32', 9, 2, 'pasillo'),
    ('30', 9, 3, 'pasillo'), ('29', 9, 4, 'ventana'),
    # Fila 10
    ('35', 10, 1, 'ventana'), ('36', 10, 2, 'pasillo'),
    ('34', 10, 3, 'pasillo'), ('33', 10, 4, 'ventana'),
    # Fila 11
    ('39', 11, 1, 'ventana'), ('40', 11, 2, 'pasillo'),
    ('38', 11, 3, 'pasillo'), ('37', 11, 4, 'ventana'),
    # Fila 12
    ('43', 12, 1, 'ventana'), ('44', 12, 2, 'pasillo'),
    ('42', 12, 3, 'pasillo'), ('41', 12, 4, 'ventana'),
    # Fila 13
    ('47', 13, 1, 'ventana'), ('48', 13, 2, 'pasillo'),
    ('46', 13, 3, 'pasillo'), ('45', 13, 4, 'ventana'),
    # Fila 14 - Baño en columnas 3 y 4
    ('49', 14, 1, 'ventana'), ('50', 14, 2, 'pasillo'),
    # Fila 15 - Baño en columnas 3 y 4
    ('51', 15, 1, 'ventana'), ('52', 15, 2, 'pasillo'),
]

for (numero, fila, columna, lado) in YUTONG_MAPA:
    YUTONG_52['posiciones'].append({
        'numero': numero, 'fila': fila, 'columna': columna,
        'piso': 1, 'lado': lado, 'tipo': 'asiento',
    })

for fila in [2, 8]:
    for col in [3, 4]:
        YUTONG_52['posiciones'].append({
            'numero': '', 'fila': fila, 'columna': col,
            'piso': 1, 'lado': '', 'tipo': 'escalera',
        })

for fila in [14, 15]:
    for col in [3, 4]:
        YUTONG_52['posiciones'].append({
            'numero': '', 'fila': fila, 'columna': col,
            'piso': 1, 'lado': '', 'tipo': 'baño',
        })


# ============================================================
# PLANTILLA: BUSCAMA (60 puestos, 2 pisos)
# ============================================================
BUSCAMA_60 = {
    'nombre': 'BUSCAMA 60 puestos',
    'tipo': 'doble_piso',
    'capacidad': 60,
    'pisos': 2,
    'posiciones': []
}

# --- PISO 1 (INFERIOR): asientos 45-60 ---
BUSCAMA_PISO1 = [
    ('45', 1, 1, 'ventana'), ('46', 1, 2, 'pasillo'),
    ('48', 1, 3, 'pasillo'), ('47', 1, 4, 'ventana'),
    ('49', 2, 1, 'ventana'), ('50', 2, 2, 'pasillo'),
    ('52', 2, 3, 'pasillo'), ('51', 2, 4, 'ventana'),
    ('53', 3, 1, 'ventana'), ('54', 3, 2, 'pasillo'),
    ('56', 3, 3, 'pasillo'), ('55', 3, 4, 'ventana'),
    ('57', 4, 1, 'ventana'), ('58', 4, 2, 'pasillo'),
    ('60', 4, 3, 'pasillo'), ('59', 4, 4, 'ventana'),
]

for (numero, fila, columna, lado) in BUSCAMA_PISO1:
    BUSCAMA_60['posiciones'].append({
        'numero': numero, 'fila': fila, 'columna': columna,
        'piso': 1, 'lado': lado, 'tipo': 'asiento',
    })

# --- PISO 2 (SUPERIOR): asientos 01-44 ---
# Fila 1 completa
BUSCAMA_60['posiciones'].append({'numero': '01', 'fila': 1, 'columna': 1, 'piso': 2, 'lado': 'ventana', 'tipo': 'asiento'})
BUSCAMA_60['posiciones'].append({'numero': '02', 'fila': 1, 'columna': 2, 'piso': 2, 'lado': 'pasillo', 'tipo': 'asiento'})
BUSCAMA_60['posiciones'].append({'numero': '04', 'fila': 1, 'columna': 3, 'piso': 2, 'lado': 'pasillo', 'tipo': 'asiento'})
BUSCAMA_60['posiciones'].append({'numero': '03', 'fila': 1, 'columna': 4, 'piso': 2, 'lado': 'ventana', 'tipo': 'asiento'})

# Filas 2-3: solo columnas 1 y 2 (escaleras en 3 y 4)
BUSCAMA_60['posiciones'].append({'numero': '05', 'fila': 2, 'columna': 1, 'piso': 2, 'lado': 'ventana', 'tipo': 'asiento'})
BUSCAMA_60['posiciones'].append({'numero': '06', 'fila': 2, 'columna': 2, 'piso': 2, 'lado': 'pasillo', 'tipo': 'asiento'})
BUSCAMA_60['posiciones'].append({'numero': '09', 'fila': 3, 'columna': 1, 'piso': 2, 'lado': 'ventana', 'tipo': 'asiento'})
BUSCAMA_60['posiciones'].append({'numero': '10', 'fila': 3, 'columna': 2, 'piso': 2, 'lado': 'pasillo', 'tipo': 'asiento'})

for fila in [2, 3]:
    for col in [3, 4]:
        BUSCAMA_60['posiciones'].append({
            'numero': '', 'fila': fila, 'columna': col,
            'piso': 2, 'lado': '', 'tipo': 'escalera',
        })

# Filas 4-12: completas (columnas 1, 2, 3, 4)
col1 = ['13', '17', '21', '25', '29', '33', '37', '41', '43']
col2 = ['14', '18', '22', '26', '30', '34', '38', '42', '44']
col3 = ['08', '12', '16', '20', '24', '28', '32', '36', '40']
col4 = ['07', '11', '15', '19', '23', '27', '31', '35', '39']

for i in range(9):
    fila = 4 + i
    BUSCAMA_60['posiciones'].append({'numero': col1[i], 'fila': fila, 'columna': 1, 'piso': 2, 'lado': 'ventana', 'tipo': 'asiento'})
    BUSCAMA_60['posiciones'].append({'numero': col2[i], 'fila': fila, 'columna': 2, 'piso': 2, 'lado': 'pasillo', 'tipo': 'asiento'})
    BUSCAMA_60['posiciones'].append({'numero': col3[i], 'fila': fila, 'columna': 3, 'piso': 2, 'lado': 'pasillo', 'tipo': 'asiento'})
    BUSCAMA_60['posiciones'].append({'numero': col4[i], 'fila': fila, 'columna': 4, 'piso': 2, 'lado': 'ventana', 'tipo': 'asiento'})


# ============================================================
# PLANTILLA: POLTRONA (40 puestos, 2 pisos)
# ============================================================
POLTRONA_40 = {
    'nombre': 'Poltrona 40 puestos',
    'tipo': 'poltrona',
    'capacidad': 40,
    'pisos': 2,
    'posiciones': []
}

# --- PISO 1 (asientos 01-31) ---
POLTRONA_PISO1 = [
    ('01', 1, 1, 'ventana'), ('02', 1, 2, 'pasillo'), ('03', 1, 4, 'ventana'),
    ('04', 2, 1, 'ventana'), ('05', 2, 2, 'pasillo'),
    ('06', 3, 1, 'ventana'), ('07', 3, 2, 'pasillo'),
    ('08', 4, 1, 'ventana'), ('09', 4, 2, 'pasillo'), ('10', 4, 4, 'ventana'),
    ('11', 5, 1, 'ventana'), ('12', 5, 2, 'pasillo'), ('13', 5, 4, 'ventana'),
    ('14', 6, 1, 'ventana'), ('15', 6, 2, 'pasillo'), ('16', 6, 4, 'ventana'),
    ('17', 7, 1, 'ventana'), ('18', 7, 2, 'pasillo'), ('19', 7, 4, 'ventana'),
    ('20', 8, 1, 'ventana'), ('21', 8, 2, 'pasillo'), ('22', 8, 4, 'ventana'),
    ('23', 9, 1, 'ventana'), ('24', 9, 2, 'pasillo'), ('25', 9, 4, 'ventana'),
    ('26', 10, 1, 'ventana'), ('27', 10, 2, 'pasillo'), ('28', 10, 4, 'ventana'),
    ('29', 11, 1, 'ventana'), ('30', 11, 2, 'pasillo'), ('31', 11, 4, 'ventana'),
]

for (numero, fila, columna, lado) in POLTRONA_PISO1:
    POLTRONA_40['posiciones'].append({
        'numero': numero, 'fila': fila, 'columna': columna,
        'piso': 1, 'lado': lado, 'tipo': 'asiento',
    })

for fila in [2, 3]:
    for col in [3, 4]:
        POLTRONA_40['posiciones'].append({
            'numero': '', 'fila': fila, 'columna': col,
            'piso': 1, 'lado': '', 'tipo': 'escalera',
        })

# --- PISO 2 (asientos 32-40) ---
POLTRONA_PISO2 = [
    ('33', 1, 1, 'ventana'), ('32', 1, 2, 'pasillo'), ('34', 1, 4, 'ventana'),
    ('35', 2, 1, 'ventana'), ('36', 2, 2, 'pasillo'), ('37', 2, 4, 'ventana'),
    ('38', 3, 1, 'ventana'), ('39', 3, 2, 'pasillo'), ('40', 3, 4, 'ventana'),
]

for (numero, fila, columna, lado) in POLTRONA_PISO2:
    POLTRONA_40['posiciones'].append({
        'numero': numero, 'fila': fila, 'columna': columna,
        'piso': 2, 'lado': lado, 'tipo': 'asiento',
    })


# ============================================================
# COMANDO
# ============================================================
class Command(BaseCommand):
    help = 'Carga las plantillas de buses iniciales'

    def handle(self, *args, **options):
        plantillas = [YUTONG_52, BUSCAMA_60, POLTRONA_40]

        # Borrar plantillas existentes para evitar duplicados
        PlantillaBus.objects.all().delete()
        self.stdout.write(self.style.WARNING('Plantillas anteriores borradas.'))

        for data in plantillas:
            plantilla = PlantillaBus.objects.create(
                nombre=data['nombre'],
                tipo=data['tipo'],
                capacidad=data['capacidad'],
                pisos=data['pisos'],
            )

            self.stdout.write(f"Creando plantilla: {plantilla.nombre}")

            for pos in data['posiciones']:
                PlantillaAsiento.objects.create(
                    plantilla=plantilla,
                    numero=pos['numero'],
                    fila=pos['fila'],
                    columna=pos['columna'],
                    piso=pos['piso'],
                    lado=pos['lado'],
                    tipo=pos['tipo'],
                )

            self.stdout.write(self.style.SUCCESS(
                f"  ✓ {len(data['posiciones'])} posiciones creadas"
            ))

        self.stdout.write(self.style.SUCCESS('\n¡Plantillas cargadas!'))
