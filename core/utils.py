"""Utilidades del sistema Viba-Web"""
from .models import Asiento, PlantillaAsiento


def generar_asientos_para_viaje(viaje):
    """
    Genera los asientos de un viaje basándose en la plantilla del bus.
    Incluye asientos, escaleras, baños y posiciones vacías.
    
    Retorna la cantidad de asientos reales creados.
    """
    bus = viaje.bus
    
    if not bus.plantilla:
        raise ValueError(
            f"El bus {bus.placa} no tiene una plantilla asignada. "
            f"Asígnala en el admin antes de crear viajes."
        )
    
    posiciones = PlantillaAsiento.objects.filter(
        plantilla=bus.plantilla,
    ).order_by('piso', 'fila', 'columna')
    
    if not posiciones.exists():
        raise ValueError(
            f"La plantilla {bus.plantilla.nombre} no tiene posiciones definidas."
        )
    
    asientos_creados = []
    total_asientos_reales = 0
    
    for pos in posiciones:
        asiento = Asiento(
            viaje=viaje,
            numero=pos.numero if pos.tipo == 'asiento' else '',
            fila=pos.fila,
            columna=pos.columna,
            piso=pos.piso,
            lado=pos.lado,
            tipo=pos.tipo,
            estado='disponible' if pos.tipo == 'asiento' else 'bloqueado'
        )
        asientos_creados.append(asiento)
        
        if pos.tipo == 'asiento':
            total_asientos_reales += 1
    
    Asiento.objects.bulk_create(asientos_creados)
    return total_asientos_reales
    
def obtener_parametro(codigo, default=None):
    """
    Lee un parámetro del sistema por su código.
    Devuelve el valor según su tipo (numero, texto, booleano).
    Si no existe o está inactivo, devuelve el default.
    """
    from .models import Parametro
    try:
        p = Parametro.objects.get(codigo=str(codigo), activo=True)
        if p.tipo == 'numero':
            return p.valor_numerico if p.valor_numerico is not None else default
        elif p.tipo == 'texto':
            return p.valor_texto if p.valor_texto else default
        elif p.tipo == 'booleano':
            return p.valor_booleano if p.valor_booleano is not None else default
    except Parametro.DoesNotExist:
        return default
    return default


def liberar_reservas_vencidas(viaje=None):
    """
    Libera los asientos cuya reserva temporal ha vencido.
    Si se pasa un viaje, solo limpia ese viaje.
    Devuelve la cantidad de asientos liberados.
    """
    from django.utils import timezone
    from .models import Asiento

    ahora = timezone.now()
    qs = Asiento.objects.filter(
        estado='reservado',
        reservado_hasta__lt=ahora
    )
    if viaje is not None:
        qs = qs.filter(viaje=viaje)

    cantidad = qs.update(
        estado='disponible',
        reservado_hasta=None,
        reservado_por=None
    )
    return cantidad
    
def obtener_tasa_bcv():
    """
    Devuelve la tasa BCV del día (parámetro 107).
    Si no existe o es 0, devuelve None.
    """
    from .models import Parametro
    try:
        p = Parametro.objects.get(codigo='107', activo=True)
        if p.valor_numerico and p.valor_numerico > 0:
            return p.valor_numerico
    except Parametro.DoesNotExist:
        pass
    return None


def convertir_a_bs(monto_usd, tasa=None):
    """
    Convierte un monto en USD a Bs. según la tasa BCV.
    
    - Si no se pasa tasa, la lee del parámetro 107.
    - Redondea a 2 decimales (ROUND).
    - Devuelve None si no hay tasa configurada.
    """
    from decimal import Decimal, ROUND_HALF_UP
    if tasa is None:
        tasa = obtener_tasa_bcv()
    if tasa is None:
        return None
    monto_usd = Decimal(str(monto_usd))
    tasa = Decimal(str(tasa))
    monto_bs = monto_usd * tasa
    # Redondear a 2 decimales (ROUND_HALF_UP = redondeo tradicional)
    return monto_bs.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def formatear_precio(monto_usd):
    """
    Devuelve un diccionario con:
    - 'usd': monto en USD formateado
    - 'bs': monto en Bs. formateado (o None si no hay tasa)
    - 'tasa': la tasa aplicada (o None)
    
    Útil para usar en templates:
        {% with precios=viaje.precio_usd|formatear_precio %}
            USD {{ precios.usd }} / Bs. {{ precios.bs }}
        {% endwith %}
    """
    from decimal import Decimal
    monto_bs = convertir_a_bs(monto_usd)
    return {
        'usd': f"{Decimal(str(monto_usd)):,.2f}",
        'bs': f"{monto_bs:,.2f}" if monto_bs is not None else None,
        'tasa': obtener_tasa_bcv(),
    }
    
def generar_codigo_transaccion():
    """Genera un código único para la transacción (T-YYYYMMDD-XXXX)"""
    from django.utils import timezone
    from .models import Transaccion
    hoy = timezone.now().strftime('%Y%m%d')
    prefijo = f"T-{hoy}-"
    
    # Buscar el último código del día
    ultimo = Transaccion.objects.filter(codigo__startswith=prefijo).order_by('-codigo').first()
    
    if ultimo:
        try:
            numero = int(ultimo.codigo.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = 1
    else:
        numero = 1
    
    return f"{prefijo}{numero:04d}"


def generar_codigo_qr():
    """Genera un código QR único para el boleto"""
    import uuid
    return uuid.uuid4().hex[:16].upper()
    
