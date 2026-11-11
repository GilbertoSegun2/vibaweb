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

def liberar_reservas_vencidas(viaje=None, usuario=None):
    """
    Libera asientos reservados cuyo tiempo ha expirado.
    
    - Si se pasa 'usuario': respeta al usuario actual (NO libera sus asientos).
      Libera los huérfanos y los de OTROS usuarios.
    - Si NO se pasa 'usuario': libera todos los vencidos (comportamiento global).
    """
    from django.utils import timezone
    from .models import Asiento
    
    ahora = timezone.now()
    total_liberados = 0
    
    # CASO 1: Asientos huérfanos (sin dueño) que ya expiraron
    qs_huerfanos = Asiento.objects.filter(
        estado='reservado',
        reservado_hasta__lt=ahora,
        reservado_por__isnull=True
    )
    if viaje is not None:
        qs_huerfanos = qs_huerfanos.filter(viaje=viaje)
    total_liberados += qs_huerfanos.update(estado='disponible', reservado_hasta=None, reservado_por=None)
    
    # CASO 2: Asientos de OTROS usuarios que expiraron (respetando al actual)
    qs_vencidos = Asiento.objects.filter(
        estado='reservado',
        reservado_hasta__lt=ahora,
        reservado_por__isnull=False
    )
    if viaje is not None:
        qs_vencidos = qs_vencidos.filter(viaje=viaje)
    if usuario is not None:
        # ⭐ CLAVE: Excluir al usuario actual para no interrumpirlo
        qs_vencidos = qs_vencidos.exclude(reservado_por=usuario)
    total_liberados += qs_vencidos.update(estado='disponible', reservado_hasta=None, reservado_por=None)
    
    # CASO 3: Pendientes de verificación
    qs_pendientes = Asiento.objects.filter(
        estado='pendiente_verificacion',
        reservado_hasta__lt=ahora
    )
    if viaje is not None:
        qs_pendientes = qs_pendientes.filter(viaje=viaje)
    total_liberados += qs_pendientes.update(estado='disponible', reservado_hasta=None, reservado_por=None)
    
    return total_liberados
    
def obtener_tasa_bcv():
    """
    Devuelve la tasa BCV del día (parámetro 107).
    Si no existe, es 0 o no es numérica, devuelve None.
    Acepta valores numéricos o de texto (con coma o punto decimal).
    """
    from .models import Parametro
    try:
        p = Parametro.objects.get(codigo='107', activo=True)
        
        # 1. Intentar con valor_numerico
        if p.valor_numerico is not None and p.valor_numerico > 0:
            return p.valor_numerico
        
        # 2. Si no, intentar con valor_texto (por si se guardó como texto)
        if p.valor_texto:
            try:
                # Limpiar comas y puntos (formato venezolano: 879,12 -> 879.12)
                texto_limpio = p.valor_texto.replace('.', '').replace(',', '.')
                valor = float(texto_limpio)
                if valor > 0:
                    return valor
            except (ValueError, TypeError):
                pass
                
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
    
def asiento_esta_disponible_en_tramo(asiento_id, viaje_id, nuevo_orden_origen, nuevo_orden_destino):
    """
    Verifica si un asiento está disponible para un tramo específico.
    Aplica la regla de choque de tramos.
    """
    from .models import Boleto
    
    # Buscamos si hay algún boleto vendido en este asiento para este viaje
    # que choque con el tramo que queremos vender.
    choque = Boleto.objects.filter(
        viaje_id=viaje_id,
        asiento_id=asiento_id,
        estado__in=['vendido', 'pendiente_verificacion'],
        orden_origen__lt=nuevo_orden_destino,   # El viejo se sube antes de que el nuevo se baje
        orden_destino__gt=nuevo_orden_origen    # El viejo se baja después de que el nuevo se sube
    ).exists()
    
    return not choque # Si hay choque, devuelve False (Ocupado). Si no, True (Libre).
    
def verificar_y_actualizar_bcv_automatico():
    """
    Verifica si la tasa del BCV del día actual en Venezuela ya fue actualizada.
    Si es un nuevo día, ejecuta el comando de actualización automáticamente.
    """
    from django.core.management import call_command
    from django.utils import timezone
    from .models import Parametro
    
    try:
        ahora_ve = timezone.localtime(timezone.now())
        hoy_str = ahora_ve.strftime('%Y-%m-%d')
        
        # Leer la fecha de la última actualización guardada en el parámetro '108'
        param_fecha = Parametro.objects.filter(codigo='108').first()
        ultima_fecha = param_fecha.valor_texto if param_fecha else None
        
        # Si no hay fecha registrada o la última fecha es de un día anterior, actualizamos
        if not ultima_fecha or not ultima_fecha.startswith(hoy_str):
            call_command('actualizar_bcv')
    except Exception as e:
        # Capturamos cualquier error de red o del BCV para que la web siga funcionando sin bloquearse
        print(f"Aviso: No se pudo actualizar la tasa BCV automáticamente: {e}")
        
def generar_numero_boleto(oficina, es_continuo=False):
    """
    Genera el número de boleto con formato CÓDIGO OFICINA-SECUENCIA.
    Si es_continuo=True, la secuencia es única para toda la empresa.
    Si es_continuo=False, cada oficina tiene su propio contador.
    """
    from .models import Boleto, Oficina
    
    # Obtener el código de la oficina (ej. "001")
    codigo_oficina = oficina.codigo if oficina else "WEB"
    
    if es_continuo:
        # Buscar el último boleto de CUALQUIER oficina (secuencia continua)
        ultimo = Boleto.objects.filter(numero_boleto__isnull=False).order_by('-id').first()
        if ultimo and ultimo.numero_boleto:
            try:
                # Extraer la secuencia (después del guión)
                secuencia = int(ultimo.numero_boleto.split('-')[1]) + 1
            except (ValueError, IndexError):
                secuencia = 1
        else:
            secuencia = 1
    else:
        # Buscar el último boleto de ESA oficina específica
        ultimo = Boleto.objects.filter(
            numero_boleto__startswith=f"{codigo_oficina}-"
        ).order_by('-id').first()
        if ultimo and ultimo.numero_boleto:
            try:
                secuencia = int(ultimo.numero_boleto.split('-')[1]) + 1
            except (ValueError, IndexError):
                secuencia = 1
        else:
            secuencia = 1
    
    # Formatear con 6 dígitos
    return f"{codigo_oficina}-{secuencia:06d}"
    
