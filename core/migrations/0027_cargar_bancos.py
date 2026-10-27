from django.db import migrations

def cargar_bancos(apps, schema_editor):
    Banco = apps.get_model('core', 'Banco')
    bancos = [
        ('0001', 'Banco Central de Venezuela'),
        ('0102', 'Banco de Venezuela (BDV)'),
        ('0104', 'Banco Venezolano de Crédito (BVC)'),
        ('0105', 'Banco Mercantil'),
        ('0108', 'Banco Provincial (BBVA)'),
        ('0114', 'Bancaribe'),
        ('0115', 'Banco Exterior'),
        ('0128', 'Banco Caroní'),
        ('0134', 'Banesco Banco Universal'),
        ('0137', 'Banco Sofitasa'),
        ('0138', 'Banco Plaza'),
        ('0146', 'Bangente'),
        ('0151', 'Banco Fondo Común (BFC)'),
        ('0156', '100% Banco'),
        ('0157', 'Del Sur Banco Universal'),
        ('0163', 'Banco del Tesoro'),
        ('0166', 'Banco Agrícola de Venezuela'),
        ('0168', 'Bancrecer'),
        ('0169', 'Mi Banco'),
        ('0171', 'Banco Activo'),
        ('0172', 'Bancamiga'),
        ('0174', 'Banplus'),
        ('0175', 'Banco Bicentenario del Pueblo'),
        ('0177', 'Banco de la Fuerza Armada Nacional Bolivariana (BANFANB)'),
        ('0191', 'Banco Nacional de Crédito (BNC)'),
    ]
    for codigo, nombre in bancos:
        Banco.objects.get_or_create(codigo=codigo, defaults={'nombre': nombre})

def borrar_bancos(apps, schema_editor):
    Banco = apps.get_model('core', 'Banco')
    Banco.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0026_banco'),  # ⭐ Depende de la migración anterior (Banco creado)
    ]

    operations = [
        migrations.RunPython(cargar_bancos, borrar_bancos),
    ]
