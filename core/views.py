from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages

from .models import Oficina, Viaje, Asiento, Transaccion, Pago, Boleto, Tarifa, MovimientoAsiento
from .forms import RegistroForm, LoginForm, PagoWebForm, PasajeroForm, PasarelaVirtualForm

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .utils import obtener_parametro, liberar_reservas_vencidas, generar_codigo_transaccion, generar_codigo_qr


# ============================================================
# FUNCIÓN AUXILIAR DE SEGURIDAD
# ============================================================

def validar_tarifa_para_viaje(viaje, origen_id, destino_id):
    """
    Valida que los IDs de origen/destino sean coherentes con la ruta del viaje.
    Retorna (tarifa, es_valido).
    
    - tarifa: objeto Tarifa o None si no se encuentra
    - es_valido: True si los IDs son válidos para este viaje, False si son manipulados
    """
    if not (origen_id and destino_id):
        return (None, True)  # Sin IDs no hay nada que validar
    
    try:
        origen_id_int = int(origen_id)
        destino_id_int = int(destino_id)
    except (ValueError, TypeError):
        return (None, False)  # IDs no numéricos = manipulados
    
    # El origen debe coincidir con la ruta del viaje
    origen_valido = (viaje.ruta.origen_id == origen_id_int)
    
    # El destino debe estar entre los destinos de la ruta
    destino_valido = viaje.ruta.destinos.filter(id=destino_id_int).exists()
    
    if not (origen_valido and destino_valido):
        return (None, False)  # IDs no coherentes con el viaje
    
    # Buscar la tarifa
    tarifa = Tarifa.objects.filter(
        origen_id=origen_id_int,
        destino_id=destino_id_int,
        activa=True
    ).first()
    
    return (tarifa, True)


# ============================================================
# VISTAS PÚBLICAS
# ============================================================

def inicio(request):
    """Página de inicio con buscador de viajes"""
    # Resetear el tiempo de reserva al volver al inicio
    request.session.pop('reserva_inicio', None)
    
    # Liberar los asientos que el cliente tenía reservados (por si acaso)
    cliente = None
    if request.user.is_authenticated:
        cliente = getattr(request.user, 'cliente', None)
    
    if cliente:
        with transaction.atomic():
            asientos_reservados = Asiento.objects.select_for_update().filter(
                estado='reservado',
                reservado_por=cliente
            )
            
            # Registrar auditoría por cada asiento liberado
            for asiento in asientos_reservados:
                MovimientoAsiento.objects.create(
                    asiento=asiento,
                    tipo='liberacion_manual',
                    estado_anterior='reservado',
                    estado_nuevo='disponible',
                    usuario=request.user,
                    motivo='El cliente volvió al inicio',
                )
            
            # Liberar los asientos
            asientos_reservados.update(
                estado='disponible',
                reservado_hasta=None,
                reservado_por=None
            )
    
    oficinas = Oficina.objects.filter(activa=True).order_by('nombre')
    return render(request, 'inicio.html', {
        'oficinas': oficinas,
    })


def buscar_viajes(request):
    """Busca viajes según origen, destino y fecha"""
    origen_id = request.GET.get('origen')
    destino_id = request.GET.get('destino')
    fecha_str = request.GET.get('fecha')
    
    # Si no hay filtros, no mostrar nada
    if not (origen_id and destino_id and fecha_str):
        return render(request, 'buscar_viajes.html', {
            'viajes_con_info': [],
            'oficina_origen': None,
            'oficina_destino': None,
            'fecha': None,
            'tarifa': None,
            'oficinas': Oficina.objects.filter(activa=True).order_by('nombre'),
        })
    
    viajes = Viaje.objects.filter(
        estado='programado',
        cerrado_venta=False,
        ruta__activa=True,
    )
    # Liberar reservas vencidas antes de buscar
    for viaje in viajes:
        liberar_reservas_vencidas(viaje=viaje)
        
    oficina_origen = Oficina.objects.filter(id=origen_id).first()
    oficina_destino = Oficina.objects.filter(id=destino_id).first()
    fecha = None
    tarifa = None
    
    if oficina_origen:
        viajes = viajes.filter(ruta__origen=oficina_origen)
    
    if oficina_destino:
        # Buscar viajes cuya RUTA incluya este destino
        viajes = viajes.filter(ruta__destinos=oficina_destino)
    
    # Procesar la fecha (solo fechas de hoy o futuras)
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hoy = timezone.now().date()
        if fecha >= hoy:
            viajes = viajes.filter(fecha=fecha)
        else:
            # Si la fecha es pasada, no mostrar nada
            viajes = viajes.none()
    except ValueError:
        viajes = viajes.none()
    
    # Buscar la tarifa según origen + destino
    if oficina_origen and oficina_destino:
        tarifa = Tarifa.objects.filter(
            origen=oficina_origen,
            destino=oficina_destino,
            activa=True
        ).first()
    
    # Guardar en sesión para usarlos al comprar
    if oficina_origen:
        request.session['busqueda_origen_id'] = oficina_origen.id
    if oficina_destino:
        request.session['busqueda_destino_id'] = oficina_destino.id
    
    viajes = viajes.select_related('ruta', 'bus', 'ruta__origen').order_by('fecha', 'hora')
    
    # Agregar información de asientos disponibles a cada viaje
    viajes_con_info = []
    for viaje in viajes:
        disponibles = viaje.asientos.filter(estado='disponible').count()
        viajes_con_info.append({
            'viaje': viaje,
            'disponibles': disponibles,
            'tarifa': tarifa,
        })
    
    return render(request, 'buscar_viajes.html', {
        'viajes_con_info': viajes_con_info,
        'oficina_origen': oficina_origen,
        'oficina_destino': oficina_destino,
        'fecha': fecha,
        'tarifa': tarifa,
        'oficinas': Oficina.objects.filter(activa=True).order_by('nombre'),
    })


@login_required
def detalle_viaje(request, viaje_id):
    """Muestra el detalle de un viaje y sus asientos organizados como mapa"""
    from .utils import liberar_reservas_vencidas
    
    viaje = get_object_or_404(Viaje, id=viaje_id)
    liberar_reservas_vencidas(viaje=viaje)
    
    # ============================================================
    # CONTROL DEL TIEMPO DE RESERVA
    # ============================================================
    minutos_reserva = int(obtener_parametro('101', default=10))
    reserva_inicio_str = request.session.get('reserva_inicio')
    
    if reserva_inicio_str:
        # Ya hay una reserva activa: calcular tiempo restante
        try:
            reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
            expira_en = reserva_inicio + timedelta(minutes=minutos_reserva)
            
            if timezone.now() > expira_en:
                # La reserva expiró: liberar y redirigir
                liberar_reservas_vencidas(viaje=viaje)
                request.session.pop('reserva_inicio', None)
                messages.warning(request, "Tu tiempo de reserva ha expirado. Selecciona de nuevo.")
                return redirect('core:inicio')
            
            segundos_restantes = int((expira_en - timezone.now()).total_seconds())
        except (ValueError, TypeError):
            # Si el formato está mal, reiniciar
            request.session['reserva_inicio'] = timezone.now().isoformat()
            segundos_restantes = minutos_reserva * 60
    else:
        # No hay reserva activa: crear una nueva
        request.session['reserva_inicio'] = timezone.now().isoformat()
        segundos_restantes = minutos_reserva * 60
    
    # ============================================================
    # RECUPERACIÓN DE ORIGEN Y DESTINO (con prioridad segura)
    # ============================================================
    # SEGURIDAD: La sesión manda (es lo que el usuario buscó conscientemente).
    # La URL solo se usa como respaldo si NO hay sesión (caso link compartido).
    # Y siempre se valida contra la ruta del viaje.
    
    origen_id = None
    destino_id = None
    
    origen_sesion = request.session.get('busqueda_origen_id')
    destino_sesion = request.session.get('busqueda_destino_id')
    
    if origen_sesion and destino_sesion:
        # ✅ Hay sesión: se usa, prevalece sobre la URL
        origen_id = origen_sesion
        destino_id = destino_sesion
    else:
        # ⚠️ No hay sesión: probar URL (caso link compartido)
        origen_url = request.GET.get('origen')
        destino_url = request.GET.get('destino')
        
        if origen_url and destino_url:
            tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_url, destino_url)
            
            if es_valido and tarifa:
                origen_id = int(origen_url)
                destino_id = int(destino_url)
                # Guardar en sesión para los siguientes pasos
                request.session['busqueda_origen_id'] = origen_id
                request.session['busqueda_destino_id'] = destino_id
            elif not es_valido:
                messages.warning(
                    request,
                    "La ruta solicitada no es válida para este viaje. Por favor, busca de nuevo."
                )
    
    # Buscar tarifa solo con datos validados
    tarifa = None
    if origen_id and destino_id:
        tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_id, destino_id)
        
        if not es_valido:
            # IDs en sesión ya no son válidos para este viaje → limpiar
            request.session.pop('busqueda_origen_id', None)
            request.session.pop('busqueda_destino_id', None)
            tarifa = None
            origen_id = None
            destino_id = None
            messages.warning(
                request,
                "La ruta seleccionada no coincide con este viaje. Por favor, busca de nuevo."
            )
    
    # ⭐ BLOQUEO DE SEGURIDAD: Si no hay tarifa válida, no se puede comprar
    # Esto evita que alguien acceda directo por URL y compre sin precio
    if not tarifa:
        messages.error(
            request,
            "Este viaje no tiene una tarifa configurada. "
            "Por favor, realiza la búsqueda desde el inicio."
        )
        return redirect('core:inicio')
    
    # Leer el seguro del parámetro 100
    valor_seguro = obtener_parametro('100', default=0)
    
    # Obtener el cliente del usuario actual (si está logueado)
    cliente = None
    if request.user.is_authenticated:
        cliente = getattr(request.user, 'cliente', None)
    
    asientos = viaje.asientos.order_by('piso', 'fila', 'columna')
    
    # Agrupar por piso
    asientos_por_piso = {}
    for asiento in asientos:
        piso = asiento.piso
        if piso not in asientos_por_piso:
            asientos_por_piso[piso] = {}
        
        fila = asiento.fila
        if fila not in asientos_por_piso[piso]:
            asientos_por_piso[piso][fila] = []
        
        asientos_por_piso[piso][fila].append(asiento)
    
    # Ordenar filas dentro de cada piso
    for piso in asientos_por_piso:
        asientos_por_piso[piso] = dict(sorted(asientos_por_piso[piso].items()))
        
    # ⭐ INVERSIÓN DE PISOS PARA DOBLE PISO
    if len(asientos_por_piso) > 1:
        asientos_por_piso = dict(reversed(list(asientos_por_piso.items())))
    
    # ⭐ Detectar si el cliente compró este viaje hace poco
    transaccion_reciente = None
    if cliente:
        hace_5_min = timezone.now() - timedelta(minutes=5)
        transaccion_reciente = Transaccion.objects.filter(
            cliente=cliente,
            viaje=viaje,
            fecha_creacion__gte=hace_5_min,
            estado__in=['pendiente_verificacion', 'confirmada'],
        ).order_by('-fecha_creacion').first()
    
    return render(request, 'detalle_viaje.html', {
        'viaje': viaje,
        'asientos_por_piso': asientos_por_piso,
        'cliente_id': cliente.id if cliente else None,
        'tarifa': tarifa,
        'tiene_tarifa': tarifa is not None,  # ⭐ Para el template
        'seguro': valor_seguro,
        'segundos_restantes': segundos_restantes,
        'transaccion_reciente': transaccion_reciente,
    })


# ============================================================
# VISTAS DE AUTENTICACIÓN
# ============================================================

def registro(request):
    """Formulario de registro de nuevos clientes"""
    if request.user.is_authenticated:
        return redirect('core:perfil')
    
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, f"¡Bienvenido, {user.first_name}! Tu cuenta fue creada exitosamente.")
            return redirect('core:perfil')
    else:
        form = RegistroForm()
    
    return render(request, 'registro.html', {'form': form})


def login_view(request):
    """Formulario de inicio de sesión"""
    if request.user.is_authenticated:
        return redirect('core:perfil')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            # Permitir login con email también
            if '@' in username:
                user_obj = User.objects.filter(email=username).first()
                if user_obj:
                    username = user_obj.username
            
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)
                messages.success(request, f"¡Bienvenido de nuevo, {user.first_name or user.username}!")
                next_url = request.POST.get('next') or request.GET.get('next') or 'core:perfil'
                return redirect(next_url)
            else:
                messages.error(request, "Usuario o contraseña incorrectos.")
    else:
        form = LoginForm()
    
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    """Cerrar sesión y liberar asientos reservados del cliente"""
    # ⭐ Liberar asientos reservados ANTES de hacer logout
    if request.user.is_authenticated:
        cliente = getattr(request.user, 'cliente', None)
        if cliente:
            with transaction.atomic():
                asientos_reservados = Asiento.objects.select_for_update().filter(
                    estado='reservado',
                    reservado_por=cliente
                )
                
                # Registrar auditoría por cada asiento liberado
                for asiento in asientos_reservados:
                    MovimientoAsiento.objects.create(
                        asiento=asiento,
                        tipo='liberacion_manual',
                        estado_anterior='reservado',
                        estado_nuevo='disponible',
                        usuario=request.user,
                        motivo='El cliente cerró sesión',
                    )
                
                # Liberar
                asientos_reservados.update(
                    estado='disponible',
                    reservado_por=None,
                    reservado_hasta=None
                )
    
    # Limpiar la lista de seleccionados de la sesión
    request.session.pop('asientos_seleccionados', None)
    request.session.pop('reserva_inicio', None)
    
    auth_logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect('core:inicio')


@login_required
def perfil(request):
    """Perfil del cliente"""
    cliente = getattr(request.user, 'cliente', None)
    
    return render(request, 'perfil.html', {
        'cliente': cliente,
    })


@require_POST
@login_required
def reservar_asientos(request):
    """
    Recibe una lista de IDs de asientos y los reserva temporalmente
    para el cliente logueado.
    """
    viaje_id = request.POST.get('viaje_id')
    asientos_ids = request.POST.getlist('asientos[]')

    if not viaje_id or not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)

    # Verificar cantidad máxima
    max_puestos = int(obtener_parametro('103', default=5))
    if len(asientos_ids) > max_puestos:
        return JsonResponse({
            'ok': False,
            'error': f'Solo puedes reservar hasta {max_puestos} puestos por transacción.'
        }, status=400)

    # Obtener el cliente del usuario logueado
    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        return JsonResponse({
            'ok': False,
            'error': 'Debes completar tu perfil antes de comprar.'
        }, status=400)

    try:
        with transaction.atomic():
            # Bloquear los asientos solicitados
            asientos = Asiento.objects.select_for_update().filter(
                id__in=asientos_ids,
                viaje_id=viaje_id,
                tipo='asiento',
            )

            if asientos.count() != len(asientos_ids):
                return JsonResponse({
                    'ok': False,
                    'error': 'Uno o más asientos no existen.'
                }, status=400)

            # Verificar que todos estén disponibles
            no_disponibles = [a.numero for a in asientos if a.estado != 'disponible']
            if no_disponibles:
                return JsonResponse({
                    'ok': False,
                    'error': f'Los asientos {", ".join(no_disponibles)} ya no están disponibles.'
                }, status=400)

            # Reservar
            minutos = int(obtener_parametro('101', default=4))
            vence = timezone.now() + timedelta(minutes=minutos)

            Asiento.objects.filter(id__in=asientos_ids).update(
                estado='reservado',
                reservado_hasta=vence,
                reservado_por=cliente
            )

        return JsonResponse({
            'ok': True,
            'vence': vence.isoformat(),
            'minutos': minutos,
            'cantidad': len(asientos_ids),
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@require_POST
@login_required
def liberar_asientos(request):
    """
    Libera los asientos reservados por el cliente actual.
    Registra el movimiento en la auditoría.
    """
    asientos_ids = request.POST.getlist('asientos[]')

    if not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)

    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        return JsonResponse({'ok': False, 'error': 'Sin cliente.'}, status=400)

    try:
        with transaction.atomic():
            # Buscar los asientos del cliente
            asientos = Asiento.objects.select_for_update().filter(
                id__in=asientos_ids,
                estado='reservado',
                reservado_por=cliente
            )
            
            # Registrar cada movimiento en la auditoría
            for asiento in asientos:
                MovimientoAsiento.objects.create(
                    asiento=asiento,
                    tipo='liberacion_manual',
                    estado_anterior='reservado',
                    estado_nuevo='disponible',
                    usuario=request.user,
                    motivo='El cliente liberó el asiento manualmente',
                )
            
            # Ahora liberar los asientos
            asientos.update(
                estado='disponible',
                reservado_hasta=None,
                reservado_por=None
            )
        
        # ⭐ Limpiar los IDs de la sesión que correspondan
        asientos_sesion = request.session.get('asientos_seleccionados', [])
        asientos_sesion = [aid for aid in asientos_sesion if str(aid) not in asientos_ids]
        request.session['asientos_seleccionados'] = asientos_sesion

        return JsonResponse({'ok': True, 'cantidad': len(asientos_ids)})

    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@login_required
def pasajeros(request, viaje_id):
    """
    Formulario para capturar los datos de cada pasajero.
    Los asientos vienen de la reserva temporal del cliente actual.
    Al entrar, se renueva la reserva por el tiempo configurado.
    """
    from .utils import liberar_reservas_vencidas, obtener_parametro
    from datetime import timedelta
    
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
    
    # Liberar reservas vencidas por si acaso
    liberar_reservas_vencidas(viaje=viaje)
    
    # ==========================================
    # 1. CÁLCULO DEL TIEMPO
    # ==========================================
    minutos = int(obtener_parametro('101', default=10))
    reserva_inicio_str = request.session.get('reserva_inicio')
    if reserva_inicio_str:
        try:
            reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
            expira_en = reserva_inicio + timedelta(minutes=minutos)
            if timezone.now() > expira_en:
                liberar_reservas_vencidas(viaje=viaje)
                request.session.pop('reserva_inicio', None)
                messages.warning(request, "Tu tiempo de reserva ha expirado. Selecciona de nuevo.")
                return redirect('core:inicio')
            segundos_restantes = int((expira_en - timezone.now()).total_seconds())
        except (ValueError, TypeError):
            segundos_restantes = minutos * 60
    else:
        segundos_restantes = minutos * 60

    # ==========================================
    # 2. RECUPERAR Y VALIDAR TARIFA (SEGURIDAD)
    # ==========================================
    origen_id = request.session.get('busqueda_origen_id')
    destino_id = request.session.get('busqueda_destino_id')
    
    tarifa = None
    if origen_id and destino_id:
        tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_id, destino_id)
        if not es_valido:
            request.session.pop('busqueda_origen_id', None)
            request.session.pop('busqueda_destino_id', None)
            messages.error(request, "Error de seguridad. Vuelve a buscar el viaje.")
            return redirect('core:inicio')
    
    # ⭐ FIX: Si no hay tarifa, no permitir avanzar
    if not tarifa:
        messages.error(
            request,
            "No hay tarifa configurada para esta ruta. "
            "Por favor, selecciona el viaje desde la búsqueda."
        )
        return redirect('core:inicio')
        
    # Leer el seguro del parámetro 100
    valor_seguro = obtener_parametro('100', default=0)
    
    # ⭐ Solo usar los asientos que el cliente seleccionó en esta sesión
    asientos_sesion = request.session.get('asientos_seleccionados', [])
    
    if asientos_sesion:
        asientos = Asiento.objects.filter(
            id__in=asientos_sesion,
            viaje=viaje,
            estado='reservado',
            reservado_por=cliente,
            reservado_hasta__gt=timezone.now()
        ).order_by('numero')
    else:
        # Fallback: si no hay sesión, usar todos los reservados (comportamiento anterior)
        asientos = Asiento.objects.filter(
            viaje=viaje,
            estado='reservado',
            reservado_por=cliente,
            reservado_hasta__gt=timezone.now()
        ).order_by('numero')
    
    if not asientos.exists():
        messages.warning(request, "No tienes asientos reservados. Selecciona asientos primero.")
        return redirect('core:detalle_viaje', viaje_id=viaje.id)
    
    # Renovar la reserva
    nuevo_vence = timezone.now() + timedelta(minutes=minutos)
    asientos.update(reservado_hasta=nuevo_vence)
    
    # Si es POST, procesar los datos
    if request.method == 'POST':
        formularios = []
        valido = True
        
        for asiento in asientos:
            prefix = f"asiento_{asiento.id}"
            form = PasajeroForm(request.POST, prefix=prefix)
            formularios.append((asiento, form))
            if not form.is_valid():
                valido = False
        
        if valido:
            pasajeros_data = []
            for asiento, form in formularios:
                pasajeros_data.append({
                    'asiento_id': asiento.id,
                    'asiento_numero': asiento.numero,
                    'nombre': form.cleaned_data['nombre'],
                    'cedula': form.cleaned_data['cedula'],
                    'telefono': form.cleaned_data['telefono'],
                    'tipo_pasajero': form.cleaned_data['tipo_pasajero'],
                })
            
            request.session['pasajeros_data'] = pasajeros_data
            request.session['viaje_id'] = viaje.id
            return redirect('core:seleccionar_metodo_pago', viaje_id=viaje.id)
    else:
        # ⭐ GET: crear formularios con datos previos de la sesión si existen
        pasajeros_previos = request.session.get('pasajeros_data', [])
        pasajeros_dict = {p['asiento_id']: p for p in pasajeros_previos}
        
        formularios = []
        for asiento in asientos:
            prefix = f"asiento_{asiento.id}"
            
            # Buscar si ya hay datos de este asiento en la sesión
            inicial = {}
            if asiento.id in pasajeros_dict:
                p = pasajeros_dict[asiento.id]
                inicial = {
                    'nombre': p.get('nombre', ''),
                    'cedula': p.get('cedula', ''),
                    'telefono': p.get('telefono', ''),
                    'tipo_pasajero': p.get('tipo_pasajero', 'normal'),
                }
            
            form = PasajeroForm(prefix=prefix, initial=inicial)
            formularios.append((asiento, form))
    
    cantidad = asientos.count()
    precio_unitario = (tarifa.monto_usd + valor_seguro) if tarifa else 0
    total_usd = precio_unitario * cantidad
    
    expiracion_iso = (timezone.now() + timedelta(seconds=segundos_restantes)).isoformat()
    return render(request, 'pasajeros.html', {
        'viaje': viaje,
        'formularios': formularios,
        'cantidad': cantidad,
        'total_usd': total_usd,
        'tarifa': tarifa,
        'seguro': valor_seguro,
        'segundos_restantes': segundos_restantes,
        'expiracion_iso': expiracion_iso,
        'minutos_reserva': minutos,
    })


@require_POST
@login_required
def reservar_temporal(request):
    """
    Bloquea un asiento temporalmente por el tiempo del parámetro 113.
    Se llama cuando el cliente hace clic en un asiento disponible.
    """
    from .utils import obtener_parametro
    from datetime import timedelta
    
    viaje_id = request.POST.get('viaje_id')
    asiento_id = request.POST.get('asiento_id')
    
    if not viaje_id or not asiento_id:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        return JsonResponse({'ok': False, 'error': 'Sin cliente.'}, status=400)
    
    segundos = int(obtener_parametro('113', default=30))
    vence = timezone.now() + timedelta(seconds=segundos)
    
    try:
        with transaction.atomic():
            asiento = Asiento.objects.select_for_update().get(id=asiento_id, viaje_id=viaje_id)
            
            # Verificar que sea un asiento real
            if asiento.tipo != 'asiento':
                return JsonResponse({'ok': False, 'error': 'Esta posición no es un asiento.'}, status=400)
            
            # Si está reservado por el mismo cliente, renovar
            if asiento.estado == 'reservado' and asiento.reservado_por == cliente:
                asiento.reservado_hasta = vence
                asiento.save()
                return JsonResponse({'ok': True, 'vence': vence.isoformat()})
                
            # Verificar el máximo ANTES de reservar
            max_puestos = int(obtener_parametro('103', default=5))
            asientos_actuales = Asiento.objects.filter(
                viaje_id=viaje_id,
                estado='reservado',
                reservado_por=cliente,
                reservado_hasta__gt=timezone.now()
            ).count()
            
            if asientos_actuales >= max_puestos:
                return JsonResponse({
                    'ok': False,
                    'error': f'Ya tienes {asientos_actuales} asientos reservados. El máximo es {max_puestos} por transacción.'
                }, status=400)
            
            # Si está reservado por otro o vendido, error
            if asiento.estado != 'disponible':
                return JsonResponse({
                    'ok': False,
                    'error': f'El puesto {asiento.numero} ya no está disponible. Por favor selecciona otro disponible.'
                }, status=400)
            
            # Reservar
            asiento.estado = 'reservado'
            asiento.reservado_hasta = vence
            asiento.reservado_por = cliente
            asiento.save()
            
            # ⭐ Guardar el ID del asiento seleccionado en la sesión
            asientos_sesion = request.session.get('asientos_seleccionados', [])
            if asiento.id not in asientos_sesion:
                asientos_sesion.append(asiento.id)
                request.session['asientos_seleccionados'] = asientos_sesion
        
        return JsonResponse({'ok': True, 'vence': vence.isoformat()})
    
    except Asiento.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Asiento no encontrado.'}, status=404)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@require_POST
@login_required
def renovar_reserva(request):
    """
    Renueva el bloqueo temporal de los asientos del cliente actual.
    Se llama cada N segundos mientras el cliente está activo.
    """
    from .utils import obtener_parametro
    from datetime import timedelta
    
    viaje_id = request.POST.get('viaje_id')
    asientos_ids = request.POST.getlist('asientos[]')
    
    if not viaje_id or not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        return JsonResponse({'ok': False, 'error': 'Sin cliente.'}, status=400)
    
    segundos = int(obtener_parametro('113', default=30))
    vence = timezone.now() + timedelta(seconds=segundos)
    
    try:
        with transaction.atomic():
            Asiento.objects.select_for_update().filter(
                id__in=asientos_ids,
                viaje_id=viaje_id,
                estado='reservado',
                reservado_por=cliente
            ).update(reservado_hasta=vence)
        
        return JsonResponse({'ok': True, 'vence': vence.isoformat()})
    
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@login_required
def pago(request, viaje_id):
    """Formulario de pago para usuarios web"""
    from .utils import obtener_parametro, liberar_reservas_vencidas
    from datetime import timedelta
    
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    
    # ==========================================
    # VALIDACIÓN DE TARIFA (SEGURIDAD)
    # ==========================================
    origen_id = request.session.get('busqueda_origen_id')
    destino_id = request.session.get('busqueda_destino_id')
    
    tarifa = None
    if origen_id and destino_id:
        tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_id, destino_id)
        if not es_valido:
            request.session.pop('busqueda_origen_id', None)
            request.session.pop('busqueda_destino_id', None)
            messages.error(request, "Error de seguridad. Vuelve a buscar el viaje.")
            return redirect('core:inicio')
    
    # ⭐ FIX: Si no hay tarifa, no permitir avanzar
    if not tarifa:
        messages.error(
            request,
            "No hay tarifa configurada. No se puede procesar la compra."
        )
        return redirect('core:inicio')
    
    # Leer el seguro del parámetro 100
    valor_seguro = obtener_parametro('100', default=0)
    
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
        
    # Recuperar los datos de los pasajeros de la sesión
    pasajeros_data = request.session.get('pasajeros_data', [])
    if not pasajeros_data:
        messages.warning(request, "No hay datos de pasajeros. Completa el formulario primero.")
        return redirect('core:pasajeros', viaje_id=viaje.id)
        
    # Obtener los asientos reservados
    asientos_ids = [p['asiento_id'] for p in pasajeros_data]
    asientos = Asiento.objects.filter(
        id__in=asientos_ids,
        viaje=viaje,
        estado='reservado',
        reservado_por=cliente
    )
    
    if asientos.count() != len(asientos_ids):
        messages.warning(request, "Algunos asientos ya no están disponibles. Selecciona de nuevo.")
        return redirect('core:detalle_viaje', viaje_id=viaje.id)
    
    # Calcular el tiempo restante según reserva_inicio
    minutos = int(obtener_parametro('101', default=10))
    reserva_inicio_str = request.session.get('reserva_inicio')
    if reserva_inicio_str:
        try:
            reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
            expira_en = reserva_inicio + timedelta(minutes=minutos)
            if timezone.now() > expira_en:
                liberar_reservas_vencidas(viaje=viaje)
                request.session.pop('reserva_inicio', None)
                messages.warning(request, "Tu tiempo de reserva ha expirado. Selecciona de nuevo.")
                return redirect('core:inicio')
            segundos_restantes = int((expira_en - timezone.now()).total_seconds())
        except (ValueError, TypeError):
            segundos_restantes = minutos * 60
    else:
        segundos_restantes = minutos * 60
    vence = timezone.now() + timedelta(minutes=minutos)
    asientos.update(reservado_hasta=vence)
    
    # Calcular totales
    cantidad = len(pasajeros_data)
    if tarifa:
        precio_unitario = tarifa.monto_usd + valor_seguro
    else:
        precio_unitario = 0
    total_usd = precio_unitario * cantidad
    tasa_bcv = obtener_parametro('107', default=0)
    total_bs = (total_usd * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0
    
    # Datos de la cuenta destino
    datos_cuenta = {
        'banco': obtener_parametro('120', default=''),
        'telefono': obtener_parametro('121', default=''),
        'cedula': obtener_parametro('122', default=''),
        'cuenta': obtener_parametro('123', default=''),
        'titular': obtener_parametro('124', default=''),
    }
    
    if request.method == 'POST':
        datos_post = request.POST.copy()
        monto_str = datos_post.get('monto_pagado_bs', '')
        
        if monto_str:
            monto_limpio = monto_str.replace('.', '').replace(',', '.')
            datos_post['monto_pagado_bs'] = monto_limpio
            
        form = PagoWebForm(datos_post, request.FILES)
        
        if form.is_valid():
            monto_pagado = form.cleaned_data['monto_pagado_bs']
            diferencia = monto_pagado - total_bs
            monto_faltante = abs(diferencia) if diferencia < 0 else Decimal('0')
            monto_excedente = diferencia if diferencia > Decimal('0.01') else Decimal('0')
            
            confirmar = request.POST.get('confirmar_diferencia')
            if (abs(diferencia) > Decimal('0.01')) and not confirmar:
                return render(request, 'pago.html', {
                    'viaje': viaje,
                    'form': form,
                    'cantidad': cantidad,
                    'total_usd': total_usd,
                    'total_bs': total_bs,
                    'tasa_bcv': tasa_bcv,
                    'datos_cuenta': datos_cuenta,
                    'minutos_reserva': minutos,
                    'tarifa': tarifa,
                    'monto_pagado': monto_pagado,
                    'diferencia': diferencia,
                    'monto_faltante': monto_faltante,
                    'monto_excedente': monto_excedente,
                    'mostrar_aviso': True,
                })
            
            codigo = generar_codigo_transaccion()        
            with transaction.atomic():
                transaccion = Transaccion.objects.create(
                    codigo=codigo,
                    cliente=cliente,
                    viaje=viaje,
                    cantidad_boletos=cantidad,
                    monto_total_usd=total_usd,
                    monto_total_bs=total_bs,
                    tasa_bcv=tasa_bcv,
                    estado='pendiente_verificacion',
                    vendido_por=None,
                    dispositivo_venta=request.META.get('HTTP_USER_AGENT', 'Desconocido'),
                    oficina_destino=viaje.ruta.destinos.first(),
                )
                
                observacion = ''
                if abs(diferencia) > Decimal('0.01'):
                    observacion = f"Diferencia de monto: pagó Bs. {monto_pagado}, esperado Bs. {total_bs}. Diferencia: Bs. {diferencia:,.2f}"
                
                pago_obj = Pago.objects.create(
                    transaccion=transaccion,
                    metodo=form.cleaned_data['metodo'],
                    monto_usd=total_usd,
                    monto_bs=monto_pagado,
                    tasa_bcv=tasa_bcv,
                    banco_origen=form.cleaned_data['banco_origen'],
                    telefono_origen=form.cleaned_data['telefono_origen'],
                    cedula_origen=form.cleaned_data['cedula_origen'],
                    referencia=form.cleaned_data['referencia'],
                    comprobante=form.cleaned_data['comprobante'],
                    estado='pendiente',
                    observacion=observacion,
                )
  
                for p in pasajeros_data:
                    asiento = Asiento.objects.select_for_update().get(id=p['asiento_id'])
                    
                    asiento.estado = 'vendido'
                    asiento.reservado_hasta = None
                    asiento.reservado_por = None
                    asiento.save()
                    
                    if tarifa:
                        monto_tarifa = tarifa.monto_usd
                        monto_seguro = valor_seguro
                    else:
                        monto_tarifa = 0
                        monto_seguro = 0
                    monto_total_boleto = monto_tarifa + monto_seguro
                    
                    boleto = Boleto.objects.create(
                        transaccion=transaccion,
                        viaje=viaje,
                        asiento=asiento,
                        pasajero_cedula=p['cedula'],
                        pasajero_nombre=p['nombre'],
                        pasajero_telefono=p.get('telefono', ''),
                        tipo_pasajero=p['tipo_pasajero'],
                        monto_tarifa_usd=monto_tarifa,
                        monto_seguro_usd=monto_seguro,
                        monto_total_usd=monto_total_boleto,
                        tasa_bcv=tasa_bcv,
                        monto_total_bs=(monto_total_boleto * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0,
                        codigo_qr=generar_codigo_qr(),
                        estado='vendido',
                    )
            
            request.session.pop('pasajeros_data', None)
            request.session.pop('viaje_id', None)
            request.session.pop('asientos_seleccionados', None)
            
            messages.success(request, "¡Pago registrado! Tu compra está pendiente de verificación.")
            return redirect('core:confirmacion', transaccion_id=transaccion.id)
    else:
        # ⭐ Preseleccionar el método según el ?metodo= de la URL
        metodo_inicial = request.GET.get('metodo', 'pago_movil')
        form = PagoWebForm(initial={'metodo': metodo_inicial})
    
    return render(request, 'pago.html', {
        'viaje': viaje,
        'form': form,
        'cantidad': cantidad,
        'tarifa': tarifa,
        'seguro': valor_seguro,
        'segundos_restantes': segundos_restantes,
        'total_usd': total_usd,
        'total_bs': total_bs,
        'tasa_bcv': tasa_bcv,
        'datos_cuenta': datos_cuenta,
        'minutos_reserva': minutos,
    })


@login_required
def confirmacion(request, transaccion_id):
    """Página de confirmación después del pago"""
    transaccion = get_object_or_404(Transaccion, id=transaccion_id)
    
    # Verificar que la transacción sea del cliente actual
    cliente = getattr(request.user, 'cliente', None)
    if not cliente or transaccion.cliente != cliente:
        messages.error(request, "No tienes acceso a esta transacción.")
        return redirect('core:inicio')
    
    # Obtener los boletos de la transacción
    boletos = transaccion.boletos.all().order_by('asiento__numero')
    
    # Obtener el pago
    pago_obj = transaccion.pagos.first()
    
    return render(request, 'confirmacion.html', {
        'transaccion': transaccion,
        'boletos': boletos,
        'pago': pago_obj,
    })


from django.contrib.auth import login
from django.contrib.auth.models import User
from .models import Cliente


def registro_usuario(request):
    if request.user.is_authenticated:
        return redirect('core:inicio')
    
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            # Extraemos los datos limpios
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            password = form.cleaned_data['password1']
            cedula = form.cleaned_data['cedula']
            telefono = form.cleaned_data['telefono']
            
            # 1. Crear el usuario base de Django
            user = User.objects.create_user(
                username=username, 
                email=email, 
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            
            # 2. Crear el perfil de Cliente vinculado
            Cliente.objects.create(
                user=user,
                cedula=cedula,
                telefono=telefono
            )
            
            # 3. Autenticar y redirigir al usuario inmediatamente
            login(request, user)
            messages.success(request, f"¡Bienvenido a Viba-Web, {first_name}! Tu cuenta ha sido creada con éxito.")
            next_url = request.POST.get('next') or request.GET.get('next') or 'core:inicio'
            return redirect(next_url)
    else:
        form = RegistroForm()
        
    return render(request, 'registro.html', {'form': form})

@login_required
def seleccionar_metodo_pago(request, viaje_id):
    """Muestra los métodos de pago disponibles según los parámetros 130, 131, 132"""
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
    
    # Recuperar datos de pasajeros de la sesión
    pasajeros_data = request.session.get('pasajeros_data', [])
    if not pasajeros_data:
        messages.warning(request, "No hay datos de pasajeros. Completa el formulario primero.")
        return redirect('core:pasajeros', viaje_id=viaje.id)
    
    # Leer los 3 parámetros de métodos de pago
    permite_pago_movil = obtener_parametro('131', default=True)
    permite_transferencia = obtener_parametro('130', default=False)
    permite_pasarela = obtener_parametro('132', default=True)
    
    # Construir lista de métodos disponibles
    metodos = []
    if permite_pago_movil:
        metodos.append({
            'id': 'pago_movil',
            'nombre': 'Pago Móvil',
            'icono': 'bi-phone-fill',
            'descripcion': 'Paga desde tu banco con tu teléfono en segundos.',
            'url': f'/viajes/{viaje.id}/pago/?metodo=pago_movil',
        })
    if permite_transferencia:
        metodos.append({
            'id': 'transferencia',
            'nombre': 'Transferencia Bancaria',
            'icono': 'bi-bank2',
            'descripcion': 'Transfiere desde tu banca en línea o taquilla.',
            'url': f'/viajes/{viaje.id}/pago/?metodo=transferencia',
        })
    if permite_pasarela:
        metodos.append({
            'id': 'pasarela',
            'nombre': 'Pasarela Digital',
            'icono': 'bi-credit-card-fill',
            'descripcion': 'Paga con tarjeta de crédito/débito de forma segura.',
            'url': f'/viajes/{viaje.id}/pasarela-virtual/',
        })

    # Si no hay ningún método habilitado, no permitir comprar
    if not metodos:
        messages.error(
            request,
            "No hay métodos de pago habilitados. Contacta a la empresa."
        )
        return redirect('core:inicio')

    # ⭐ Si solo hay UN método habilitado Y NO venimos de "cancelar" → ir directo
    # (si venimos de cancelar, mostramos la pantalla para no crear un loop infinito)
    from_cancelar = request.GET.get('from') == 'cancelar'
    if len(metodos) == 1 and not from_cancelar:
        return redirect(metodos[0]['url'])
    
    # Si venimos de cancelar y solo hay 1 método, pasamos a la plantilla
    # una bandera para mostrar el botón "Cancelar compra"
    mostrar_cancelar = from_cancelar
    
    # Calcular totales para mostrar en la pantalla
    cantidad = len(pasajeros_data)
    valor_seguro = obtener_parametro('100', default=0)
    origen_id = request.session.get('busqueda_origen_id')
    destino_id = request.session.get('busqueda_destino_id')
    
    tarifa = None
    if origen_id and destino_id:
        tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_id, destino_id)
        if not es_valido:
            request.session.pop('busqueda_origen_id', None)
            request.session.pop('busqueda_destino_id', None)
            messages.error(request, "Error de seguridad. Vuelve a buscar el viaje.")
            return redirect('core:inicio')
    
    if not tarifa:
        messages.error(request, "No hay tarifa configurada.")
        return redirect('core:inicio')
    
    precio_unitario = tarifa.monto_usd + valor_seguro
    total_usd = precio_unitario * cantidad
    tasa_bcv = obtener_parametro('107', default=0)
    total_bs = (total_usd * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0
    
    return render(request, 'seleccionar_metodo_pago.html', {
        'viaje': viaje,
        'metodos': metodos,
        'cantidad': cantidad,
        'total_usd': total_usd,
        'total_bs': total_bs,
        'tasa_bcv': tasa_bcv,
        'mostrar_cancelar': mostrar_cancelar,   # ⭐ NUEVO
    })

@login_required
def pasarela_virtual_view(request, viaje_id):
    """Pasarela de pagos virtual simulada para demostraciones con formulario seguro de tarjeta/token"""
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    
    # ⭐ Validar que la pasarela digital esté habilitada (parámetro 132)
    permite_pasarela = obtener_parametro('132', default=True)
    if not permite_pasarela:
        messages.error(
            request,
            "La pasarela digital no está habilitada. Elige otro método de pago."
        )
        return redirect('core:seleccionar_metodo_pago', viaje_id=viaje.id)
    
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
        
    # Recuperar datos de pasajeros de la sesión
    pasajeros_data = request.session.get('pasajeros_data', [])
    if not pasajeros_data:
        messages.warning(request, "No hay datos de pasajeros. Completa el formulario primero.")
        return redirect('core:pasajeros', viaje_id=viaje.id)
        
    # Validar disponibilidad de asientos
    asientos_ids = [p['asiento_id'] for p in pasajeros_data]
    asientos = Asiento.objects.filter(id__in=asientos_ids, viaje=viaje, estado='reservado', reservado_por=cliente)
    
    if asientos.count() != len(asientos_ids):
        messages.warning(request, "Algunos asientos ya no están disponibles.")
        return redirect('core:detalle_viaje', viaje_id=viaje.id)

    # ==========================================
    # VALIDACIÓN DE TARIFA (SEGURIDAD)
    # ==========================================
    cantidad = len(pasajeros_data)
    valor_seguro = obtener_parametro('100', default=0)
    origen_id = request.session.get('busqueda_origen_id')
    destino_id = request.session.get('busqueda_destino_id')
    
    tarifa = None
    if origen_id and destino_id:
        tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_id, destino_id)
        if not es_valido:
            request.session.pop('busqueda_origen_id', None)
            request.session.pop('busqueda_destino_id', None)
            messages.error(request, "Error de seguridad. Vuelve a buscar el viaje.")
            return redirect('core:inicio')
    
    # ⭐ FIX: Si no hay tarifa, no permitir avanzar (última defensa)
    if not tarifa:
        messages.error(
            request,
            "No hay tarifa configurada. No se puede procesar la compra."
        )
        return redirect('core:inicio')
    
    precio_unitario = (tarifa.monto_usd + valor_seguro) if tarifa else 0
    total_usd = precio_unitario * cantidad
    tasa_bcv = obtener_parametro('107', default=0)
    total_bs = (total_usd * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0
    
    if request.method == 'POST':
        form = PasarelaVirtualForm(request.POST)
        
        if form.is_valid():
            codigo = generar_codigo_transaccion()
            
            with transaction.atomic():
                # 1. Crear la transacción con su trazabilidad completa
                transaccion = Transaccion.objects.create(
                    codigo=codigo,
                    cliente=cliente,
                    viaje=viaje,
                    cantidad_boletos=cantidad,
                    monto_total_usd=total_usd,
                    monto_total_bs=total_bs,
                    tasa_bcv=tasa_bcv,
                    estado='confirmada',
                    vendido_por=None,
                    dispositivo_venta=request.META.get('HTTP_USER_AGENT', 'Desconocido'),
                    oficina_destino=viaje.ruta.destinos.first(),
                )
                
                # 2. Registrar el pago digital aprobado
                pago_obj = Pago.objects.create(
                    transaccion=transaccion,
                    metodo='pasarela_digital',
                    monto_usd=total_usd,
                    monto_bs=total_bs,
                    tasa_bcv=tasa_bcv,
                    referencia='PASS-' + codigo,
                    estado='aprobado',
                    observacion="Pago procesado exitosamente mediante Pasarela Digital segura."
                )
                
                # 3. Marcar asientos como vendidos y generar los boletos
                for p in pasajeros_data:
                    asiento = Asiento.objects.select_for_update().get(id=p['asiento_id'])
                    asiento.estado = 'vendido'
                    asiento.reservado_hasta = None
                    asiento.reservado_por = None
                    asiento.save()
                    
                    monto_tarifa = tarifa.monto_usd if tarifa else 0
                    monto_seguro = valor_seguro if tarifa else 0
                    monto_total_boleto = monto_tarifa + monto_seguro
                    
                    Boleto.objects.create(
                        transaccion=transaccion,
                        viaje=viaje,
                        asiento=asiento,
                        pasajero_cedula=p['cedula'],
                        pasajero_nombre=p['nombre'],
                        pasajero_telefono=p.get('telefono', ''),
                        tipo_pasajero=p['tipo_pasajero'],
                        monto_tarifa_usd=monto_tarifa,
                        monto_seguro_usd=monto_seguro,
                        monto_total_usd=monto_total_boleto,
                        tasa_bcv=tasa_bcv,
                        monto_total_bs=(monto_total_boleto * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0,
                        codigo_qr=generar_codigo_qr(),
                        estado='vendido',
                    )
            
            # Limpiar sesión y notificar éxito
            request.session.pop('pasajeros_data', None)
            request.session.pop('asientos_seleccionados', None)
            messages.success(request, "¡Compra registrada exitosamente!")
            # ⭐ REDIRIGIR a la página de confirmación
            return redirect('core:confirmacion', transaccion_id=transaccion.id)
    else:
        form = PasarelaVirtualForm()

    return render(request, 'pasarela_virtual.html', {
        'form': form,
        'viaje': viaje,
        'cantidad': cantidad,
        'total_usd': total_usd,
        'total_bs': total_bs,
        'tasa_bcv': tasa_bcv,
    })


# ============================================================
# VISTA PERSONALIZADA DE ERROR CSRF
# ============================================================

def mi_vista_error_csrf(request, reason=""):
    """Vista personalizada para errores CSRF (evita el 403 feo de Django)."""
    from django.http import JsonResponse
    
    # Caso 1: Petición AJAX/fetch → JSON
    if (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Accept', '').startswith('application/json')):
        return JsonResponse({
            'ok': False,
            'error': 'Sesión expirada. Recarga la página e intenta de nuevo.',
            'csrf_failed': True,
        }, status=403)
    
    # Caso 2: Formulario HTML
    messages.warning(
        request,
        "Tu sesión de seguridad expiró. Por favor, intenta de nuevo."
    )
    
    if request.path.startswith('/login/'):
        return redirect('core:login')
    if request.path.startswith('/registro/'):
        return redirect('core:registro')
    
    return redirect('core:inicio')



# ============================================================
# MIS BOLETOS (historial del cliente)
# ============================================================

@login_required
def mis_boletos(request):
    """Página que muestra todos los boletos comprados por el cliente"""
    cliente = getattr(request.user, 'cliente', None)
    
    if not cliente:
        messages.error(
            request,
            "Debes completar tu perfil antes de ver tus boletos."
        )
        return redirect('core:perfil')
    
    # Obtener todas las transacciones del cliente
    from .models import Transaccion, Boleto
    
    transacciones = Transaccion.objects.filter(cliente=cliente).order_by('-fecha_creacion')
    
    # Para cada transacción, traer sus boletos
    transacciones_con_boletos = []
    for t in transacciones:
        boletos = t.boletos.all().order_by('asiento__numero')
        transacciones_con_boletos.append({
            'transaccion': t,
            'boletos': boletos,
            'cantidad': boletos.count(),
        })
    
    return render(request, 'mis_boletos.html', {
        'cliente': cliente,
        'transacciones_con_boletos': transacciones_con_boletos,
    })
