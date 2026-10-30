from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import (
    Oficina, Viaje, Asiento, Transaccion, Pago, Boleto, Tarifa, 
    MovimientoAsiento, UsuarioEmpresa, Cliente, Credito, 
    PlantillaBus, PlantillaAsiento, Ruta, RutaParada, Suscripcion
)
from .forms import RegistroForm, LoginForm, PagoWebForm, PasajeroForm, PasarelaVirtualForm
from .utils import (
    obtener_parametro, liberar_reservas_vencidas, generar_codigo_transaccion,
    generar_codigo_qr, asiento_esta_disponible_en_tramo
)

# ============================================================
# SEGURIDAD: SESIÓN ÚNICA POR USUARIO-WEB
# ============================================================
def procesar_login_con_espera(request, user):
    from .models import SesionActiva
    if user.is_staff or user.is_superuser:
        return True, "OK"
    cliente = getattr(user, 'cliente', None)
    if not cliente:
        return True, "OK"
    minutos_espera = int(obtener_parametro('142', default=3))
    sesion_existente = SesionActiva.objects.filter(user=user).first()
    if sesion_existente:
        inactividad = timezone.now() - sesion_existente.ultima_actividad
        if inactividad < timedelta(minutes=minutos_espera):
            minutos_restantes = minutos_espera - int(inactividad.total_seconds() / 60)
            if minutos_restantes < 1:
                minutos_restantes = 1
            return False, (f"Estimado cliente: su cuenta se encuentra activa en otro dispositivo. "
                           f"Por su seguridad, aguarde {minutos_restantes} minuto(s) antes de intentar nuevamente.")
        else:
            sesion_existente.delete()
    return True, "OK"

# ============================================================
# FUNCIÓN AUXILIAR DE SEGURIDAD
# ============================================================
def validar_tarifa_para_viaje(viaje, origen_id, destino_id):
    if not (origen_id and destino_id):
        return (None, True)
    try:
        origen_id_int = int(origen_id)
        destino_id_int = int(destino_id)
    except (ValueError, TypeError):
        return (None, False)
    origen_valido = (viaje.ruta.origen_id == origen_id_int)
    destino_valido = viaje.ruta.destinos.filter(id=destino_id_int).exists()
    if not (origen_valido and destino_valido):
        return (None, False)
    tarifa = Tarifa.objects.filter(origen_id=origen_id_int, destino_id=destino_id_int, activa=True).first()
    return (tarifa, True)

# ============================================================
# VISTAS PÚBLICAS
# ============================================================
def inicio(request):
    # ⭐ Limpiar mensajes viejos para evitar acumulación
    from django.contrib.messages import get_messages
    list(get_messages(request))
    # ⭐ Si es empleado, redirigir a su área de taquilla
    if request.user.is_authenticated and getattr(request.user, 'usuarioempresa', None):
        return redirect('core:taquilla_inicio')
        
    request.session.pop('reserva_inicio', None)
    logout_reciente = request.session.pop('logout_reciente', False)
    cliente = getattr(request.user, 'cliente', None)
    if cliente:
        with transaction.atomic():
            asientos_reservados = Asiento.objects.select_for_update().filter(estado='reservado', reservado_por=request.user)
            for asiento in asientos_reservados:
                MovimientoAsiento.objects.create(asiento=asiento, tipo='liberacion_manual', estado_anterior='reservado', estado_nuevo='disponible', usuario=request.user, motivo='El cliente volvió al inicio')
            asientos_reservados.update(estado='disponible', reservado_hasta=None, reservado_por=None)
    oficinas = Oficina.objects.filter(activa=True).order_by('nombre')
    bienvenida_titulo = obtener_parametro('160', default='Bienvenido a Viba-Web')
    bienvenida_subtitulo = obtener_parametro('161', default='Compra tus boletos de autobús de forma rápida y segura')
    return render(request, 'inicio.html', {
        'oficinas': oficinas, 'logout_reciente': logout_reciente,
        'bienvenida_titulo': bienvenida_titulo, 'bienvenida_subtitulo': bienvenida_subtitulo,
    })

@login_required
def detalle_viaje(request, viaje_id):
    viaje = get_object_or_404(Viaje, id=viaje_id)
    
    minutos_reserva = int(obtener_parametro('101', default=10))
    reserva_inicio_str = request.session.get('reserva_inicio')
    
    if reserva_inicio_str:
        try:
            reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
            expira_en = reserva_inicio + timedelta(minutes=minutos_reserva)
            
            if timezone.now() > expira_en:
                liberar_reservas_vencidas(viaje=viaje)
                request.session.pop('reserva_inicio', None)
                messages.warning(request, "Tu tiempo de reserva ha expirado. Selecciona de nuevo.")
                return redirect('core:inicio')
            
            segundos_restantes = int((expira_en - timezone.now()).total_seconds())
            
            # ⭐ PROTECCIÓN AL REGRESAR DE PAGO/PASAJEROS:
            # Refrescamos el tiempo en la base de datos para los asientos del usuario actual 
            # asegurando que la limpieza global no los borre mientras navegaba por los formularios.
            Asiento.objects.filter(
                viaje=viaje,
                estado='reservado',
                reservado_por=request.user
            ).update(reservado_hasta=expira_en)
            
        except (ValueError, TypeError):
            request.session['reserva_inicio'] = timezone.now().isoformat()
            segundos_restantes = minutos_reserva * 60
    else:
        request.session['reserva_inicio'] = timezone.now().isoformat()
        segundos_restantes = minutos_reserva * 60

    # Limpiamos únicamente las reservas vencidas de otros usuarios
    liberar_reservas_vencidas(viaje=viaje)

    origen_id = None
    destino_id = None
    origen_sesion = request.session.get('busqueda_origen_id')
    destino_sesion = request.session.get('busqueda_destino_id')
    
    if origen_sesion and destino_sesion:
        origen_id = origen_sesion
        destino_id = destino_sesion
    else:
        origen_url = request.GET.get('origen')
        destino_url = request.GET.get('destino')
        if origen_url and destino_url:
            tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_url, destino_url)
            if es_valido and tarifa:
                origen_id = int(origen_url)
                destino_id = int(destino_url)
                request.session['busqueda_origen_id'] = origen_id
                request.session['busqueda_destino_id'] = destino_id
            elif not es_valido:
                messages.warning(request, "La ruta solicitada no es válida para este viaje. Por favor, busca de nuevo.")
                
    tarifa = None
    if origen_id and destino_id:
        tarifa, es_valido = validar_tarifa_para_viaje(viaje, origen_id, destino_id)
        if not es_valido:
            request.session.pop('busqueda_origen_id', None)
            request.session.pop('busqueda_destino_id', None)
            tarifa = None
            origen_id = None
            destino_id = None
            messages.warning(request, "La ruta seleccionada no coincide con este viaje. Por favor, busca de nuevo.")
            
    if not tarifa:
        messages.error(request, "Este viaje no tiene una tarifa configurada. Por favor, realiza la búsqueda desde el inicio.")
        return redirect('core:inicio')
        
    valor_seguro = obtener_parametro('100', default=0)
    cliente = getattr(request.user, 'cliente', None)
    asientos = viaje.asientos.order_by('piso', 'fila', 'columna')
    asientos_por_piso = {}
    
    for asiento in asientos:
        piso = asiento.piso
        if piso not in asientos_por_piso: asientos_por_piso[piso] = {}
        fila = asiento.fila
        if fila not in asientos_por_piso[piso]: asientos_por_piso[piso][fila] = []
        asientos_por_piso[piso][fila].append(asiento)
        
    for piso in asientos_por_piso:
        asientos_por_piso[piso] = dict(sorted(asientos_por_piso[piso].items()))
        
    if len(asientos_por_piso) > 1:
        asientos_por_piso = dict(reversed(list(asientos_por_piso.items())))

    transaccion_reciente = None
    if cliente:
        hace_5_min = timezone.now() - timedelta(minutes=5)
        transaccion_reciente = Transaccion.objects.filter(
            cliente=cliente, viaje=viaje, fecha_creacion__gte=hace_5_min,
            estado__in=['pendiente_verificacion', 'confirmada']
        ).order_by('-fecha_creacion').first()

    # ⭐ CALCULAR LA EXPIRACIÓN PARA EL RELOJ FLOTANTE
    if reserva_inicio_str:
        expiracion_iso = (reserva_inicio + timedelta(minutes=minutos_reserva)).isoformat()
    else:
        expiracion_iso = (timezone.now() + timedelta(minutes=minutos_reserva)).isoformat()
    
    return render(request, 'detalle_viaje.html', {
        'viaje': viaje, 
        'asientos_por_piso': asientos_por_piso, 
        'cliente_id': cliente.id if cliente else None,
        'usuario_id': request.user.id if request.user.is_authenticated else None, # 👈 AÑADE ESTA LÍNEA
        'tarifa': tarifa, 
        'tiene_tarifa': tarifa is not None, 
        'seguro': valor_seguro,
        'segundos_restantes': segundos_restantes, 
        'transaccion_reciente': transaccion_reciente,
        'expiracion_iso': expiracion_iso,
    })

# ============================================================
# VISTAS DE AUTENTICACIÓN
# ============================================================
def registro(request):
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
    if request.user.is_authenticated:
        return redirect('core:perfil')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            if '@' in username:
                user_obj = User.objects.filter(email=username).first()
                if user_obj: username = user_obj.username
            user = authenticate(request, username=username, password=password)
            if user is not None:
                exito, mensaje = procesar_login_con_espera(request, user)
                if not exito:
                    messages.warning(request, mensaje)
                    return render(request, 'login.html', {'form': form, 'mostrar_desbloqueo': True, 'username_bloqueado': username})
                
                auth_login(request, user)
                # ⭐ VERIFICAR SI EL EMAIL ESTÁ VERIFICADO
                if getattr(user, 'cliente', None) and not user.cliente.email_verificado:
                    messages.warning(request, "Debes verificar tu correo electrónico antes de continuar.")
                    return redirect('core:verificar_email')
                
                # ⭐ LIMPIEZA DE RESERVAS HUÉRFANAS (Para ambos roles)
                # Si el usuario cerró el navegador, sus asientos quedaron reservados.
                # Al volver a loguearse, los liberamos para que empiece limpio.
                Asiento.objects.filter(
                    estado='reservado',
                    reservado_por=user
                ).update(
                    estado='disponible',
                    reservado_por=None,
                    reservado_hasta=None  # 👈 Limpia la fecha en la DB
                )
                
                # ⭐ LIMPIEZA DE SEÑALES DE TIEMPO EN LA SESIÓN
                # Borramos el punto de partida del reloj y los datos temporales
                request.session.pop('reserva_inicio', None)
                request.session.pop('asientos_seleccionados', None)
                request.session.pop('pasajeros_data', None)
                
                from .models import SesionActiva
                if not (user.is_staff or user.is_superuser) and getattr(user, 'cliente', None):
                    SesionActiva.objects.update_or_create(
                        user=user, 
                        defaults={
                            'session_key': request.session.session_key, 
                            'ip_address': request.META.get('REMOTE_ADDR'), 
                            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:250], 
                            'ultima_actividad': timezone.now()
                        }
                    )
                
                nombre = user.first_name or user.username
                messages.success(request, f"Estimado cliente {nombre}: bienvenido nuevamente. Es un gusto tenerlo de vuelta.")
                
                # ⭐ REDIRECCIÓN INTELIGENTE (BLOQUE ÚNICO)
                next_url = request.POST.get('next') or request.GET.get('next') or ''
                
                # 1. Si es empleado (taquillero), va a la taquilla
                if getattr(user, 'usuarioempresa', None):
                    return redirect('core:taquilla_inicio')
                
                # 2. Si es cliente y viene de /taquilla/, avisarle
                if 'taquilla' in next_url and getattr(user, 'cliente', None):
                    messages.info(
                        request, 
                        "Estimado cliente: el área de taquilla es exclusiva para empleados. "
                        "Lo hemos redirigido a su perfil."
                    )
                    return redirect('core:perfil')
                
                # 3. Cliente normal (o admin)
                return redirect(next_url or 'core:perfil')
            else:
                messages.error(request, "Estimado cliente: los datos ingresados no coinciden con nuestros registros. Por favor, verifique su usuario y contraseña e intente nuevamente.")
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    if request.user.is_authenticated:
        cliente = getattr(request.user, 'cliente', None)
        if cliente:
            with transaction.atomic():
                asientos_reservados = Asiento.objects.select_for_update().filter(estado='reservado', reservado_por=request.user)
                for asiento in asientos_reservados:
                    MovimientoAsiento.objects.create(asiento=asiento, tipo='liberacion_manual', estado_anterior='reservado', estado_nuevo='disponible', usuario=request.user, motivo='El cliente cerró sesión.')
                asientos_reservados.update(estado='disponible', reservado_por=None, reservado_hasta=None)
        from .models import SesionActiva
        SesionActiva.objects.filter(user=request.user).delete()
    request.session.pop('asientos_seleccionados', None)
    request.session.pop('reserva_inicio', None)
    auth_logout(request)
    messages.info(request, "Estimado cliente: su sesión ha finalizado correctamente. Gracias por preferirnos.")
    request.session['logout_reciente'] = True
    response = redirect('core:inicio')
    response.status_code = 303
    return response

@login_required
def perfil(request):
    cliente = getattr(request.user, 'cliente', None)
    total_transacciones = 0; transacciones_activas = 0; total_boletos = 0
    if cliente:
        transacciones = Transaccion.objects.filter(cliente=cliente)
        total_transacciones = transacciones.count()
        transacciones_activas = transacciones.exclude(estado__in=['cancelada', 'rechazada']).count()
        total_boletos = Boleto.objects.filter(transaccion__cliente=cliente).exclude(transaccion__estado__in=['cancelada', 'rechazada']).count()
    return render(request, 'perfil.html', {'cliente': cliente, 'total_transacciones': total_transacciones, 'transacciones_activas': transacciones_activas, 'total_boletos': total_boletos})

# ============================================================
# RESERVAS Y PAGOS WEB
# ============================================================
@require_POST
@login_required
def reservar_asientos(request):
    viaje_id = request.POST.get('viaje_id')
    asientos_ids = request.POST.getlist('asientos[]')
    if not viaje_id or not asientos_ids: return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    max_puestos = int(obtener_parametro('103', default=5))
    if len(asientos_ids) > max_puestos: return JsonResponse({'ok': False, 'error': f'Solo puedes reservar hasta {max_puestos} puestos.'}, status=400)
    cliente = getattr(request.user, 'cliente', None)
    if not cliente: return JsonResponse({'ok': False, 'error': 'Debes completar tu perfil.'}, status=400)
    try:
        with transaction.atomic():
            asientos = Asiento.objects.select_for_update().filter(id__in=asientos_ids, viaje_id=viaje_id, tipo='asiento')
            if asientos.count() != len(asientos_ids): return JsonResponse({'ok': False, 'error': 'Asientos no existen.'}, status=400)
            no_disponibles = [a.numero for a in asientos if a.estado != 'disponible']
            if no_disponibles: return JsonResponse({'ok': False, 'error': f'Los asientos {", ".join(no_disponibles)} ya no están disponibles.'}, status=400)
            minutos = int(obtener_parametro('101', default=10))
            vence = timezone.now() + timedelta(minutes=minutos)
            Asiento.objects.filter(id__in=asientos_ids).update(estado='reservado', reservado_hasta=vence, reservado_por=request.user)
        return JsonResponse({'ok': True, 'vence': vence.isoformat(), 'minutos': minutos, 'cantidad': len(asientos_ids)})
    except Exception as e: return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@require_POST
@login_required
def liberar_asientos(request):
    asientos_ids = request.POST.getlist('asientos[]')
    if not asientos_ids: return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    cliente = getattr(request.user, 'cliente', None)
    if not cliente: return JsonResponse({'ok': False, 'error': 'Sin cliente.'}, status=400)
    try:
        with transaction.atomic():
            asientos = Asiento.objects.select_for_update().filter(id__in=asientos_ids, estado='reservado', reservado_por=request.user)
            for asiento in asientos:
                MovimientoAsiento.objects.create(asiento=asiento, tipo='liberacion_manual', estado_anterior='reservado', estado_nuevo='disponible', usuario=request.user, motivo='El cliente liberó el asiento.')
            asientos.update(estado='disponible', reservado_hasta=None, reservado_por=None)
        asientos_sesion = request.session.get('asientos_seleccionados', [])
        asientos_sesion = [aid for aid in asientos_sesion if str(aid) not in asientos_ids]
        request.session['asientos_seleccionados'] = asientos_sesion
        return JsonResponse({'ok': True, 'cantidad': len(asientos_ids)})
    except Exception as e: return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@login_required
def pasajeros(request, viaje_id):
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
    liberar_reservas_vencidas(viaje=viaje)
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
        except (ValueError, TypeError): segundos_restantes = minutos * 60
    else: segundos_restantes = minutos * 60
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
        messages.error(request, "No hay tarifa configurada para esta ruta. Por favor, selecciona el viaje desde la búsqueda.")
        return redirect('core:inicio')
    valor_seguro = obtener_parametro('100', default=0)
    asientos_sesion = request.session.get('asientos_seleccionados', [])
    if asientos_sesion:
        asientos = Asiento.objects.filter(id__in=asientos_sesion, viaje=viaje, estado='reservado', reservado_por=request.user, reservado_hasta__gt=timezone.now()).order_by('numero')
    else:
        asientos = Asiento.objects.filter(viaje=viaje, estado='reservado', reservado_por=request.user, reservado_hasta__gt=timezone.now()).order_by('numero')
    if not asientos.exists():
        messages.warning(request, "No tienes asientos reservados. Selecciona asientos primero.")
        return redirect('core:detalle_viaje', viaje_id=viaje.id)
    nuevo_vence = timezone.now() + timedelta(minutes=minutos)
    asientos.update(reservado_hasta=nuevo_vence)
    if request.method == 'POST':
        formularios = []
        valido = True
        for asiento in asientos:
            prefix = f"asiento_{asiento.id}"
            form = PasajeroForm(request.POST, prefix=prefix)
            formularios.append((asiento, form))
            if not form.is_valid(): valido = False
        if valido:
            pasajeros_data = []
            for asiento, form in formularios:
                pasajeros_data.append({'asiento_id': asiento.id, 'asiento_numero': asiento.numero, 'nombre': form.cleaned_data['nombre'], 'cedula': form.cleaned_data['cedula'], 'telefono': form.cleaned_data['telefono'], 'tipo_pasajero': form.cleaned_data['tipo_pasajero']})
            request.session['pasajeros_data'] = pasajeros_data
            request.session['viaje_id'] = viaje.id
            return redirect('core:seleccionar_metodo_pago', viaje_id=viaje.id)
    else:
        pasajeros_previos = request.session.get('pasajeros_data', [])
        pasajeros_dict = {p['asiento_id']: p for p in pasajeros_previos}
        formularios = []
        for asiento in asientos:
            prefix = f"asiento_{asiento.id}"
            inicial = {}
            if asiento.id in pasajeros_dict:
                p = pasajeros_dict[asiento.id]
                inicial = {'nombre': p.get('nombre', ''), 'cedula': p.get('cedula', ''), 'telefono': p.get('telefono', ''), 'tipo_pasajero': p.get('tipo_pasajero', 'normal')}
            form = PasajeroForm(prefix=prefix, initial=inicial)
            formularios.append((asiento, form))
    cantidad = asientos.count()
    precio_unitario = (tarifa.monto_usd + valor_seguro) if tarifa else 0
    total_usd = precio_unitario * cantidad
    expiracion_iso = (timezone.now() + timedelta(seconds=segundos_restantes)).isoformat()
    return render(request, 'pasajeros.html', {'viaje': viaje, 'formularios': formularios, 'cantidad': cantidad, 'total_usd': total_usd, 'tarifa': tarifa, 'seguro': valor_seguro, 'segundos_restantes': segundos_restantes, 'expiracion_iso': expiracion_iso, 'minutos_reserva': minutos})

@login_required
def pago(request, viaje_id):
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
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
        messages.error(request, "No hay tarifa configurada. No se puede procesar la compra.")
        return redirect('core:inicio')
    valor_seguro = obtener_parametro('100', default=0)
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
    pasajeros_data = request.session.get('pasajeros_data', [])
    if not pasajeros_data:
        messages.warning(request, "No hay datos de pasajeros. Completa el formulario primero.")
        return redirect('core:pasajeros', viaje_id=viaje.id)
    asientos_ids = [p['asiento_id'] for p in pasajeros_data]
    asientos = Asiento.objects.filter(id__in=asientos_ids, viaje=viaje, estado='reservado', reservado_por=request.user)
    if asientos.count() != len(asientos_ids):
        messages.warning(request, "Algunos asientos ya no están disponibles. Selecciona de nuevo.")
        return redirect('core:detalle_viaje', viaje_id=viaje.id)
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
        except (ValueError, TypeError): segundos_restantes = minutos * 60
    else: segundos_restantes = minutos * 60
    vence = timezone.now() + timedelta(minutes=minutos)
    asientos.update(reservado_hasta=vence)
    cantidad = len(pasajeros_data)
    precio_unitario = tarifa.monto_usd + valor_seguro if tarifa else 0
    total_usd = precio_unitario * cantidad
    tasa_bcv = obtener_parametro('107', default=0)
    total_bs = (total_usd * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0
    datos_cuenta = {'banco': obtener_parametro('120', default=''), 'telefono': obtener_parametro('121', default=''), 'cedula': obtener_parametro('122', default=''), 'cuenta': obtener_parametro('123', default=''), 'titular': obtener_parametro('124', default='')}
    if request.method == 'POST':
        datos_post = request.POST.copy()
        monto_str = datos_post.get('monto_pagado_bs', '')
        if monto_str: datos_post['monto_pagado_bs'] = monto_str.replace('.', '').replace(',', '.')
        form = PagoWebForm(datos_post, request.FILES)
        if form.is_valid():
            monto_pagado = form.cleaned_data['monto_pagado_bs']
            diferencia = monto_pagado - total_bs
            monto_faltante = abs(diferencia) if diferencia < 0 else Decimal('0')
            monto_excedente = diferencia if diferencia > Decimal('0.01') else Decimal('0')
            confirmar = request.POST.get('confirmar_diferencia')
            if (abs(diferencia) > Decimal('0.01')) and not confirmar:
                return render(request, 'pago.html', {'viaje': viaje, 'form': form, 'cantidad': cantidad, 'total_usd': total_usd, 'total_bs': total_bs, 'tasa_bcv': tasa_bcv, 'datos_cuenta': datos_cuenta, 'minutos_reserva': minutos, 'tarifa': tarifa, 'monto_pagado': monto_pagado, 'diferencia': diferencia, 'monto_faltante': monto_faltante, 'monto_excedente': monto_excedente, 'mostrar_aviso': True})
            codigo = generar_codigo_transaccion()        
            with transaction.atomic():
                transaccion = Transaccion.objects.create(codigo=codigo, cliente=cliente, viaje=viaje, cantidad_boletos=cantidad, monto_total_usd=total_usd, monto_total_bs=total_bs, tasa_bcv=tasa_bcv, estado='pendiente_verificacion', vendido_por=None, dispositivo_venta=request.META.get('HTTP_USER_AGENT', 'Desconocido'), oficina_destino=viaje.ruta.destinos.first())
                observacion = ''
                if abs(diferencia) > Decimal('0.01'): observacion = f"Diferencia de monto: pagó Bs. {monto_pagado}, esperado Bs. {total_bs}. Diferencia: Bs. {diferencia:,.2f}"
                Pago.objects.create(transaccion=transaccion, metodo=form.cleaned_data['metodo'], monto_usd=total_usd, monto_bs=monto_pagado, tasa_bcv=tasa_bcv, banco_origen=form.cleaned_data['banco_origen'], telefono_origen=form.cleaned_data['telefono_origen'], cedula_origen=form.cleaned_data['cedula_origen'], referencia=form.cleaned_data['referencia'], comprobante=form.cleaned_data['comprobante'], estado='pendiente', observacion=observacion)
                horas_verificacion = int(obtener_parametro('141', default=72))
                vence_verificacion = timezone.now() + timedelta(hours=horas_verificacion)
                for p in pasajeros_data:
                    asiento = Asiento.objects.select_for_update().get(id=p['asiento_id'])
                    asiento.estado = 'pendiente_verificacion'
                    asiento.reservado_hasta = vence_verificacion
                    # ~ asiento.reservado_por = cliente
                    asiento.reservado_por = request.user
                    asiento.save()
                    monto_tarifa = tarifa.monto_usd if tarifa else 0
                    monto_seguro = valor_seguro if tarifa else 0
                    monto_total_boleto = monto_tarifa + monto_seguro
                    Boleto.objects.create(transaccion=transaccion, viaje=viaje, asiento=asiento, pasajero_cedula=p['cedula'], pasajero_nombre=p['nombre'], pasajero_telefono=p.get('telefono', ''), tipo_pasajero=p['tipo_pasajero'], monto_tarifa_usd=monto_tarifa, monto_seguro_usd=monto_seguro, monto_total_usd=monto_total_boleto, tasa_bcv=tasa_bcv, monto_total_bs=(monto_total_boleto * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0, codigo_qr=generar_codigo_qr(), estado='pendiente_verificacion')
            request.session.pop('pasajeros_data', None)
            request.session.pop('viaje_id', None)
            request.session.pop('asientos_seleccionados', None)
            messages.success(request, "¡Pago registrado! Tu compra está pendiente de verificación.")
            return redirect('core:confirmacion', transaccion_id=transaccion.id)
    else:
        metodo_inicial = request.GET.get('metodo', 'pago_movil')
        form = PagoWebForm(initial={'metodo': metodo_inicial})
    return render(request, 'pago.html', {'viaje': viaje, 'form': form, 'cantidad': cantidad, 'tarifa': tarifa, 'seguro': valor_seguro, 'segundos_restantes': segundos_restantes, 'total_usd': total_usd, 'total_bs': total_bs, 'tasa_bcv': tasa_bcv, 'datos_cuenta': datos_cuenta, 'minutos_reserva': minutos})

@login_required
def confirmacion(request, transaccion_id):
    transaccion = get_object_or_404(Transaccion, id=transaccion_id)
    cliente = getattr(request.user, 'cliente', None)
    if not cliente or transaccion.cliente != cliente:
        messages.error(request, "No tienes acceso a esta transacción.")
        return redirect('core:inicio')
    boletos = transaccion.boletos.all().order_by('asiento__numero')
    pago_obj = transaccion.pagos.first()
    return render(request, 'confirmacion.html', {'transaccion': transaccion, 'boletos': boletos, 'pago': pago_obj})

# ============================================================
# SELECCIÓN DE MÉTODO DE PAGO Y PASARELA
# ============================================================
@login_required
def seleccionar_metodo_pago(request, viaje_id):
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
    pasajeros_data = request.session.get('pasajeros_data', [])
    if not pasajeros_data:
        messages.warning(request, "No hay datos de pasajeros. Completa el formulario primero.")
        return redirect('core:pasajeros', viaje_id=viaje.id)
    permite_pago_movil = obtener_parametro('131', default=True)
    permite_transferencia = obtener_parametro('130', default=False)
    permite_pasarela = obtener_parametro('132', default=True)
    metodos = []
    if permite_pago_movil: metodos.append({'id': 'pago_movil', 'nombre': 'Pago Móvil', 'icono': 'bi-phone-fill', 'descripcion': 'Paga desde tu banco con tu teléfono en segundos.', 'url': f'/viajes/{viaje.id}/pago/?metodo=pago_movil'})
    if permite_transferencia: metodos.append({'id': 'transferencia', 'nombre': 'Transferencia Bancaria', 'icono': 'bi-bank2', 'descripcion': 'Transfiere desde tu banca en línea o taquilla.', 'url': f'/viajes/{viaje.id}/pago/?metodo=transferencia'})
    if permite_pasarela: metodos.append({'id': 'pasarela', 'nombre': 'Pasarela Digital', 'icono': 'bi-credit-card-fill', 'descripcion': 'Paga con tarjeta de crédito/débito de forma segura.', 'url': f'/viajes/{viaje.id}/pasarela-virtual/'})
    if not metodos:
        messages.error(request, "No hay métodos de pago habilitados. Contacta a la empresa.")
        return redirect('core:inicio')
    from_cancelar = request.GET.get('from') == 'cancelar'
    if len(metodos) == 1 and not from_cancelar: return redirect(metodos[0]['url'])
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
    return render(request, 'seleccionar_metodo_pago.html', {'viaje': viaje, 'metodos': metodos, 'cantidad': cantidad, 'total_usd': total_usd, 'total_bs': total_bs, 'tasa_bcv': tasa_bcv, 'mostrar_cancelar': from_cancelar})

@login_required
def pasarela_virtual_view(request, viaje_id):
    viaje = get_object_or_404(Viaje, id=viaje_id)
    cliente = getattr(request.user, 'cliente', None)
    permite_pasarela = obtener_parametro('132', default=True)
    if not permite_pasarela:
        messages.error(request, "La pasarela digital no está habilitada. Elige otro método de pago.")
        return redirect('core:seleccionar_metodo_pago', viaje_id=viaje.id)
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de comprar.")
        return redirect('core:perfil')
    pasajeros_data = request.session.get('pasajeros_data', [])
    if not pasajeros_data:
        messages.warning(request, "No hay datos de pasajeros. Completa el formulario primero.")
        return redirect('core:pasajeros', viaje_id=viaje.id)
    asientos_ids = [p['asiento_id'] for p in pasajeros_data]
    asientos = Asiento.objects.filter(id__in=asientos_ids, viaje=viaje, estado='reservado', reservado_por=request.user)
    if asientos.count() != len(asientos_ids):
        messages.warning(request, "Algunos asientos ya no están disponibles.")
        return redirect('core:detalle_viaje', viaje_id=viaje.id)
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
        messages.error(request, "No hay tarifa configurada. No se puede procesar la compra.")
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
                transaccion = Transaccion.objects.create(codigo=codigo, cliente=cliente, viaje=viaje, cantidad_boletos=cantidad, monto_total_usd=total_usd, monto_total_bs=total_bs, tasa_bcv=tasa_bcv, estado='confirmada', fecha_confirmacion=timezone.now(), vendido_por=None, dispositivo_venta=request.META.get('HTTP_USER_AGENT', 'Desconocido'), oficina_destino=viaje.ruta.destinos.first())
                Pago.objects.create(transaccion=transaccion, metodo='pasarela_digital', monto_usd=total_usd, monto_bs=total_bs, tasa_bcv=tasa_bcv, referencia='PASS-' + codigo, estado='aprobado', observacion="Pago procesado exitosamente mediante Pasarela Digital segura.")
                for p in pasajeros_data:
                    asiento = Asiento.objects.select_for_update().get(id=p['asiento_id'])
                    asiento.estado = 'vendido'
                    asiento.reservado_hasta = None
                    asiento.reservado_por = None
                    asiento.save()
                    monto_tarifa = tarifa.monto_usd if tarifa else 0
                    monto_seguro = valor_seguro if tarifa else 0
                    monto_total_boleto = monto_tarifa + monto_seguro
                    Boleto.objects.create(transaccion=transaccion, viaje=viaje, asiento=asiento, pasajero_cedula=p['cedula'], pasajero_nombre=p['nombre'], pasajero_telefono=p.get('telefono', ''), tipo_pasajero=p['tipo_pasajero'], monto_tarifa_usd=monto_tarifa, monto_seguro_usd=monto_seguro, monto_total_usd=monto_total_boleto, tasa_bcv=tasa_bcv, monto_total_bs=(monto_total_boleto * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0, codigo_qr=generar_codigo_qr(), estado='vendido')
            request.session.pop('pasajeros_data', None)
            request.session.pop('asientos_seleccionados', None)
            messages.success(request, "¡Compra registrada exitosamente!")
            return redirect('core:confirmacion', transaccion_id=transaccion.id)
    else:
        form = PasarelaVirtualForm()
    return render(request, 'pasarela_virtual.html', {'form': form, 'viaje': viaje, 'cantidad': cantidad, 'total_usd': total_usd, 'total_bs': total_bs, 'tasa_bcv': tasa_bcv})

# ============================================================
# VISTAS DE UTILIDAD
# ============================================================
def mi_vista_error_csrf(request, reason=""):
    from django.http import JsonResponse
    if (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept', '').startswith('application/json')):
        return JsonResponse({'ok': False, 'error': 'Sesión expirada. Recarga la página e intenta de nuevo.', 'csrf_failed': True}, status=403)
    messages.warning(request, "Tu sesión de seguridad expiró. Por favor, intenta de nuevo.")
    if request.path.startswith('/login/'): return redirect('core:login')
    if request.path.startswith('/registro/'): return redirect('core:registro')
    return redirect('core:inicio')

@login_required
def mis_boletos(request):
    cliente = getattr(request.user, 'cliente', None)
    if not cliente:
        messages.error(request, "Debes completar tu perfil antes de ver tus boletos.")
        return redirect('core:perfil')
    transacciones = Transaccion.objects.filter(cliente=cliente).order_by('-fecha_creacion')
    transacciones_con_boletos = []
    for t in transacciones:
        boletos = t.boletos.all().order_by('asiento__numero')
        transacciones_con_boletos.append({'transaccion': t, 'boletos': boletos, 'cantidad': boletos.count()})
    return render(request, 'mis_boletos.html', {'cliente': cliente, 'transacciones_con_boletos': transacciones_con_boletos})

def session_check(request):
    from django.http import JsonResponse
    return JsonResponse({'authenticated': request.user.is_authenticated}, status=200 if request.user.is_authenticated else 401)

def ayuda(request):
    from .models import Parametro
    def ptexto(codigo, default=''):
        try:
            p = Parametro.objects.get(codigo=codigo, activo=True)
            return p.valor_texto or default
        except Parametro.DoesNotExist:
            return default
    contexto = {'empresa_nombre': ptexto(1, 'Viba-Web'), 'empresa_rif': ptexto(2, ''), 'empresa_direccion': ptexto(3, ''), 'empresa_telefono': ptexto(4, ''), 'empresa_email': ptexto(5, ''), 'banco_empresa': ptexto(120, ''), 'telefono_pago_movil': ptexto(121, ''), 'cedula_pago_movil': ptexto(122, ''), 'cuenta_bancaria': ptexto(123, ''), 'titular_cuenta': ptexto(124, '')}
    return render(request, 'ayuda.html', contexto)

# ============================================================
# VISTAS DE TAQUILLA (EMPLEADOS)
# ============================================================
def taquilla_inicio(request):
    # ⭐ Liberar asientos vencidos (igual que el cliente web)
    from .utils import liberar_reservas_vencidas
    viajes_con_reservas = Viaje.objects.filter(
        asientos__estado='reservado',
        asientos__reservado_hasta__lt=timezone.now()
    ).distinct()
    for viaje in viajes_con_reservas:
        liberar_reservas_vencidas(viaje=viaje)

    # Resetear el tiempo de reserva al volver al inicio
    request.session.pop('reserva_inicio', None)
    if not request.user.is_authenticated:
        return redirect('core:login')
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos para acceder a la taquilla.")
        return redirect('core:inicio')

    # 1. Por defecto, el origen es la oficina del taquillero
    origen_id = request.GET.get('origen', empleado.oficina.id)
    destino_id = request.GET.get('destino')
    fecha_str = request.GET.get('fecha')
    
    viajes_con_info = []
    tasa_bcv = obtener_parametro('107', default=0)
    oficinas = Oficina.objects.filter(activa=True).order_by('nombre')
    
    if destino_id and fecha_str and origen_id:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            oficina_origen = Oficina.objects.get(id=origen_id)
            
            hoy = timezone.localtime(timezone.now()).date()
            ahora = timezone.localtime(timezone.now()).time()

            viajes_del_dia = Viaje.objects.filter(
                fecha=fecha, estado='programado', cerrado_venta=False
            ).select_related('ruta', 'bus')

            # ⭐ FILTRO POR HORA: si es hoy, solo mostrar viajes que aún no han salido
            if fecha == hoy:
                viajes_del_dia = viajes_del_dia.filter(hora__gt=ahora)

            for viaje in viajes_del_dia:
                pasa_por_origen = viaje.ruta.paradas.filter(oficina=oficina_origen).exists()
                pasa_por_destino = viaje.ruta.paradas.filter(oficina_id=destino_id).exists()
                
                if pasa_por_origen and pasa_por_destino:
                    # Buscar la tarifa exacta para ese tramo
                    tarifa = Tarifa.objects.filter(origen=oficina_origen, destino_id=destino_id, activa=True).first()
                    disponibles = viaje.asientos.filter(estado='disponible').count()
                    
                    viajes_con_info.append({
                        'viaje': viaje, 'tarifa': tarifa,
                        'precio_usd': tarifa.monto_usd if tarifa else 0,
                        'precio_bs': (tarifa.monto_usd * tasa_bcv) if tarifa and tasa_bcv else 0,
                        'disponibles': disponibles
                    })
        except ValueError:
            messages.error(request, "Formato de fecha inválido.")

    return render(request, 'taquilla/inicio.html', {
        'empleado': empleado, 'oficinas': oficinas,
        'viajes_con_info': viajes_con_info,
        'origen_seleccionado': int(origen_id) if origen_id else None,
        'destino_seleccionado': int(destino_id) if destino_id else None,
        'fecha_seleccionada': fecha_str, 'tasa_bcv': tasa_bcv,
    })

def taquilla_mapa(request, viaje_id):
    """Muestra el mapa de asientos para el taquillero usando el template del cliente."""
    if not request.user.is_authenticated:
        return redirect('core:login')

    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos para acceder a la taquilla.")
        return redirect('core:inicio')

    viaje = get_object_or_404(Viaje, id=viaje_id)
    
    # ⭐ CONTROL DEL TIEMPO Y PROTECCIÓN AL REGRESAR
    minutos_reserva = int(obtener_parametro('171', default=5))
    reserva_inicio_str = request.session.get('reserva_inicio')
    
    if not reserva_inicio_str:
        reserva_inicio = timezone.now()
        request.session['reserva_inicio'] = reserva_inicio.isoformat()
    else:
        try:
            reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
        except (ValueError, TypeError):
            reserva_inicio = timezone.now()
            request.session['reserva_inicio'] = reserva_inicio.isoformat()

    expira_en = reserva_inicio + timedelta(minutes=minutos_reserva)
    tiempo_actual = timezone.now()

    if tiempo_actual > expira_en:
        Asiento.objects.filter(estado='reservado', reservado_por=request.user).update(
            estado='disponible', reservado_por=None, reservado_hasta=None
        )
        request.session.pop('reserva_inicio', None)
        messages.warning(request, "Tu tiempo de reserva ha expirado. Selecciona de nuevo.")
        return redirect('core:taquilla_inicio')

    # ⭐ Refrescamos el tiempo en la base de datos para los asientos del taquillero actual
    Asiento.objects.filter(
        viaje=viaje,
        estado='reservado',
        reservado_por=request.user
    ).update(reservado_hasta=expira_en)

    # Limpiamos únicamente las reservas vencidas de otros usuarios
    liberar_reservas_vencidas(viaje=viaje)

    origen_id = request.GET.get('origen', empleado.oficina.id)
    destino_id = request.GET.get('destino')
    
    if not destino_id:
        messages.error(request, "No se seleccionó un destino.")
        return redirect('core:taquilla_inicio')

    parada_origen = viaje.ruta.paradas.filter(oficina_id=origen_id).first()
    parada_destino = viaje.ruta.paradas.filter(oficina_id=destino_id).first()

    if not parada_origen or not parada_destino:
        messages.error(request, "Ruta no válida para este tramo.")
        return redirect('core:taquilla_inicio')

    tarifa = Tarifa.objects.filter(origen_id=origen_id, destino_id=destino_id, activa=True).first()
    tasa_bcv = obtener_parametro('107', default=0)
    valor_seguro = obtener_parametro('100', default=0)

    asientos = viaje.asientos.order_by('piso', 'fila', 'columna')
    asientos_por_piso = {}
    for asiento in asientos:
        if asiento.tipo == 'asiento':
            disponible_para_tramo = asiento_esta_disponible_en_tramo(asiento.id, viaje.id, parada_origen.orden, parada_destino.orden)
        else:
            disponible_para_tramo = False
            
        if asiento.estado in ['reservado', 'bloqueado'] and asiento.reservado_por != request.user:
            disponible_para_tramo = False

        asiento.estado_real = asiento.estado
        asiento.disponible_para_tramo = disponible_para_tramo

        piso = asiento.piso
        if piso not in asientos_por_piso: asientos_por_piso[piso] = {}
        fila = asiento.fila
        if fila not in asientos_por_piso[piso]: asientos_por_piso[piso][fila] = []
        asientos_por_piso[piso][fila].append(asiento)

    if len(asientos_por_piso) > 1:
        asientos_por_piso = dict(reversed(list(asientos_por_piso.items())))

    expiracion_iso = expira_en.isoformat()
    segundos_restantes = max(0, int((expira_en - tiempo_actual).total_seconds()))

    return render(request, 'detalle_viaje.html', {
        'viaje': viaje,
        'asientos_por_piso': asientos_por_piso,
        'cliente_id': request.user.id,
        'usuario_id': request.user.id,  # ⭐ Asegura que se envíe el ID del usuario taquillero
        'tarifa': tarifa,
        'tiene_tarifa': True,
        'seguro': valor_seguro,
        'segundos_restantes': segundos_restantes,
        'transaccion_reciente': None,
        'origen_id': origen_id,
        'destino_id': destino_id,
        'expiracion_iso': expiracion_iso,
    })
    
def taquilla_cobrar(request, viaje_id):
    if not request.user.is_authenticated:
        return redirect('core:login')
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos para acceder a la taquilla.")
        return redirect('core:inicio')

    viaje = get_object_or_404(Viaje, id=viaje_id)
    destino_id = request.GET.get('destino') or request.POST.get('destino')
    origen_id = request.GET.get('origen') or request.POST.get('origen') or empleado.oficina.id
    
    if not destino_id:
        messages.error(request, "No se seleccionó un destino.")
        return redirect('core:taquilla_inicio')

    parada_origen = viaje.ruta.paradas.filter(oficina_id=origen_id).first()
    parada_destino = viaje.ruta.paradas.filter(oficina_id=destino_id).first()
    
    tarifa = Tarifa.objects.filter(origen_id=origen_id, destino_id=destino_id, activa=True).first()
    tasa_bcv = obtener_parametro('107', default=0)
    valor_seguro = obtener_parametro('100', default=0)
    
    descuento_preferencial = obtener_parametro('174', default=50)
    cobrar_seguro_cortesia = obtener_parametro('175', default=True)
    intervalo_renovacion = int(obtener_parametro('114', default=20))

    if not tarifa:
        messages.error(request, "No hay tarifa configurada para este tramo.")
        return redirect('core:taquilla_inicio')

    # ⭐ CONTROL DEL TIEMPO (Sincronizado y Persistente)
    minutos_reserva = int(obtener_parametro('171', default=5))
    reserva_inicio_str = request.session.get('reserva_inicio')
    
    if not reserva_inicio_str:
        # Si es la primera vez, creamos el punto de partida
        reserva_inicio = timezone.now()
        request.session['reserva_inicio'] = reserva_inicio.isoformat()
    else:
        try:
            reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
        except (ValueError, TypeError):
            reserva_inicio = timezone.now()
            request.session['reserva_inicio'] = reserva_inicio.isoformat()

    # Calculamos la hora exacta de expiración
    expira_en = reserva_inicio + timedelta(minutes=minutos_reserva)
    tiempo_actual = timezone.now()

    if tiempo_actual > expira_en:
        # Si expiró, liberar asientos y redirigir
        Asiento.objects.filter(estado='reservado', reservado_por=request.user).update(
            estado='disponible', reservado_por=None, reservado_hasta=None
        )
        request.session.pop('reserva_inicio', None)
        messages.warning(request, "Tu tiempo de reserva ha expirado. Selecciona de nuevo.")
        return redirect('core:taquilla_inicio')

    # Variables que van al HTML
    expiracion_iso = expira_en.isoformat()
    segundos_restantes = max(0, int((expira_en - tiempo_actual).total_seconds()))

    liberar_reservas_vencidas(viaje=viaje)

    asientos_ids = request.GET.getlist('asientos[]')
    asientos_seleccionados = list(Asiento.objects.filter(id__in=asientos_ids).values_list('numero', flat=True).order_by('numero'))
    cantidad = len(asientos_ids)

    asientos_con_datos = []
    for asiento_id in asientos_ids:
        asiento = Asiento.objects.filter(id=asiento_id).first()
        if asiento:
            asientos_con_datos.append({
                'id': asiento.id,
                'numero': asiento.numero,
                'lado': asiento.get_lado_display() if hasattr(asiento, 'get_lado_display') else '',
            })

    precio_unitario = tarifa.monto_usd + valor_seguro
    total_usd = precio_unitario * cantidad
    total_bs = (total_usd * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0

    if request.method == 'POST':
        import json
        asientos_ids = request.POST.getlist('asientos[]')
        pagos_json = request.POST.get('pagos_json', '[]')

        if not asientos_ids:
            messages.error(request, "No hay asientos seleccionados.")
            return redirect('core:taquilla_mapa', viaje_id=viaje.id)

        boletos_creados = []
        total_venta_usd = Decimal('0.00')
        total_venta_bs = Decimal('0.00')

        for asiento_id in asientos_ids:
            cedula = request.POST.get(f'cedula_{asiento_id}')
            nombre = request.POST.get(f'nombre_{asiento_id}')
            telefono = request.POST.get(f'telefono_{asiento_id}', '')
            tipo = request.POST.get(f'tipo_pasajero_{asiento_id}', 'normal')

            if not cedula or not nombre:
                messages.error(request, f"Faltan datos para el asiento {asiento_id}.")
                return redirect(f"/taquilla/viaje/{viaje.id}/cobrar/?destino={destino_id}&origen={origen_id}&" + "&".join([f"asientos[]={aid}" for aid in asientos_ids]))

            if tipo == 'cortesia':
                precio_final = Decimal('0.00')
                seguro_final = valor_seguro if cobrar_seguro_cortesia else Decimal('0.00')
            elif tipo in ['tercera_edad', 'discapacitado']:
                precio_final = tarifa.monto_usd * (1 - (Decimal(descuento_preferencial) / 100))
                seguro_final = valor_seguro
            else:
                precio_final = tarifa.monto_usd
                seguro_final = valor_seguro

            total_unitario = precio_final + seguro_final
            total_venta_usd += total_unitario
            total_venta_bs += (total_unitario * tasa_bcv) if tasa_bcv else Decimal('0.00')

            boletos_creados.append({
                'asiento_id': asiento_id, 'cedula': cedula, 'nombre': nombre,
                'telefono': telefono, 'tipo': tipo, 'precio': precio_final,
                'seguro': seguro_final, 'total': total_unitario,
            })

        try:
            pagos_lista = json.loads(pagos_json)
        except json.JSONDecodeError:
            pagos_lista = []

        if not pagos_lista:
            messages.error(request, "Debe registrar al menos un pago.")
            return redirect(f"/taquilla/viaje/{viaje.id}/cobrar/?destino={destino_id}&origen={origen_id}&" + "&".join([f"asientos[]={aid}" for aid in asientos_ids]))

        total_pagado = sum(float(p['monto_usd']) for p in pagos_lista)
        if abs(total_pagado - float(total_venta_usd)) > 0.01:
            messages.error(request, f"El total pagado (${total_pagado:.2f}) no coincide con el total a cobrar (${total_venta_usd:.2f}).")
            return redirect(f"/taquilla/viaje/{viaje.id}/cobrar/?destino={destino_id}&origen={origen_id}&" + "&".join([f"asientos[]={aid}" for aid in asientos_ids]))

        try:
            with transaction.atomic():
                codigo = generar_codigo_transaccion()
                transaccion = Transaccion.objects.create(
                    codigo=codigo, cliente=None, viaje=viaje, cantidad_boletos=len(boletos_creados),
                    monto_total_usd=total_venta_usd, monto_total_bs=total_venta_bs, tasa_bcv=tasa_bcv,
                    estado='confirmada', fecha_confirmacion=timezone.now(),
                    vendido_por=request.user, oficina_venta=empleado.oficina,
                    oficina_destino=parada_destino.oficina, dispositivo_venta='Taquilla',
                )

                for p in pagos_lista:
                    Pago.objects.create(
                        transaccion=transaccion, metodo=p['metodo'],
                        monto_usd=Decimal(p['monto_usd']), monto_bs=Decimal(p['monto_bs']),
                        tasa_bcv=tasa_bcv, referencia=p.get('referencia', ''),
                        estado='confirmado', confirmado_por=request.user, fecha_confirmacion=timezone.now()
                    )

                for b in boletos_creados:
                    asiento = Asiento.objects.select_for_update().get(id=b['asiento_id'], viaje=viaje)
                    asiento.estado = 'vendido'
                    asiento.reservado_hasta = None
                    asiento.reservado_por = None
                    asiento.save()

                    Boleto.objects.create(
                        transaccion=transaccion, viaje=viaje, asiento=asiento,
                        pasajero_cedula=b['cedula'], pasajero_nombre=b['nombre'], pasajero_telefono=b['telefono'],
                        tipo_pasajero=b['tipo'], monto_tarifa_usd=b['precio'], monto_seguro_usd=b['seguro'],
                        monto_total_usd=b['total'], tasa_bcv=tasa_bcv,
                        monto_total_bs=(b['total'] * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0,
                        codigo_qr=generar_codigo_qr(), estado='vendido', vendido_por=request.user
                    )

            request.session.pop('reserva_inicio', None)
            messages.success(request, f"¡Venta exitosa! Código: {codigo}")
            return redirect('core:taquilla_inicio')

        except Exception as e:
            messages.error(request, f"Error al procesar la venta: {str(e)}")
            return redirect('core:taquilla_mapa', viaje_id=viaje.id)

    return render(request, 'taquilla/cobrar.html', {
        'empleado': empleado, 'viaje': viaje, 'parada_origen': parada_origen,
        'parada_destino': parada_destino, 'tarifa': tarifa, 'tasa_bcv': tasa_bcv,
        'valor_seguro': valor_seguro, 'destino_id': destino_id, 'origen_id': origen_id,
        'asientos_seleccionados': asientos_seleccionados, 'asientos_ids': asientos_ids,
        'asientos_con_datos': asientos_con_datos, 'total_usd': total_usd, 'total_bs': total_bs,
        'intervalo_renovacion': intervalo_renovacion, 'descuento_preferencial': descuento_preferencial,
        'cobrar_seguro_cortesia': cobrar_seguro_cortesia,
        'expiracion_iso': expiracion_iso, 'segundos_restantes': segundos_restantes, 'minutos_reserva': minutos_reserva,
    })

@login_required
def taquilla_buscar_pasajero(request):
    cedula = request.GET.get('cedula', '')
    if not cedula:
        return JsonResponse({'encontrado': False})
    
    cliente = Cliente.objects.filter(cedula__iexact=cedula).first()
    if cliente:
        return JsonResponse({
            'encontrado': True,
            'nombre': cliente.user.get_full_name() or cliente.user.username,
            'telefono': cliente.telefono
        })
    return JsonResponse({'encontrado': False})
    
import random
from django.core.mail import send_mail
from django.conf import settings

def registro_usuario(request):
    if request.user.is_authenticated:
        return redirect('core:inicio')
    
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            password = form.cleaned_data['password1']
            cedula = form.cleaned_data['cedula']
            telefono = form.cleaned_data['telefono']
            
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name
            )
            
            # Generar código de verificación
            codigo = str(random.randint(100000, 999999))
            cliente = Cliente.objects.create(
                user=user, cedula=cedula, telefono=telefono,
                codigo_verificacion=codigo,
                fecha_expiracion_codigo=timezone.now() + timedelta(hours=24)
            )
            
            # Guardamos el ID en la sesión temporalmente
            request.session['verificacion_user_id'] = user.id
            
            # HTML del correo con el número grande profesional
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
                <h2 style="color: #003366; text-align: center;">Viba-Web</h2>
                <p>Hola <strong>{first_name}</strong>,</p>
                <p>Tu código de verificación para activar tu cuenta es:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <span style="font-size: 36px; font-weight: bold; color: #003366; background-color: #f4f6f8; padding: 12px 24px; border-radius: 6px; letter-spacing: 6px; border: 1px dashed #003366;">
                        {codigo}
                    </span>
                </div>
                <p>Ingresa este código en la plataforma para completar tu registro.</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 12px; text-align: center;">Este es un mensaje automático, por favor no lo respondas.<br>Viba-Web</p>
            </div>
            """

            # ========================================================
            # 📌 AQUÍ ES EXACTAMENTE A ESTE NIVEL DE ALTURA:
            # ========================================================
            try:
                send_mail(
                    subject='Verifica tu cuenta - Viba-Web',
                    message=f'Hola {first_name},\n\nTu código de verificación es: {codigo}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    html_message=html_content,
                    fail_silently=False,
                )
            except Exception as e:
                messages.warning(request, f"Cuenta creada, pero hubo un detalle al enviar el correo: {str(e)}")
            
            messages.success(request, f"¡Registro exitoso, {first_name}! Te hemos enviado un código de verificación a tu correo.")
            return redirect('core:verificar_email')
    else:
        form = RegistroForm()
        
    return render(request, 'registro.html', {'form': form})
    
@require_POST
@login_required
def reservar_temporal(request):
    """Bloquea un asiento temporalmente usando el Reloj Único de Sesión."""
    viaje_id = request.POST.get('viaje_id')
    asiento_id = request.POST.get('asiento_id')
    
    if not viaje_id or not asiento_id:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    empleado = getattr(request.user, 'usuarioempresa', None)
    
    if not cliente and not empleado:
        return JsonResponse({'ok': False, 'error': 'Usuario no autorizado.'}, status=400)
    
    # ⭐ RELOJ ÚNICO: Usamos el tiempo de sesión (101 web / 171 taquilla)
    if empleado:
        minutos = float(obtener_parametro('171', default=5))
    else:
        minutos = float(obtener_parametro('101', default=10))
    
    vence = timezone.now() + timedelta(minutes=minutos)
    
    try:
        with transaction.atomic():
            asiento = Asiento.objects.select_for_update().get(id=asiento_id, viaje_id=viaje_id)
            
            if asiento.tipo != 'asiento':
                return JsonResponse({'ok': False, 'error': 'Esta posición no es un asiento.'}, status=400)
            
            if asiento.estado == 'reservado' and asiento.reservado_por == request.user:
                asiento.reservado_hasta = vence
                asiento.save()
                return JsonResponse({'ok': True, 'vence': vence.isoformat()})
                
            max_puestos = int(obtener_parametro('103', default=5))
            asientos_actuales = Asiento.objects.filter(
                viaje_id=viaje_id, estado='reservado', reservado_por=request.user, reservado_hasta__gt=timezone.now()
            ).count()
            
            if asientos_actuales >= max_puestos:
                return JsonResponse({'ok': False, 'error': f'Ya tienes {asientos_actuales} asientos reservados. El máximo es {max_puestos}.'}, status=400)
            
            if asiento.estado != 'disponible':
                return JsonResponse({'ok': False, 'error': f'El puesto {asiento.numero} ya no está disponible.'}, status=400)
            
            asiento.estado = 'reservado'
            asiento.reservado_hasta = vence
            asiento.reservado_por = request.user
            asiento.save()
            
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
    """Renueva el bloqueo temporal usando el Reloj Único de Sesión."""
    viaje_id = request.POST.get('viaje_id')
    asientos_ids = request.POST.getlist('asientos[]')
    
    if not viaje_id or not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    empleado = getattr(request.user, 'usuarioempresa', None)
    
    if not cliente and not empleado:
        return JsonResponse({'ok': False, 'error': 'Usuario no autorizado.'}, status=400)
    
    # ⭐ RELOJ ÚNICO: Usamos el tiempo de sesión (101 web / 171 taquilla)
    if empleado:
        minutos = int(obtener_parametro('171', default=5))
    else:
        minutos = int(obtener_parametro('101', default=10))
    
    vence = timezone.now() + timedelta(minutes=minutos)
    
    try:
        with transaction.atomic():
            Asiento.objects.select_for_update().filter(
                id__in=asientos_ids, viaje_id=viaje_id, estado='reservado', reservado_por=request.user
            ).update(reservado_hasta=vence)
        
        return JsonResponse({'ok': True, 'vence': vence.isoformat()})
    
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
        
@require_POST
def heartbeat(request):
    """Recibe el latido del navegador para saber que el usuario sigue activo."""
    if request.user.is_authenticated:
        # Actualizamos la última actividad en la sesión
        request.session['ultima_actividad_heartbeat'] = timezone.now().isoformat()
        request.session.modified = True
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=401)
        
def buscar_viajes(request):
    origen_id = request.GET.get('origen')
    destino_id = request.GET.get('destino')
    fecha_str = request.GET.get('fecha')
    if not (origen_id and destino_id and fecha_str):
        return render(request, 'buscar_viajes.html', {'viajes_con_info': [], 'oficinas': Oficina.objects.filter(activa=True).order_by('nombre')})
    viajes = Viaje.objects.filter(estado='programado', cerrado_venta=False, ruta__activa=True)
    for viaje in viajes:
        liberar_reservas_vencidas(viaje=viaje)
    oficina_origen = Oficina.objects.filter(id=origen_id).first()
    oficina_destino = Oficina.objects.filter(id=destino_id).first()
    fecha = None
    tarifa = None
    if oficina_origen:
        viajes = viajes.filter(ruta__origen=oficina_origen)
    if oficina_destino:
        viajes = viajes.filter(ruta__destinos=oficina_destino)
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hoy = timezone.now().date()
        if fecha >= hoy:
            viajes = viajes.filter(fecha=fecha)
        else:
            viajes = viajes.none()
    except ValueError:
        viajes = viajes.none()
    if oficina_origen and oficina_destino:
        tarifa = Tarifa.objects.filter(origen=oficina_origen, destino=oficina_destino, activa=True).first()
    if oficina_origen:
        request.session['busqueda_origen_id'] = oficina_origen.id
    if oficina_destino:
        request.session['busqueda_destino_id'] = oficina_destino.id
    viajes = viajes.select_related('ruta', 'bus', 'ruta__origen').order_by('fecha', 'hora')
    viajes_con_info = []
    for viaje in viajes:
        disponibles = viaje.asientos.filter(estado='disponible').count()
        viajes_con_info.append({'viaje': viaje, 'disponibles': disponibles, 'tarifa': tarifa})
    return render(request, 'buscar_viajes.html', {
        'viajes_con_info': viajes_con_info, 'oficina_origen': oficina_origen, 'oficina_destino': oficina_destino,
        'fecha': fecha, 'tarifa': tarifa, 'oficinas': Oficina.objects.filter(activa=True).order_by('nombre'),
    })
    
@require_POST
def solicitar_desbloqueo_login(request):
    """Envía un código al correo del usuario bloqueado para forzar la liberación de su sesión."""
    username = request.POST.get('username')
    user = User.objects.filter(username=username).first() or User.objects.filter(email=username).first()
    
    if not user:
        messages.error(request, "Usuario no encontrado.")
        return redirect('core:login')
    
    cliente = getattr(user, 'cliente', None)
    if not cliente:
        messages.error(request, "Esta cuenta no es de tipo cliente.")
        return redirect('core:login')
    
    # Generar código de 6 dígitos para desbloqueo
    codigo = str(random.randint(100000, 999999))
    cliente.codigo_verificacion = codigo
    cliente.fecha_expiracion_codigo = timezone.now() + timedelta(minutes=15)
    cliente.save()
    
    # Guardar en sesión temporalmente el ID del usuario a desbloquear
    request.session['usuario_desbloqueo_id'] = user.id
    
    # ⭐ CORREO HTML PROFESIONAL DE DESBLOQUEO
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #003366; text-align: center;">Viba-Web - Seguridad</h2>
        <p>Hola <strong>{user.first_name}</strong>,</p>
        <p>Has solicitado desbloquear tu sesión activa y liberar tus asientos pendientes.</p>
        <p>Tu código de verificación es:</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 36px; font-weight: bold; color: #dc3545; background-color: #f4f6f8; padding: 12px 24px; border-radius: 6px; letter-spacing: 6px; border: 1px dashed #dc3545;">
                {codigo}
            </span>
        </div>
        <p>Este código expirará en <strong>15 minutos</strong>.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 12px; text-align: center;">Si no solicitaste este cambio, puedes ignorar este mensaje.<br>Viba-Web</p>
    </div>
    """

    # Enviar correo mediante Resend
    try:
        send_mail(
            subject='Código de desbloqueo de sesión - Viba-Web',
            message=f'Hola {user.first_name},\n\nHas solicitado desbloquear tu sesión activa en Viba-Web.\nTu código de verificación es: {codigo}\n\nEste código expirará en 15 minutos.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        messages.success(request, "Te hemos enviado un código de desbloqueo a tu correo electrónico.")
    except Exception as e:
        messages.error(request, f"Error al enviar el correo: {str(e)}")
        
    return redirect('core:confirmar_desbloqueo')
    
# ~ @login_required
def verificar_email(request):
    user_id = request.session.get('verificacion_user_id')
    if not user_id:
        messages.error(request, "No hay ningún proceso de verificación pendiente.")
        return redirect('core:login')
        
    user = get_object_or_404(User, id=user_id)
    cliente = getattr(user, 'cliente', None)
    
    if not cliente or cliente.email_verificado:
        return redirect('core:inicio')
    
    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo', '').strip()
        
        if codigo_ingresado == cliente.codigo_verificacion:
            if timezone.now() > cliente.fecha_expiracion_codigo:
                messages.error(request, "El código ha expirado. Solicita uno nuevo.")
                return render(request, 'verificar_email.html')
            
            # 1. Marcar email como verificado
            cliente.email_verificado = True
            cliente.codigo_verificacion = None
            cliente.fecha_expiracion_codigo = None
            cliente.save()
            
            # 2. ⭐ INICIAR SESIÓN AQUÍ OFICIALMENTE POR PRIMERA VEZ
            auth_login(request, user)
            request.session.pop('verificacion_user_id', None)
            
            messages.success(request, "¡Email verificado exitosamente! Bienvenido a Viba-Web.")
            return redirect('core:inicio')
        else:
            messages.error(request, "El código ingresado no es correcto.")
    
    return render(request, 'verificar_email.html')


@require_POST
def solicitar_desbloqueo_login(request):
    """Envía un código al correo del usuario bloqueado para forzar la liberación de su sesión."""
    username = request.POST.get('username')
    user = User.objects.filter(username=username).first() or User.objects.filter(email=username).first()
    
    if not user:
        messages.error(request, "Usuario no encontrado.")
        return redirect('core:login')
    
    cliente = getattr(user, 'cliente', None)
    if not cliente:
        messages.error(request, "Esta cuenta no es de tipo cliente.")
        return redirect('core:login')
    
    # Generar código de 6 dígitos para desbloqueo
    codigo = str(random.randint(100000, 999999))
    cliente.codigo_verificacion = codigo
    cliente.fecha_expiracion_codigo = timezone.now() + timedelta(minutes=15)
    cliente.save()
    
    # Guardar en sesión temporalmente el ID del usuario a desbloquear
    request.session['usuario_desbloqueo_id'] = user.id
    
    # ⭐ CORREO HTML PROFESIONAL DE DESBLOQUEO
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #003366; text-align: center;">Viba-Web - Seguridad</h2>
        <p>Hola <strong>{user.first_name}</strong>,</p>
        <p>Has solicitado desbloquear tu sesión activa y liberar tus asientos pendientes.</p>
        <p>Tu código de verificación es:</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 36px; font-weight: bold; color: #dc3545; background-color: #f4f6f8; padding: 12px 24px; border-radius: 6px; letter-spacing: 6px; border: 1px dashed #dc3545;">
                {codigo}
            </span>
        </div>
        <p>Este código expirará en <strong>15 minutos</strong>.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 12px; text-align: center;">Si no solicitaste este cambio, puedes ignorar este mensaje.<br>Viba-Web</p>
    </div>
    """

    try:
        send_mail(
            subject='Código de desbloqueo de sesión - Viba-Web',
            message=f'Hola {user.first_name},\n\nHas solicitado desbloquear tu sesión activa en Viba-Web.\nTu código de verificación es: {codigo}\n\nEste código expirará en 15 minutos.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        messages.success(request, "Te hemos enviado un código de desbloqueo a tu correo electrónico.")
    except Exception as e:
        messages.error(request, f"Error al enviar el correo: {str(e)}")
        
    return redirect('core:confirmar_desbloqueo')


def confirmar_desbloqueo_view(request):
    """Valida el código, destruye la sesión anterior, libera asientos huérfanos y loguea al cliente."""
    user_id = request.session.get('usuario_desbloqueo_id')
    if not user_id:
        messages.warning(request, "Por favor, ingresa tu usuario primero.")
        return redirect('core:login')
        
    user = get_object_or_404(User, id=user_id)
    cliente = getattr(user, 'cliente', None)
    
    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo', '').strip()
        
        if codigo_ingresado and codigo_ingresado == cliente.codigo_verificacion:
            if timezone.now() > cliente.fecha_expiracion_codigo:
                messages.error(request, "El código ha expirado. Solicita uno nuevo.")
                return render(request, 'confirmar_desbloqueo.html')
                
            with transaction.atomic():
                # 1. Destruir la sesión activa anterior en la base de datos
                SesionActiva.objects.filter(user=user).delete()
                
                # 2. Liberar asientos amarillos / huérfanos reservados por este usuario
                Asiento.objects.filter(
                    estado='reservado',
                    reservado_por=user
                ).update(
                    estado='disponible',
                    reservado_por=None,
                    reservado_hasta=None
                )
                
                # 3. Limpiar código usado
                cliente.codigo_verificacion = None
                cliente.fecha_expiracion_codigo = None
                cliente.save()
                
            # 4. Iniciar sesión limpiamente de forma automática
            auth_login(request, user)
            request.session.pop('usuario_desbloqueo_id', None)
            request.session.pop('reserva_inicio', None)
            request.session.pop('asientos_seleccionados', None)
            
            messages.success(request, "¡Sesión desbloqueada y liberada con éxito! Has ingresado limpiamente.")
            return redirect('core:perfil')
        else:
            messages.error(request, "El código ingresado es incorrecto.")
            
    return render(request, 'confirmar_desbloqueo.html', {'user_obj': user})
