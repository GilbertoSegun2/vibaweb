from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import (
    Oficina, Viaje, Asiento, Transaccion, Pago, Boleto, Tarifa, 
    MovimientoAsiento, UsuarioEmpresa, Cliente, Credito, 
    PlantillaBus, PlantillaAsiento, Ruta, RutaParada, Suscripcion,
    Pistero, SesionActiva
)
from .forms import RegistroForm, LoginForm, PagoWebForm, PasajeroForm, PasarelaVirtualForm
from .utils import (
    obtener_parametro, liberar_reservas_vencidas, generar_codigo_transaccion,
    generar_codigo_qr, asiento_esta_disponible_en_tramo,
    generar_numero_boleto,
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
# FUNCIONES AUXILIARES DE SEGURIDAD Y TRAMOS
# ============================================================
def validar_tarifa_para_viaje(viaje, origen_id, destino_id):
    if not (origen_id and destino_id):
        return (None, True)
    try:
        origen_id_int = int(origen_id)
        destino_id_int = int(destino_id)
    except (ValueError, TypeError):
        return (None, False)
    
    p_origen = viaje.ruta.paradas.filter(oficina_id=origen_id_int).first()
    p_destino = viaje.ruta.paradas.filter(oficina_id=destino_id_int).first()
    
    if p_origen and p_destino:
        if p_origen.orden >= p_destino.orden:
            return (None, False)
    else:
        origen_valido = (viaje.ruta.origen_id == origen_id_int)
        destino_valido = viaje.ruta.destinos.filter(id=destino_id_int).exists()
        if not (origen_valido and destino_valido):
            return (None, False)
            
    tarifa = Tarifa.objects.filter(origen_id=origen_id_int, destino_id=destino_id_int, activa=True).first()
    return (tarifa, True)

def obtener_ordenes_tramo(viaje, origen_id, destino_id):
    if not (origen_id and destino_id):
        return None, None
    try:
        p_origen = viaje.ruta.paradas.filter(oficina_id=int(origen_id)).first()
        p_destino = viaje.ruta.paradas.filter(oficina_id=int(destino_id)).first()
        if p_origen and p_destino:
            return p_origen.orden, p_destino.orden
    except (ValueError, TypeError):
        pass
    return None, None

def inicio(request):
    # ~ # ⭐ PRUEBA DE FUEGO: Forzar un error aquí mismo para ver si entra a la función
    # ~ raise Exception(f"EL SLUG LEÍDO ES: {obtener_parametro('200', default='NO_EXISTE')}")
    
    # ~ if request.user.is_authenticated and getattr(request.user, 'usuarioempresa', None):
        # ~ return redirect('core:taquilla_inicio')
    
    if request.user.is_authenticated and getattr(request.user, 'usuarioempresa', None):
        return redirect('core:taquilla_inicio')
        
    request.session.pop('reserva_inicio', None)
    logout_reciente = request.session.pop('logout_reciente', False)
    
    oficinas = Oficina.objects.filter(activa=True).order_by('nombre')
    bienvenida_titulo = obtener_parametro('160', default='Bienvenido a Viba-Web')
    bienvenida_subtitulo = obtener_parametro('161', default='Compra tus boletos de autobús de forma rápida y segura')
    hoy = timezone.localtime(timezone.now()).strftime('%Y-%m-%d')
    
    empresa_slug = obtener_parametro('200', default='core')
    template = f'{empresa_slug}/inicio.html'
    
    from django.template.loader import get_template
    from django.template import TemplateDoesNotExist
    
    try:
        get_template(template)
    except TemplateDoesNotExist:
        template = 'core/inicio.html'
        # ~ empresa_slug = 'core' # Si hace fallback, usamos core
    
    return render(request, template, {
        'oficinas': oficinas, 
        'logout_reciente': logout_reciente,
        'bienvenida_titulo': bienvenida_titulo, 
        'bienvenida_subtitulo': bienvenida_subtitulo,
        'hoy': hoy,
        'prefijo_empresa': empresa_slug, # ⭐ ESTE ERA EL DETALLE FALTANTE
    })

@login_required
def detalle_viaje(request, viaje_id):
    viaje = get_object_or_404(Viaje, id=viaje_id)
    
    minutos_bloqueo = int(obtener_parametro('184', default=60))
    ahora = timezone.localtime(timezone.now())
    hora_limite = ahora + timedelta(minutes=minutos_bloqueo)
    
    if viaje.fecha == ahora.date() and viaje.hora <= hora_limite.time():
        messages.warning(request, "Apreciado cliente: El tiempo limite de compra Web para esta salida a finalizado.")
        return redirect('core:inicio')
    
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

    if reserva_inicio_str:
        expiracion_iso = (reserva_inicio + timedelta(minutes=minutos_reserva)).isoformat()
    else:
        expiracion_iso = (timezone.now() + timedelta(minutes=minutos_reserva)).isoformat()
    
    return render(request, 'detalle_viaje.html', {
        'viaje': viaje, 
        'asientos_por_piso': asientos_por_piso, 
        'cliente_id': cliente.id if cliente else None,
        'usuario_id': request.user.id if request.user.is_authenticated else None,
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
        next_url = request.GET.get('next') or ''
        if next_url and not any(x in next_url for x in ['/perfil', '/login', '/registro']):
            return redirect(next_url)
        return redirect('core:inicio')
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
                
                # ⭐ VERIFICAR SI YA HAY UNA SESIÓN ACTIVA ANTES DE LOGUEAR
                from .models import SesionActiva
                from django.utils import timezone
                from datetime import timedelta
                
                if not (user.is_staff or user.is_superuser):
                    sesion_existente = SesionActiva.objects.filter(user=user).first()
                    
                    if sesion_existente:
                        minutos_espera = int(obtener_parametro('142', default=3))
                        inactividad = timezone.now() - sesion_existente.ultima_actividad
                        
                        if inactividad < timedelta(minutes=minutos_espera):
                            # El usuario ya tiene una sesión activa reciente -> BLOQUEAMOS el nuevo ingreso
                            messages.warning(
                                request, 
                                f"Estimado usuario: su cuenta ya está activa en otro dispositivo (IP: {sesion_existente.ip_address}). "
                                f"Por seguridad, no puede iniciar una nueva sesión hasta que la anterior expire o se cierre. "
                                f"Si usted es el dueño de la cuenta, espere unos minutos o contacte al administrador."
                            )
                            return render(request, 'login.html', {'form': form})

                auth_login(request, user)
                request.session.set_expiry(0)
                
                if getattr(user, 'cliente', None) and not user.cliente.email_verificado:
                    messages.warning(request, "Debes verificar tu correo electrónico antes de continuar.")
                    return redirect('core:verificar_email')
                
                Asiento.objects.filter(
                    estado='reservado',
                    reservado_por=user
                ).update(
                    estado='disponible',
                    reservado_por=None,
                    reservado_hasta=None
                )
                
                request.session.pop('reserva_inicio', None)
                request.session.pop('asientos_seleccionados', None)
                request.session.pop('pasajeros_data', None)
                
                # ⭐ REGISTRAMOS LA SESIÓN (Ahora sí, para todos los roles)
                if not (user.is_staff or user.is_superuser):
                    SesionActiva.objects.filter(user=user).delete()
                    SesionActiva.objects.create(
                        user=user, 
                        session_key=request.session.session_key, 
                        ip_address=request.META.get('REMOTE_ADDR'), 
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:250], 
                        ultima_actividad=timezone.now()
                    )
                
                nombre = user.first_name or user.username
                messages.success(request, f"Estimado usuario {nombre}: bienvenido nuevamente. Es un gusto tenerlo de vuelta.")
                
                next_url = request.POST.get('next') or request.GET.get('next') or ''
                
                if getattr(user, 'usuarioempresa', None):
                    return redirect('core:taquilla_inicio')
                
                if 'taquilla' in next_url and getattr(user, 'cliente', None):
                    messages.info(
                        request, 
                        "Estimado cliente: el área de taquilla es exclusiva para empleados. "
                        "Lo hemos redirigido a su perfil."
                    )
                    return redirect('core:perfil')
                    
                if next_url and not any(x in next_url for x in ['/perfil', '/login', '/registro']):
                    return redirect(next_url)
                else:
                    return redirect('core:inicio')
            else:
                messages.error(request, "Estimado usuario: los datos ingresados no coinciden con nuestros registros. Por favor, verifique su usuario y contraseña e intente nuevamente.")
    else:
        form = LoginForm()
    minutos_login = int(obtener_parametro('185', default=2))
    
    return render(request, 'login.html', {
        'form': form,
        'minutos_login': minutos_login,
    })

def procesar_liberacion_asientos(user):
    cliente = getattr(user, 'cliente', None)
    if cliente:
        with transaction.atomic():
            asientos_reservados = Asiento.objects.select_for_update().filter(
                estado='reservado', 
                reservado_por=user
            )
            for asiento in asientos_reservados:
                MovimientoAsiento.objects.create(
                    asiento=asiento, 
                    tipo='liberacion_manual', 
                    estado_anterior='reservado', 
                    estado_nuevo='disponible', 
                    usuario=user, 
                    motivo='El cliente cerró sesión o expiró la sesión por inactividad.'
                )
            asientos_reservados.update(estado='disponible', reservado_por=None, reservado_hasta=None)

def logout_view(request):
    if request.user.is_authenticated:
        procesar_liberacion_asientos(request.user)
        SesionActiva.objects.filter(user=request.user).delete()
    
    request.session.pop('asientos_seleccionados', None)
    request.session.pop('reserva_inicio', None)
    request.session.pop('login_inicio', None)
    
    logout(request)
    messages.info(request, "Estimado cliente: su sesión ha finalizado correctamente. Gracias por preferirnos.")
    request.session['logout_reciente'] = True
    response = redirect('core:inicio')
    response.status_code = 303
    return response

@require_POST
@login_required
def timeout_logout_view(request):
    if request.user.is_authenticated:
        procesar_liberacion_asientos(request.user)
        SesionActiva.objects.filter(user=request.user).delete()
        logout(request)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'unauthorized'}, status=401)

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
    if not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    empleado = getattr(request.user, 'usuarioempresa', None)
    
    if not cliente and not empleado:
        return JsonResponse({'ok': False, 'error': 'Usuario no autorizado.'}, status=400)
    
    try:
        with transaction.atomic():
            asientos = Asiento.objects.select_for_update().filter(
                id__in=asientos_ids, estado='reservado', reservado_por=request.user
            )
            for asiento in asientos:
                MovimientoAsiento.objects.create(
                    asiento=asiento, tipo='liberacion_manual', 
                    estado_anterior='reservado', estado_nuevo='disponible', 
                    usuario=request.user, motivo='El usuario liberó el asiento.'
                )
            asientos.update(estado='disponible', reservado_hasta=None, reservado_por=None)
        
        asientos_sesion = request.session.get('asientos_seleccionados', [])
        asientos_sesion = [aid for aid in asientos_sesion if str(aid) not in asientos_ids]
        request.session['asientos_seleccionados'] = asientos_sesion
        
        return JsonResponse({'ok': True, 'cantidad': len(asientos_ids)})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

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
    
    minutos_bloqueo = int(obtener_parametro('184', default=60))
    ahora = timezone.localtime(timezone.now())
    hora_limite = ahora + timedelta(minutes=minutos_bloqueo)
    
    if viaje.fecha == ahora.date() and viaje.hora <= hora_limite.time():
        messages.warning(request, "Apreciado cliente: El tiempo limite de compra Web para esta salida a finalizado.")
        return redirect('core:inicio')
    
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
    
    orden_origen, orden_destino = obtener_ordenes_tramo(viaje, origen_id, destino_id)

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
                    asiento.reservado_por = request.user
                    asiento.save()
                    monto_tarifa = tarifa.monto_usd if tarifa else 0
                    monto_seguro = valor_seguro if tarifa else 0
                    monto_total_boleto = monto_tarifa + monto_seguro
                    Boleto.objects.create(
                        transaccion=transaccion, viaje=viaje, 
                        asiento=asiento, 
                        orden_origen=orden_origen,
                        orden_destino=orden_destino,
                        pasajero_cedula=p['cedula'], 
                        pasajero_nombre=p['nombre'], 
                        pasajero_telefono=p.get('telefono', ''), 
                        tipo_pasajero=p['tipo_pasajero'], 
                        monto_tarifa_usd=monto_tarifa, 
                        monto_seguro_usd=monto_seguro, 
                        monto_total_usd=monto_total_boleto, 
                        tasa_bcv=tasa_bcv, 
                        monto_total_bs=(monto_total_boleto * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0,
                        numero_boleto=generar_numero_boleto(None, es_continuo=obtener_parametro('179', default=False)),
                        codigo_qr=generar_codigo_qr(), 
                        estado='pendiente_verificacion'
                    )
                    
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
    pagos = transaccion.pagos.all() 
    return render(request, 'confirmacion.html', {
        'transaccion': transaccion, 
        'boletos': boletos, 
        'pagos': pagos,
        'fecha_venta': transaccion.fecha_creacion,
    })

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

    orden_origen, orden_destino = obtener_ordenes_tramo(viaje, origen_id, destino_id)

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
                    Boleto.objects.create(
                        transaccion=transaccion, viaje=viaje, asiento=asiento, 
                        orden_origen=orden_origen,
                        orden_destino=orden_destino,
                        pasajero_cedula=p['cedula'], 
                        pasajero_nombre=p['nombre'], 
                        pasajero_telefono=p.get('telefono', ''), 
                        tipo_pasajero=p['tipo_pasajero'], 
                        monto_tarifa_usd=monto_tarifa, 
                        monto_seguro_usd=monto_seguro, 
                        monto_total_usd=monto_total_boleto, 
                        tasa_bcv=tasa_bcv, 
                        monto_total_bs=(monto_total_boleto * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0, 
                        numero_boleto=generar_numero_boleto(None, es_continuo=obtener_parametro('179', default=False)),
                        codigo_qr=generar_codigo_qr(), 
                        estado='vendido'
                    )
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
    from .utils import liberar_reservas_vencidas
    viajes_con_reservas = Viaje.objects.filter(
        asientos__estado='reservado',
        asientos__reservado_hasta__lt=timezone.now()
    ).distinct()
    for viaje in viajes_con_reservas:
        liberar_reservas_vencidas(viaje=viaje)

    request.session.pop('reserva_inicio', None)
    if not request.user.is_authenticated:
        return redirect('core:login')
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos para acceder a la taquilla.")
        return redirect('core:inicio')

    origen_id = request.GET.get('origen', empleado.oficina.id)
    destino_id = request.GET.get('destino')
    fecha_str = request.GET.get('fecha')
    
    if not fecha_str:
        fecha_str = timezone.localtime(timezone.now()).strftime('%Y-%m-%d')
    
    viajes_con_info = []
    tasa_bcv = obtener_parametro('107', default=0)
    oficinas = Oficina.objects.filter(activa=True).order_by('nombre')
    
    if destino_id and fecha_str and origen_id:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            oficina_origen = Oficina.objects.get(id=origen_id)
            oficina_destino = Oficina.objects.get(id=destino_id) # Obtenemos la oficina destino
            
            hoy = timezone.localtime(timezone.now()).date()
            ahora = timezone.localtime(timezone.now()).time()

            viajes_del_dia = Viaje.objects.filter(
                fecha=fecha, estado='programado', cerrado_venta=False
            ).select_related('ruta', 'bus')

            # ~ if fecha == hoy:
                # ~ viajes_del_dia = viajes_del_dia.filter(hora__gt=ahora)

            for viaje in viajes_del_dia:
                # ⭐ VALIDACIÓN ESTRICTA DE DIRECCIÓN
                parada_origen = viaje.ruta.paradas.filter(oficina=oficina_origen).first()
                parada_destino = viaje.ruta.paradas.filter(oficina=oficina_destino).first()
                
                if parada_origen and parada_destino and parada_origen.orden < parada_destino.orden:
                    tarifa = Tarifa.objects.filter(origen=oficina_origen, destino=oficina_destino, activa=True).first()
                    disponibles = viaje.asientos.filter(estado='disponible').count()
                    
                    viajes_con_info.append({
                        'viaje': viaje, 'tarifa': tarifa,
                        'precio_usd': tarifa.monto_usd if tarifa else 0,
                        'precio_bs': (tarifa.monto_usd * tasa_bcv) if tarifa and tasa_bcv else 0,
                        'disponibles': disponibles
                    })
        except (ValueError, Oficina.DoesNotExist):
            messages.error(request, "Formato de fecha o datos inválidos.")

    return render(request, 'taquilla/inicio.html', {
        'empleado': empleado, 'oficinas': oficinas,
        'viajes_con_info': viajes_con_info,
        'origen_seleccionado': int(origen_id) if origen_id else None,
        'destino_seleccionado': int(destino_id) if destino_id else None,
        'fecha_seleccionada': fecha_str, 'tasa_bcv': tasa_bcv,
    })

def taquilla_mapa(request, viaje_id):
    if not request.user.is_authenticated:
        return redirect('core:login')

    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos para acceder a la taquilla.")
        return redirect('core:inicio')

    viaje = get_object_or_404(Viaje, id=viaje_id)
    
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

    Asiento.objects.filter(
        viaje=viaje,
        estado='reservado',
        reservado_por=request.user
    ).update(reservado_hasta=expira_en)

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
        asiento.refresh_from_db()
        if asiento.tipo == 'asiento':
            disponible_para_tramo = asiento_esta_disponible_en_tramo(asiento.id, viaje.id, parada_origen.orden, parada_destino.orden)
        else:
            disponible_para_tramo = False
            
        if asiento.estado in ['reservado', 'bloqueado'] and asiento.reservado_por != request.user:
            disponible_para_tramo = False

        asiento.estado_real = asiento.estado
        asiento.disponible_para_tramo = disponible_para_tramo

        # ⭐ NUEVO: Buscar info del pasajero si el asiento está vendido o usado
        asiento.info_pasajero = None
        if asiento.estado in ['vendido', 'usado', 'pendiente_verificacion']:
            boleto = Boleto.objects.filter(asiento=asiento, viaje=viaje).first()
            if boleto:
                asiento.info_pasajero = f"{boleto.pasajero_nombre} ({boleto.numero_boleto})"

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
        'usuario_id': request.user.id,
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

    pisteros = Pistero.objects.filter(oficina=empleado.oficina, activo=True).order_by('nombre')

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

        pistero_id = request.POST.get('pistero_id')
        pistero = Pistero.objects.filter(id=pistero_id, oficina=empleado.oficina).first() if pistero_id else None
        comision_pistero = (pistero.comision_usd * len(boletos_creados)) if pistero else Decimal('0.00')

        try:
            with transaction.atomic():
                codigo = generar_codigo_transaccion()
                transaccion = Transaccion.objects.create(
                    codigo=codigo, cliente=None, viaje=viaje, cantidad_boletos=len(boletos_creados),
                    monto_total_usd=total_venta_usd, monto_total_bs=total_venta_bs, tasa_bcv=tasa_bcv,
                    estado='confirmada', fecha_confirmacion=timezone.now(),
                    vendido_por=request.user, oficina_venta=empleado.oficina,
                    oficina_destino=parada_destino.oficina, dispositivo_venta='Taquilla',
                    pistero=pistero, 
                    comision_pistero_usd=comision_pistero, 
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
                        orden_origen=parada_origen.orden,
                        orden_destino=parada_destino.orden,
                        pasajero_cedula=b['cedula'], pasajero_nombre=b['nombre'], pasajero_telefono=b['telefono'],
                        tipo_pasajero=b['tipo'], monto_tarifa_usd=b['precio'], monto_seguro_usd=b['seguro'],
                        monto_total_usd=b['total'], tasa_bcv=tasa_bcv,
                        monto_total_bs=(b['total'] * tasa_bcv).quantize(Decimal('0.01')) if tasa_bcv else 0,
                        codigo_qr=generar_codigo_qr(), estado='vendido', vendido_por=request.user,
                        numero_boleto=generar_numero_boleto(empleado.oficina, es_continuo=obtener_parametro('179', default=False)),
                    )

                # ⭐ AUTO-ABORDAR: DENTRO DEL WITH
                minutos_auto = int(obtener_parametro('202', default=15))
                ahora = timezone.localtime(timezone.now())
                fecha_hora_viaje = timezone.make_aware(datetime.combine(viaje.fecha, viaje.hora))
                minutos_para_salida = (fecha_hora_viaje - ahora).total_seconds() / 60

                if 0 <= minutos_para_salida <= minutos_auto:
                    for boleto_creado in transaccion.boletos.all():
                        boleto_creado.estado = 'usado'
                        boleto_creado.fecha_chequeo = timezone.now()
                        boleto_creado.chequeado_por = request.user
                        boleto_creado.observacion = f"Auto-chequeado al vender (faltan {int(minutos_para_salida)} min)."
                        boleto_creado.save()
                        
                        # ⭐ NUEVO: Actualizar el estado del asiento también
                        asiento_creado = boleto_creado.asiento
                        asiento_creado.estado = 'usado'
                        asiento_creado.save()
                        
                        MovimientoAsiento.objects.create(
                            asiento=boleto_creado.asiento, tipo='chequeo',
                            estado_anterior='vendido', estado_nuevo='usado',
                            usuario=request.user, motivo=f'Auto-chequeo al vender. Boleto: {boleto_creado.numero_boleto}', 
                            boleto_relacionado=boleto_creado
                        )

            request.session.pop('reserva_inicio', None)
            messages.success(request, f"¡Venta exitosa! Código: {codigo}")
            return redirect('core:taquilla_confirmacion', transaccion_id=transaccion.id)

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
        'pisteros': pisteros, 
    })

@login_required
def taquilla_confirmacion(request, transaccion_id):
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos para acceder a la taquilla.")
        return redirect('core:inicio')
    
    transaccion = get_object_or_404(Transaccion, id=transaccion_id)
    boletos = transaccion.boletos.all().order_by('asiento__numero')
    pagos = transaccion.pagos.all() 
    
    return render(request, 'taquilla/confirmacion.html', {
        'transaccion': transaccion,
        'boletos': boletos,
        'pagos': pagos,
        'empleado': empleado,
        'fecha_venta': transaccion.fecha_creacion, 
        'formato_impresion': obtener_parametro('176', default=1), 
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
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .forms import RegistroForm 
from .models import Cliente     
import resend                    

def registro_usuario(request):
    if request.user.is_authenticated:
        return redirect('core:inicio')
    
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password1'],
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', '')
            )

            minutos_expiracion = int(obtener_parametro('188', default=15))
            
            codigo = str(random.randint(100000, 999999))
            cliente = Cliente.objects.create(
                user=user,
                cedula=data['cedula'],
                telefono=data['telefono'],
                whatsapp=data.get('whatsapp', ''),
                codigo_verificacion=codigo,
                fecha_expiracion_codigo=timezone.now() + timedelta(minutes=minutos_expiracion), 
                email_verificado=False
            )
            
            try:
                html_content = render_to_string('email_verificacion.html', {
                    'user': user,
                    'codigo': codigo,
                    'first_name': user.first_name,
                })
                
                resend.api_key = settings.EMAIL_HOST_PASSWORD
                
                params = {
                    "from": settings.DEFAULT_FROM_EMAIL,
                    "to": [user.email],
                    "subject": "Verifica tu cuenta - Viba-Web",
                    "html": html_content,
                }
                
                email_response = resend.Emails.send(params)
                
                request.session['verificacion_user_id'] = user.id
                messages.success(request, f"¡Registro exitoso, {user.first_name}! Te hemos enviado un código de verificación a tu correo.")
                return redirect('core:verificar_email')
                
            except Exception as e:
                if user.pk:
                    user.delete()
                messages.error(request, f"No pudimos enviar el correo de verificación debido a un problema de red: {str(e)}")
                return render(request, 'registro.html', {'form': form})
    else:
        form = RegistroForm()
    
    return render(request, 'registro.html', {'form': form})
    
@require_POST
@login_required
def reservar_temporal(request):
    viaje_id = request.POST.get('viaje_id')
    asiento_id = request.POST.get('asiento_id')
    
    if not viaje_id or not asiento_id:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    empleado = getattr(request.user, 'usuarioempresa', None)
    
    if not cliente and not empleado:
        return JsonResponse({'ok': False, 'error': 'Usuario no autorizado.'}, status=400)
    
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
    viaje_id = request.POST.get('viaje_id')
    asientos_ids = request.POST.getlist('asientos[]')
    
    if not viaje_id or not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
    
    cliente = getattr(request.user, 'cliente', None)
    empleado = getattr(request.user, 'usuarioempresa', None)
    
    if not cliente and not empleado:
        return JsonResponse({'ok': False, 'error': 'Usuario no autorizado.'}, status=400)
    
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
    if request.user.is_authenticated:
        from .models import SesionActiva
        SesionActiva.objects.filter(user=request.user).update(
            ultima_actividad=timezone.now()
        )
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=401)
        
def buscar_viajes(request):
    origen_id = request.GET.get('origen')
    destino_id = request.GET.get('destino')
    fecha_str = request.GET.get('fecha')
    
    if not (origen_id and destino_id and fecha_str):
        return render(request, 'buscar_viajes.html', {'viajes_con_info': [], 'oficinas': Oficina.objects.filter(activa=True).order_by('nombre')})
    
    try:
        origen_id = int(origen_id)
        destino_id = int(destino_id)
    except ValueError:
        return render(request, 'buscar_viajes.html', {'viajes_con_info': [], 'oficinas': Oficina.objects.filter(activa=True).order_by('nombre')})

    oficina_origen = Oficina.objects.filter(id=origen_id).first()
    oficina_destino = Oficina.objects.filter(id=destino_id).first()
    
    if not oficina_origen or not oficina_destino:
        return render(request, 'buscar_viajes.html', {'viajes_con_info': [], 'oficinas': Oficina.objects.filter(activa=True).order_by('nombre')})

    # ⭐ LA SOLUCIÓN: Buscar todos los viajes programados y filtrar manualmente
    viajes_base = Viaje.objects.filter(
        estado='programado', 
        cerrado_venta=False, 
        ruta__activa=True
    ).select_related('ruta', 'bus')

    viajes_validos = []
    for viaje in viajes_base:
        # Buscamos la parada de origen y la de destino en la ruta de ESTE viaje
        parada_origen = viaje.ruta.paradas.filter(oficina=oficina_origen).first()
        parada_destino = viaje.ruta.paradas.filter(oficina=oficina_destino).first()
        
        # Si el origen y destino están en la ruta, y el origen va ANTES que el destino -> ¡Es válido!
        if parada_origen and parada_destino and parada_origen.orden < parada_destino.orden:
            viajes_validos.append(viaje)

    # Ahora filtramos por fecha
    fecha = None
    tarifa = None
    viajes_finales = []
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hoy = timezone.now().date()
        
        if fecha >= hoy:
            for viaje in viajes_validos:
                if viaje.fecha == fecha:
                    # Validar hora si es hoy
                    if fecha == hoy:
                        minutos_bloqueo = int(obtener_parametro('184', default=60))
                        ahora = timezone.localtime(timezone.now())
                        hora_limite = ahora + timedelta(minutes=minutos_bloqueo)
                        if viaje.hora > hora_limite.time():
                            viajes_finales.append(viaje)
                    else:
                        viajes_finales.append(viaje)
    except ValueError:
        viajes_finales = []

    # Calcular tarifa
    if oficina_origen and oficina_destino:
        tarifa = Tarifa.objects.filter(origen=oficina_origen, destino=oficina_destino, activa=True).first()
    
    # Guardar en sesión
    if oficina_origen:
        request.session['busqueda_origen_id'] = oficina_origen.id
    if oficina_destino:
        request.session['busqueda_destino_id'] = oficina_destino.id
    
    # Liberar reservas vencidas de estos viajes
    for viaje in viajes_finales:
        liberar_reservas_vencidas(viaje=viaje)
        
    viajes_con_info = []
    tasa_bcv = obtener_parametro('107', default=0)
    
    for viaje in viajes_finales:
        disponibles = viaje.asientos.filter(estado='disponible').count()
        precio_usd = tarifa.monto_usd if tarifa else 0
        
        precio_bs_num = (precio_usd * tasa_bcv) if tasa_bcv else 0
        precio_bs_formateado = f"{precio_bs_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        viajes_con_info.append({
            'viaje': viaje, 
            'disponibles': disponibles, 
            'tarifa': tarifa,
            'precio_usd': precio_usd,
            'precio_bs': precio_bs_formateado,
        })
        
    return render(request, 'buscar_viajes.html', {
        'viajes_con_info': viajes_con_info, 
        'oficina_origen': oficina_origen, 
        'oficina_destino': oficina_destino,
        'fecha': fecha, 
        'tarifa': tarifa, 
        'oficinas': Oficina.objects.filter(activa=True).order_by('nombre'),
    })
    
@require_POST
def solicitar_desbloqueo_login(request):
    username = request.POST.get('username')
    user = User.objects.filter(username=username).first() or User.objects.filter(email=username).first()
    
    if not user:
        messages.error(request, "Usuario no encontrado.")
        return redirect('core:login')
    
    cliente = getattr(user, 'cliente', None)
    if not cliente:
        messages.error(request, "Esta cuenta no es de tipo cliente.")
        return redirect('core:login')
    
    codigo = str(random.randint(100000, 999999))
    cliente.codigo_verificacion = codigo
    cliente.fecha_expiracion_codigo = timezone.now() + timedelta(minutes=15)
    cliente.save()
    
    request.session['usuario_desbloqueo_id'] = user.id
    
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
            
            cliente.email_verificado = True
            cliente.codigo_verificacion = None
            cliente.fecha_expiracion_codigo = None
            cliente.save()
            
            auth_login(request, user)
            request.session.pop('verificacion_user_id', None)
            
            messages.success(request, "¡Email verificado exitosamente! Bienvenido a Viba-Web.")
            return redirect('core:inicio')
        else:
            messages.error(request, "El código ingresado no es correcto.")
    
    return render(request, 'verificar_email.html')
    
def confirmar_desbloqueo_view(request):
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
                SesionActiva.objects.filter(user=user).delete()
                Asiento.objects.filter(
                    estado='reservado',
                    reservado_por=user
                ).update(
                    estado='disponible',
                    reservado_por=None,
                    reservado_hasta=None
                )
                cliente.codigo_verificacion = None
                cliente.fecha_expiracion_codigo = None
                cliente.save()
                
            auth_login(request, user)
            request.session.pop('usuario_desbloqueo_id', None)
            request.session.pop('reserva_inicio', None)
            request.session.pop('asientos_seleccionados', None)
            
            messages.success(request, "¡Sesión desbloqueada y liberada con éxito! Has ingresado limpiamente.")
            return redirect('core:perfil')
        else:
            messages.error(request, "El código ingresado es incorrecto.")
            
    return render(request, 'confirmar_desbloqueo.html', {'user_obj': user})

def cancelar_registro(request):
    user_id = request.session.get('verificacion_user_id')
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            user.delete()
        except User.DoesNotExist:
            pass
        
        del request.session['verificacion_user_id']
        
    messages.info(request, "El registro ha sido cancelado.")
    return redirect('core:inicio')
    
from django.db.models import Count

def api_destinos_populares(request):
    origen_id = request.GET.get('origen_id')
    if not origen_id:
        return JsonResponse([], safe=False)

    populares = Boleto.objects.filter(
        viaje__ruta__origen_id=origen_id,
        estado__in=['vendido', 'usado', 'liquidado']
    ).values(
        'viaje__ruta__destinos__id', 
        'viaje__ruta__destinos__nombre'
    ).annotate(
        total=Count('id')
    ).order_by('-total')[:10]

    data = []
    for p in populares:
        if p['viaje__ruta__destinos__id']:
            data.append({
                'id': p['viaje__ruta__destinos__id'],
                'nombre': p['viaje__ruta__destinos__nombre']
            })

    if not data:
        destinos = Oficina.objects.filter(activa=True).order_by('nombre')
        data = [{'id': d.id, 'nombre': d.nombre} for d in destinos]

    return JsonResponse(data, safe=False)
    
def api_buscar_oficinas(request):
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    oficinas = Oficina.objects.filter(
        nombre__icontains=query,
        activa=True
    ).order_by('nombre')[:10]
    
    data = [{'id': o.id, 'nombre': o.nombre} for o in oficinas]
    return JsonResponse(data, safe=False)
    
@login_required
def taquilla_buscar_boleto(request):
    """Busca un boleto para TRANSFERIR (en cualquier viaje)."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'ok': False, 'error': 'Ingrese un dato de búsqueda'}, status=400)
        
    filtros = Q(pasajero_cedula__icontains=query) | Q(codigo_qr__icontains=query) | Q(numero_boleto__icontains=query)
    boletos = Boleto.objects.filter(filtros, estado='vendido').select_related('viaje', 'asiento', 'viaje__ruta').order_by('-fecha_venta')[:10]
    
    resultados = [{
        'id': b.id,
        'cedula': b.pasajero_cedula,
        'nombre': b.pasajero_nombre,
        'asiento_numero': b.asiento.numero,
        'asiento_id': b.asiento.id,
        'viaje_id': b.viaje_id,
        'viaje_ruta': b.viaje.ruta.nombre,
        'viaje_hora': b.viaje.hora.strftime('%I:%M %p'),
    } for b in boletos]
        
    return JsonResponse({'ok': True, 'resultados': resultados})

@require_POST
@login_required
def taquilla_ejecutar_transferencia(request):
    """Mueve el asiento de un pasajero a otro asiento (mismo bus o distinto bus)."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    boleto_id = request.POST.get('boleto_id')
    nuevo_asiento_id = request.POST.get('nuevo_asiento_id')
    
    if not boleto_id or not nuevo_asiento_id:
        return JsonResponse({'ok': False, 'error': 'Faltan datos.'}, status=400)
        
    try:
        with transaction.atomic():
            boleto = Boleto.objects.select_for_update().get(id=boleto_id, estado='vendido')
            asiento_viejo = boleto.asiento
            asiento_nuevo = Asiento.objects.select_for_update().get(id=nuevo_asiento_id)
            
            # ⭐ VALIDACIÓN: Acepta 'disponible' o 'reservado' por el mismo taquillero
            if asiento_nuevo.estado != 'disponible' and asiento_nuevo.reservado_por != request.user:
                return JsonResponse({'ok': False, 'error': 'El asiento ya fue tomado por otro usuario.'}, status=400)

            # Liberar viejo, ocupar nuevo
            asiento_viejo.estado = 'disponible'
            asiento_viejo.save()
            
            asiento_nuevo.estado = 'vendido'
            asiento_nuevo.reservado_por = None
            asiento_nuevo.reservado_hasta = None
            asiento_nuevo.save()
            
            # Actualizar boleto (cambia el asiento y el viaje)
            boleto.asiento = asiento_nuevo
            boleto.viaje = asiento_nuevo.viaje  # <--- CAMBIA EL VIAJE AL NUEVO BUS
            boleto.save()
            
            # Auditoría
            MovimientoAsiento.objects.create(
                asiento=asiento_viejo, tipo='transferencia', 
                estado_anterior='vendido', estado_nuevo='disponible', 
                usuario=request.user, motivo=f'Transferido al asiento {asiento_nuevo.numero} (Bus {asiento_nuevo.viaje.id})', boleto_relacionado=boleto
            )
            MovimientoAsiento.objects.create(
                asiento=asiento_nuevo, tipo='transferencia', 
                estado_anterior='disponible', estado_nuevo='vendido', 
                usuario=request.user, motivo=f'Recibido del asiento {asiento_viejo.numero} (Bus {asiento_viejo.viaje.id})', boleto_relacionado=boleto
            )
            
        return JsonResponse({'ok': True, 'mensaje': f'Pasajero movido al asiento {asiento_nuevo.numero} del bus {asiento_nuevo.viaje.hora}.'})
    except Boleto.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Boleto no encontrado.'}, status=404)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@login_required
def taquilla_buscar_boleto_reprogramar(request):
    """Busca un boleto en CUALQUIER viaje para REPROGRAMAR (cambiar de bus)."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'ok': False, 'error': 'Ingrese un dato'}, status=400)
        
    filtros = Q(pasajero_cedula__icontains=query) | Q(codigo_qr__icontains=query) | Q(numero_boleto__icontains=query)
    boletos = Boleto.objects.filter(filtros, estado='vendido').select_related('viaje', 'asiento', 'viaje__ruta').order_by('-fecha_venta')[:10]
    
    resultados = [{
        'id': b.id, 'numero_boleto': b.numero_boleto, 'cedula': b.pasajero_cedula, 'nombre': b.pasajero_nombre,
        'viaje_ruta': b.viaje.ruta.nombre, 'viaje_fecha': b.viaje.fecha.strftime('%d/%m/%Y'),
        'asiento_numero': b.asiento.numero, 'monto_total_usd': float(b.monto_total_usd), 
        'monto_total_bs': float(b.monto_total_bs), 'tasa_bcv': float(b.tasa_bcv),
    } for b in boletos]
    return JsonResponse({'ok': True, 'resultados': resultados})

@login_required
def taquilla_reprogramar_cobro(request, viaje_id, boleto_id):
    """Cobra la diferencia y hace el cambio de boleto."""
    if not hasattr(request.user, 'usuarioempresa'):
        return redirect('core:inicio')

    viaje_nuevo = get_object_or_404(Viaje, id=viaje_id)
    boleto_viejo = get_object_or_404(Boleto, id=boleto_id, estado='vendido')
    
    asiento_id_url = request.GET.get('asiento_id')
    if not asiento_id_url:
        messages.error(request, "Debe seleccionar un asiento en el mapa antes de reprogramar.")
        return redirect('core:taquilla_mapa', viaje_id=viaje_id)
    
    destino_id = request.GET.get('destino')
    origen_id = request.GET.get('origen') or request.user.usuarioempresa.oficina.id
    
    tarifa_nueva = Tarifa.objects.filter(origen_id=origen_id, destino_id=destino_id, activa=True).first()
    if not tarifa_nueva:
        messages.error(request, "No hay tarifa para el nuevo viaje.")
        return redirect('core:taquilla_mapa', viaje_id=viaje_id)

    tasa_bcv_actual = Decimal(str(obtener_parametro('107', default=0)))
    valor_seguro = Decimal(str(obtener_parametro('100', default=0)))
    
    monto_nuevo_usd = tarifa_nueva.monto_usd + valor_seguro
    monto_nuevo_bs = (monto_nuevo_usd * tasa_bcv_actual).quantize(Decimal('0.01'))
    
    # ⭐ CÁLCULO CORRECTO: Diferencia basada en Bolívares
    diferencia_bs = monto_nuevo_bs - boleto_viejo.monto_total_bs
    
    # Convertimos esa diferencia en Bolívares a Dólares (a la tasa de hoy) solo para mostrarla
    if tasa_bcv_actual > 0:
        diferencia_usd = (diferencia_bs / tasa_bcv_actual).quantize(Decimal('0.01'))
    else:
        diferencia_usd = Decimal('0.00')

    if diferencia_bs < 0:
        messages.error(request, "El boleto nuevo es más barato en Bolívares. Use la opción de generar crédito.")
        return redirect('core:taquilla_mapa', viaje_id=viaje_id)

    if request.method == 'POST':
        import json
        asiento_nuevo_id = request.POST.get('asiento_id')
        pagos_json = request.POST.get('pagos_json', '[]')
        
        try:
            pagos_lista = json.loads(pagos_json)
            
            # ⭐ VALIDACIÓN DE REDONDEO (tolerancia de 5 céntimos)
            total_pagado_bs = sum(Decimal(str(p['monto_bs'])) for p in pagos_lista)
            if pagos_lista and abs(total_pagado_bs - diferencia_bs) > Decimal('0.05'):
                messages.warning(request, f"El pago registrado (Bs. {total_pagado_bs}) no coincide con la diferencia (Bs. {diferencia_bs}). Verifique los montos.")
                return redirect(request.path + f"?origen={origen_id}&destino={destino_id}&asiento_id={asiento_nuevo_id}&numero={request.GET.get('numero')}")

            with transaction.atomic():
                # 1. Anular boleto viejo y liberar su asiento
                asiento_nuevo = Asiento.objects.select_for_update().get(id=asiento_nuevo_id)
                boleto_viejo.estado = 'reprogramado'
                boleto_viejo.save()
                asiento_viejo = boleto_viejo.asiento
                asiento_viejo.estado = 'disponible'
                asiento_viejo.save()
                
                # 2. Ocupar asiento nuevo
                asiento_nuevo.estado = 'vendido'
                asiento_nuevo.save()
                
                # 3. Crear nueva Transacción
                codigo_tx = generar_codigo_transaccion()
                transaccion = Transaccion.objects.create(
                    codigo=codigo_tx, cliente=None, viaje=viaje_nuevo, cantidad_boletos=1,
                    monto_total_usd=monto_nuevo_usd, monto_total_bs=monto_nuevo_bs, tasa_bcv=tasa_bcv_actual,
                    estado='confirmada', fecha_confirmacion=timezone.now(),
                    vendido_por=request.user, oficina_venta=request.user.usuarioempresa.oficina,
                    dispositivo_venta='Taquilla (Reprogramación)',
                    observacion=f"Reprogramación del boleto {boleto_viejo.numero_boleto}"
                )
                
                # 4. El pago del boleto viejo entra a la caja como "Reprogramación"
                Pago.objects.create(
                    transaccion=transaccion, metodo='reprogramacion',
                    monto_usd=boleto_viejo.monto_total_usd, monto_bs=boleto_viejo.monto_total_bs,
                    tasa_bcv=boleto_viejo.tasa_bcv, referencia=f"Boleto Nro: {boleto_viejo.numero_boleto}",
                    estado='confirmado', confirmado_por=request.user, fecha_confirmacion=timezone.now(),
                    observacion=f"Abono por reprogramación del boleto {boleto_viejo.numero_boleto}"
                )
                
                # 5. Los pagos de la diferencia (Efectivo, Pago Móvil)
                for p in pagos_lista:
                    Pago.objects.create(
                        transaccion=transaccion, metodo=p['metodo'], monto_usd=Decimal(p['monto_usd']),
                        monto_bs=Decimal(p['monto_bs']), tasa_bcv=tasa_bcv_actual, referencia=p.get('referencia', ''),
                        estado='confirmado', confirmado_por=request.user, fecha_confirmacion=timezone.now()
                    )
                
                # 6. Crear nuevo boleto (Hereda los datos del pasajero viejo)
                Boleto.objects.create(
                    transaccion=transaccion, viaje=viaje_nuevo, asiento=asiento_nuevo,
                    pasajero_cedula=boleto_viejo.pasajero_cedula, 
                    pasajero_nombre=boleto_viejo.pasajero_nombre, 
                    pasajero_telefono=boleto_viejo.pasajero_telefono,
                    tipo_pasajero=boleto_viejo.tipo_pasajero, 
                    monto_tarifa_usd=tarifa_nueva.monto_usd, 
                    monto_seguro_usd=valor_seguro,
                    monto_total_usd=monto_nuevo_usd, tasa_bcv=tasa_bcv_actual,
                    monto_total_bs=monto_nuevo_bs,
                    codigo_qr=generar_codigo_qr(), estado='vendido', vendido_por=request.user,
                    numero_boleto=generar_numero_boleto(request.user.usuarioempresa.oficina, es_continuo=obtener_parametro('179', default=False)),
                    observacion=f"Generado por reprogramación. Boleto original: {boleto_viejo.numero_boleto}"
                )
                
            messages.success(request, f"Reprogramación exitosa. Nuevo código: {codigo_tx}")
            return redirect('core:taquilla_confirmacion', transaccion_id=transaccion.id)
            
        except Exception as e:
            messages.error(request, f"Error al reprogramar: {str(e)}")

    return render(request, 'taquilla/reprogramar.html', {
        'boleto_viejo': boleto_viejo,
        'viaje_nuevo': viaje_nuevo,
        'tarifa_nueva': tarifa_nueva,
        'tasa_bcv': tasa_bcv_actual,
        'monto_nuevo_usd': monto_nuevo_usd,
        'monto_nuevo_bs': monto_nuevo_bs,
        'diferencia_usd': diferencia_usd,
        'diferencia_bs': diferencia_bs,
        'asiento_id': request.GET.get('asiento_id'),
    })

@require_POST
@login_required
def taquilla_bloquear_asiento_reprogramar(request):
    """Bloquea temporalmente un asiento mientras el taquillero confirma la reprogramación."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    asiento_id = request.POST.get('asiento_id')
    if not asiento_id:
        return JsonResponse({'ok': False, 'error': 'Falta el asiento.'}, status=400)
        
    try:
        with transaction.atomic():
            asiento = Asiento.objects.select_for_update().get(id=asiento_id)
            
            # ⭐ VALIDACIÓN CLAVE: Si ya está reservado por este mismo taquillero, es válido.
            if asiento.estado == 'reservado' and asiento.reservado_por == request.user:
                return JsonResponse({'ok': True, 'mensaje': 'Asiento ya reservado por usted.'})
            
            if asiento.estado != 'disponible':
                return JsonResponse({'ok': False, 'error': 'El asiento ya fue tomado por otro usuario.'}, status=400)
                
            # Lo bloqueamos por 5 minutos (parámetro 171)
            minutos = int(obtener_parametro('171', default=5))
            vence = timezone.now() + timedelta(minutes=minutos)
            
            asiento.estado = 'reservado'
            asiento.reservado_por = request.user
            asiento.reservado_hasta = vence
            asiento.save()
            
        return JsonResponse({'ok': True, 'vence': vence.isoformat()})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@require_POST
@login_required
def taquilla_liberar_asiento_reprogramar(request):
    """Libera el asiento si el taquillero cancela la operación."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    asiento_id = request.POST.get('asiento_id')
    if not asiento_id:
        return JsonResponse({'ok': False, 'error': 'Falta el asiento.'}, status=400)
        
    try:
        with transaction.atomic():
            asiento = Asiento.objects.select_for_update().filter(
                id=asiento_id, estado='reservado', reservado_por=request.user
            ).first()
            
            if asiento:
                asiento.estado = 'disponible'
                asiento.reservado_por = None
                asiento.reservado_hasta = None
                asiento.save()
                
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@login_required
def taquilla_api_asientos_disponibles_bloquear(request):
    """Devuelve los asientos disponibles para bloquear."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    viaje_id = request.GET.get('viaje_id')
    if not viaje_id:
        return JsonResponse({'ok': False, 'error': 'Falta viaje_id'}, status=400)
        
    # Solo asientos disponibles y de tipo 'asiento'
    asientos = Asiento.objects.filter(
        viaje_id=viaje_id, estado='disponible', tipo='asiento'
    ).exclude(numero='').order_by('numero')
    
    data = [{
        'asiento_id': a.id,
        'asiento_numero': a.numero,
    } for a in asientos]
    
    return JsonResponse({'ok': True, 'asientos': data})


@require_POST
@login_required
def taquilla_api_bloquear_asientos(request):
    """Bloquea los asientos seleccionados."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    asientos_ids = request.POST.getlist('asientos_ids[]')
    if not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'No se seleccionaron asientos.'}, status=400)
        
    try:
        with transaction.atomic():
            asientos = Asiento.objects.select_for_update().filter(
                id__in=asientos_ids, estado='disponible'
            )
            
            bloqueados = 0
            for asiento in asientos:
                asiento.estado = 'bloqueado'
                asiento.save()
                
                MovimientoAsiento.objects.create(
                    asiento=asiento, tipo='bloqueo',
                    estado_anterior='disponible', estado_nuevo='bloqueado',
                    usuario=request.user,
                    motivo='Asiento bloqueado desde la taquilla (posible falla mecánica).'
                )
                bloqueados += 1
                
        return JsonResponse({'ok': True, 'mensaje': f'{bloqueados} asiento(s) bloqueado(s) exitosamente.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@login_required
def taquilla_api_asientos_bloqueados(request):
    """Devuelve los asientos bloqueados para poder desbloquearlos."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    viaje_id = request.GET.get('viaje_id')
    if not viaje_id:
        return JsonResponse({'ok': False, 'error': 'Falta viaje_id'}, status=400)
        
    asientos = Asiento.objects.filter(
        viaje_id=viaje_id, estado='bloqueado'
    ).exclude(numero='').order_by('numero')  
    
    data = [{
        'asiento_id': a.id,
        'asiento_numero': a.numero,
    } for a in asientos]
    
    return JsonResponse({'ok': True, 'asientos': data})


@require_POST
@login_required
def taquilla_api_desbloquear_asientos(request):
    """Desbloquea los asientos seleccionados."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    asientos_ids = request.POST.getlist('asientos_ids[]')
    if not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'No se seleccionaron asientos.'}, status=400)
        
    try:
        with transaction.atomic():
            asientos = Asiento.objects.select_for_update().filter(
                id__in=asientos_ids, estado='bloqueado'
            )
            
            desbloqueados = 0
            for asiento in asientos:
                asiento.estado = 'disponible'
                asiento.save()
                
                MovimientoAsiento.objects.create(
                    asiento=asiento, tipo='desbloqueo',
                    estado_anterior='bloqueado', estado_nuevo='disponible',
                    usuario=request.user,
                    motivo='Asiento desbloqueado desde la taquilla.'
                )
                desbloqueados += 1
                
        return JsonResponse({'ok': True, 'mensaje': f'{desbloqueados} asiento(s) desbloqueado(s) exitosamente.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)

@login_required
def taquilla_liquidar(request):
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos.")
        return redirect('core:inicio')

    porcentaje_empresa = Decimal(str(obtener_parametro('201', default=20)))
    
    if request.method == 'POST':
        bus_id = request.POST.get('bus_id')
        viaje_id = request.POST.get('viaje_id')
        conductores_nombres = request.POST.get('conductores_nombres')
        observacion = request.POST.get('observacion', '')
        
        if not bus_id or not viaje_id:
            messages.error(request, "Debe seleccionar un bus y un viaje.")
            return redirect('core:taquilla_liquidar')
        
        try:
            with transaction.atomic():
                bus = Bus.objects.get(id=bus_id)
                viaje = Viaje.objects.get(id=viaje_id)
                
                boletos = Boleto.objects.filter(
                    viaje=viaje, estado='usado',
                    transaccion__oficina_venta=empleado.oficina
                )
                
                if not boletos.exists():
                    messages.warning(request, "No hay boletos escaneados para liquidar.")
                    return redirect('core:taquilla_liquidar')
                
                total_bruto_usd = sum(b.monto_total_usd for b in boletos)
                tasa_bcv = Decimal(str(obtener_parametro('107', default=0)))
                total_bruto_bs = total_bruto_usd * tasa_bcv
                monto_empresa_usd = total_bruto_usd * (porcentaje_empresa / 100)
                
                gastos_antes = request.POST.getlist('gasto_antes_monto[]')
                gastos_despues = request.POST.getlist('gasto_despues_monto[]')
                conceptos_antes = request.POST.getlist('gasto_antes_concepto[]')
                conceptos_despues = request.POST.getlist('gasto_despues_concepto[]')
                
                total_gastos_antes = sum(Decimal(m) for m in gastos_antes if m)
                total_gastos_despues = sum(Decimal(m) for m in gastos_despues if m)
                
                neto_usd = total_bruto_usd - total_gastos_antes - monto_empresa_usd - total_gastos_despues
                neto_bs = neto_usd * tasa_bcv
                
                ultima_liq = Liquidacion.objects.filter(oficina_liquidacion=empleado.oficina).order_by('-id').first()
                nuevo_num = int(ultima_liq.numero_liquidacion.split('-')[1]) + 1 if ultima_liq else 1
                numero_liq = f"{empleado.oficina.codigo}-{nuevo_num:06d}"
                
                liquidacion = Liquidacion.objects.create(
                    numero_liquidacion=numero_liq, viaje=viaje, bus=bus,
                    oficina_liquidacion=empleado.oficina, dueno=bus.empresa,
                    conductores_nombres=conductores_nombres,
                    total_bruto_usd=total_bruto_usd, total_bruto_bs=total_bruto_bs,
                    porcentaje_empresa=porcentaje_empresa, monto_porcentaje_empresa_usd=monto_empresa_usd,
                    total_gastos_antes_usd=total_gastos_antes, total_gastos_despues_usd=total_gastos_despues,
                    neto_a_pagar_usd=neto_usd, neto_a_pagar_bs=neto_bs,
                    liquidado_por=request.user, observacion=observacion
                )
                
                for i, c in enumerate(conceptos_antes):
                    m = gastos_antes[i] if i < len(gastos_antes) else 0
                    if m: GastoLiquidacion.objects.create(liquidacion=liquidacion, concepto=c, monto_usd=Decimal(m), tipo='antes')
                for i, c in enumerate(conceptos_despues):
                    m = gastos_despues[i] if i < len(gastos_despues) else 0
                    if m: GastoLiquidacion.objects.create(liquidacion=liquidacion, concepto=c, monto_usd=Decimal(m), tipo='despues')
                
                boletos.update(estado='liquidado')
                
                messages.success(request, f"Liquidación {numero_liq} generada exitosamente.")
                return redirect('core:taquilla_liquidacion_detalle', liquidacion.id)
        except Exception as e:
            messages.error(request, f"Error al liquidar: {str(e)}")
            return redirect('core:taquilla_liquidar')
    
    hoy = timezone.localtime(timezone.now()).date()
    viajes = Viaje.objects.filter(fecha=hoy, estado='programado').order_by('hora')
    viaje_id_preseleccionado = request.GET.get('viaje_id')
    
    return render(request, 'taquilla/liquidar.html', {
        'viajes': viajes,
        'porcentaje_empresa': porcentaje_empresa,
        'viaje_id_preseleccionado': viaje_id_preseleccionado,
    })
    
@login_required
def api_datos_liquidacion(request):
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
    
    viaje_id = request.GET.get('viaje_id')
    if not viaje_id:
        return JsonResponse({'ok': False, 'error': 'Falta viaje_id'}, status=400)
    
    try:
        empleado = request.user.usuarioempresa
        viaje = Viaje.objects.get(id=viaje_id)
        
        # Datos del bus
        numero_bus = viaje.bus.numero_bus or 'Sin número'
        dueno = viaje.bus.empresa.nombre if viaje.bus.empresa else 'Sin dueño'
        
        conductores = ', '.join([c.nombre for c in viaje.bus.conductores.all()])
        
        # Boletos escaneados (usados) de esta oficina para este viaje
        boletos = Boleto.objects.filter(
            viaje=viaje, 
            estado='usado',
            transaccion__oficina_venta=empleado.oficina
        ).select_related('asiento')
        
        boletos_data = [{
            'asiento': b.asiento.numero,
            'nombre': b.pasajero_nombre,
            'cedula': b.pasajero_cedula,
            'monto_total_usd': float(b.monto_total_usd),
        } for b in boletos]
        
        return JsonResponse({
            'ok': True,
            'bus_id': viaje.bus.id,  # ⭐ NUEVO: Necesario para el formulario
            'numero_bus': numero_bus,
            'dueno': dueno,
            'conductores': conductores,
            'boletos': boletos_data
        })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
        
# ============================================================
# MÓDULO DE ABORDAJE Y CHEQUEO QR
# ============================================================
@login_required
def taquilla_escaner(request):
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos.")
        return redirect('core:inicio')

    hoy = timezone.localtime(timezone.now()).date()
    viajes = Viaje.objects.filter(
        fecha=hoy, estado='programado', cerrado_venta=False
    ).select_related('ruta', 'bus').order_by('hora')
    
    viaje_id_preseleccionado = request.GET.get('viaje_id')
    
    # ⭐ NUEVO: Contar los boletos ya abordados (usados) para este viaje
    total_abordados = 0
    if viaje_id_preseleccionado:
        total_abordados = Boleto.objects.filter(viaje_id=viaje_id_preseleccionado, estado='usado').count()
    
    return render(request, 'taquilla/escaner_qr.html', {
        'viajes': viajes,
        'viaje_preseleccionado': viaje_id_preseleccionado,
        'total_abordados': total_abordados, # ⭐ Se lo pasamos al template
    })


@require_POST
@login_required
def api_validar_qr(request):
    """Valida un boleto (QR o número manual) para abordaje."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
    
    codigo_qr = request.POST.get('codigo_qr', '').strip()
    numero_boleto_manual = request.POST.get('numero_boleto', '').strip()
    viaje_id = request.POST.get('viaje_id')
    
    if not (codigo_qr or numero_boleto_manual):
        return JsonResponse({'ok': False, 'error': 'Debe escanear el QR o escribir el número de boleto.'}, status=400)
        
    try:
        with transaction.atomic():
            boleto = None
            if codigo_qr:
                boleto = Boleto.objects.select_for_update().filter(codigo_qr=codigo_qr).first()
            if not boleto and numero_boleto_manual:
                boleto = Boleto.objects.select_for_update().filter(numero_boleto=numero_boleto_manual).first()
            
            if not boleto:
                return JsonResponse({'ok': False, 'error': 'Boleto no encontrado. Verifique el código o el número.'})
            
            # Validar que sea para el viaje que está en puerta
            if str(boleto.viaje.id) != str(viaje_id):
                return JsonResponse({'ok': False, 'error': f'Este boleto es para otro viaje (Ruta: {boleto.viaje.ruta.nombre} - {boleto.viaje.hora}).'})
            
            # Validar que no haya sido usado ni liquidado
            if boleto.estado == 'usado':
                return JsonResponse({'ok': False, 'error': 'Este boleto ya fue abordado anteriormente.'})
            if boleto.estado == 'liquidado':
                return JsonResponse({'ok': False, 'error': 'Este boleto ya fue liquidado (viaje cerrado). No puede abordar.'})
            if boleto.estado != 'vendido':
                return JsonResponse({'ok': False, 'error': f'El boleto está en estado: {boleto.get_estado_display()}. No se puede abordar.'})
            
            # ¡Todo bien! Marcamos como usado (Abordado)
            boleto.estado = 'usado'
            boleto.fecha_chequeo = timezone.now()
            boleto.chequeado_por = request.user
            boleto.save()
            
            # ⭐ NUEVO: Actualizar el estado del asiento también
            asiento = boleto.asiento
            asiento.estado = 'usado'
            asiento.save()
            
            # Auditoría
            MovimientoAsiento.objects.create(
                asiento=boleto.asiento, tipo='chequeo',
                estado_anterior='vendido', estado_nuevo='usado',
                usuario=request.user, motivo=f'Abordaje por QR/Nro Boleto. Boleto: {boleto.numero_boleto}', boleto_relacionado=boleto
            )
            
            return JsonResponse({
                'ok': True, 
                'mensaje': '✅ Abordado correctamente',
                'pasajero': boleto.pasajero_nombre,
                'cedula': boleto.pasajero_cedula,
                'asiento': boleto.asiento.numero,
                'boleto': boleto.numero_boleto
            })
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)


@require_POST
@login_required
def taquilla_cerrar_venta(request, viaje_id):
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
    try:
        viaje = Viaje.objects.get(id=viaje_id)
        if viaje.cerrado_venta:
            return JsonResponse({'ok': False, 'error': 'La venta ya está cerrada.'}, status=400)
        viaje.cerrado_venta = True
        viaje.save()
        return JsonResponse({'ok': True, 'mensaje': 'Venta cerrada exitosamente.'})
    except Viaje.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Viaje no encontrado.'}, status=404)
        
@login_required
def taquilla_liquidacion_detalle(request, liquidacion_id):
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos.")
        return redirect('core:inicio')

    liquidacion = get_object_or_404(Liquidacion, id=liquidacion_id, oficina_liquidacion=empleado.oficina)
    gastos = liquidacion.gastos.all().order_by('tipo')
    
    return render(request, 'taquilla/liquidacion_detalle.html', {
        'liquidacion': liquidacion,
        'gastos': gastos,
    })

@login_required
def taquilla_consultar_boleto(request):
    try:
        empleado = request.user.usuarioempresa
    except UsuarioEmpresa.DoesNotExist:
        messages.error(request, "No tiene permisos.")
        return redirect('core:inicio')

    boleto = None
    movimientos = []
    busqueda = request.GET.get('q', '').strip()

    if busqueda:
        boleto = Boleto.objects.filter(numero_boleto__iexact=busqueda).first()
        if boleto:
            movimientos = MovimientoAsiento.objects.filter(
                boleto_relacionado=boleto
            ).order_by('-fecha_hora')

    # ⭐ ACTIVAR (Solo si está USADO y con clave del usuario actual)
    if request.method == 'POST' and request.POST.get('accion') == 'activar':
        boleto_id = request.POST.get('boleto_id')
        password = request.POST.get('password')
        boleto = get_object_or_404(Boleto, id=boleto_id)

        if boleto.estado != 'usado':
            messages.error(
                request, 
                f"No se puede reactivar el boleto {boleto.numero_boleto}. "
                f"Estado actual: {boleto.get_estado_display()}. "
                f"Solo se reactivan boletos chequeados/abordados."
            )
            return redirect('core:taquilla_consultar_boleto')

        if not request.user.check_password(password):
            messages.error(request, "Clave incorrecta. No puede reactivar el boleto.")
            return redirect('core:taquilla_consultar_boleto')

        with transaction.atomic():
            boleto.estado = 'vendido'
            boleto.fecha_chequeo = None
            boleto.chequeado_por = None
            boleto.save()

            asiento = boleto.asiento
            asiento.estado = 'vendido'
            asiento.save()

            MovimientoAsiento.objects.create(
                asiento=asiento, tipo='desbloqueo',
                estado_anterior='usado', estado_nuevo='vendido',
                usuario=request.user,
                motivo=f'Boleto reactivado por el taquillero. Boleto: {boleto.numero_boleto}',
                boleto_relacionado=boleto
            )

        messages.success(request, f"Boleto {boleto.numero_boleto} reactivado exitosamente.")
        return redirect('core:taquilla_consultar_boleto')

    # ⭐ ANULAR (Solo si está VENDIDO, es de HOY y clave del vendedor original)
    if request.method == 'POST' and request.POST.get('accion') == 'anular':
        boleto_id = request.POST.get('boleto_id')
        password = request.POST.get('password')
        boleto = get_object_or_404(Boleto, id=boleto_id)

        if boleto.estado != 'vendido':
            messages.error(
                request, 
                f"No se puede anular el boleto {boleto.numero_boleto}. "
                f"Estado actual: {boleto.get_estado_display()}. "
                f"Solo se anulan boletos con estado 'Vendido'."
            )
            return redirect('core:taquilla_consultar_boleto')

        # Validación contable: Solo se anulan boletos vendidos HOY
        hoy = timezone.localtime(timezone.now()).date()
        fecha_venta_boleto = timezone.localtime(boleto.fecha_venta).date()
        if fecha_venta_boleto < hoy:
            messages.error(
                request, 
                f"No se puede anular el boleto {boleto.numero_boleto}. "
                f"Fue vendido el {fecha_venta_boleto.strftime('%d/%m/%Y')} y la caja de esa fecha ya fue cerrada. "
                f"Solo se pueden anular boletos vendidos el día de HOY."
            )
            return redirect('core:taquilla_consultar_boleto')

        # Validar clave del vendedor original
        if not boleto.vendido_por:
            messages.error(request, "Este boleto no tiene un vendedor registrado.")
            return redirect('core:taquilla_consultar_boleto')

        if not boleto.vendido_por.check_password(password):
            messages.error(request, "Clave incorrecta. Solo el taquillero que vendió el boleto puede anularlo.")
            return redirect('core:taquilla_consultar_boleto')

        with transaction.atomic():
            boleto.estado = 'anulado' # ⭐ CAMBIADO DE 'cancelado' a 'anulado'
            boleto.save()

            asiento = boleto.asiento
            asiento.estado = 'disponible'
            asiento.reservado_por = None
            asiento.reservado_hasta = None
            asiento.save()

            MovimientoAsiento.objects.create(
                asiento=asiento, tipo='cancelacion',
                estado_anterior='vendido', estado_nuevo='disponible',
                usuario=request.user,
                motivo=f'Boleto anulado por el taquillero original. Boleto: {boleto.numero_boleto}',
                boleto_relacionado=boleto
            )

        messages.success(request, f"Boleto {boleto.numero_boleto} anulado exitosamente.")
        return redirect('core:taquilla_consultar_boleto')

    return render(request, 'taquilla/consultar_boleto.html', {
        'boleto': boleto,
        'movimientos': movimientos,
        'busqueda': busqueda,
    })
    
@login_required
def taquilla_api_boletos_vendidos(request):
    """Devuelve la lista de boletos en estado 'vendido' para el modal de liberación."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    viaje_id = request.GET.get('viaje_id')
    if not viaje_id:
        return JsonResponse({'ok': False, 'error': 'Falta viaje_id'}, status=400)
        
    # ⭐ FILTRO MEJORADO: Solo boletos 'vendidos' CUYO ASIENTO siga 'vendido'
    boletos = Boleto.objects.filter(
        viaje_id=viaje_id, 
        estado='vendido',
        asiento__estado='vendido'  # <--- ESTA ES LA CLAVE
    ).select_related('asiento').order_by('asiento__numero')
    
    data = [{
        'boleto_id': b.id,
        'asiento_numero': b.asiento.numero,
        'asiento_id': b.asiento.id,
        'pasajero_nombre': b.pasajero_nombre,
        'pasajero_cedula': b.pasajero_cedula,
        'numero_boleto': b.numero_boleto
    } for b in boletos]
    
    return JsonResponse({'ok': True, 'boletos': data})


@require_POST
@login_required
def taquilla_api_liberar_puestos_vendidos(request):
    """Libera los asientos de boletos que están en estado 'vendido' (Lista de Espera)."""
    if not hasattr(request.user, 'usuarioempresa'):
        return JsonResponse({'ok': False, 'error': 'No autorizado'}, status=403)
        
    asientos_ids = request.POST.getlist('asientos_ids[]')
    if not asientos_ids:
        return JsonResponse({'ok': False, 'error': 'No se seleccionaron asientos.'}, status=400)
        
    try:
        with transaction.atomic():
            # Buscamos los boletos estrictamente en estado 'vendido'
            boletos = Boleto.objects.select_for_update().filter(
                asiento_id__in=asientos_ids, estado='vendido'
            )
            
            liberados = 0
            for boleto in boletos:
                # ⭐ EL BOLETO SE QUEDA EN 'VENDIDO', NO LO TOCAMOS ⭐
                
                # Liberar el asiento (vuelve a estar disponible)
                asiento = boleto.asiento
                asiento.estado = 'disponible'
                asiento.reservado_por = None
                asiento.reservado_hasta = None
                asiento.save()
                
                # Auditoría
                MovimientoAsiento.objects.create(
                    asiento=asiento, tipo='liberacion_manual',
                    estado_anterior='vendido', estado_nuevo='disponible',
                    usuario=request.user,
                    motivo=f'Liberación de puesto (Lista de Espera). Boleto original: {boleto.numero_boleto}',
                    boleto_relacionado=boleto
                )
                liberados += 1
                
        return JsonResponse({'ok': True, 'mensaje': f'{liberados} puesto(s) liberado(s) exitosamente.'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
