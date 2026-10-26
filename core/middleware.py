from .utils import obtener_parametro

class SessionTimeoutMiddleware:
    """
    Ajusta dinámicamente el timeout de la sesión según el rol:
    - Cliente web: parámetro 140 (120 min)
    - Taquillero: parámetro 173 (15 min)
    - Si es 0: la sesión muere al cerrar el navegador.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        rutas_excluidas = ['/login/', '/logout/', '/registro/']
        if any(request.path.startswith(ruta) for ruta in rutas_excluidas):
            return self.get_response(request)
        
        if request.user.is_authenticated:
            # ⭐ VERIFICAR SI ES EMPLEADO (TAQUILLERO)
            es_empleado = getattr(request.user, 'usuarioempresa', None) is not None
            
            if es_empleado:
                # Taquillero: 15 min por defecto
                try:
                    minutos = int(obtener_parametro('173', default=15))
                except (ValueError, TypeError):
                    minutos = 15
            else:
                # Cliente web: 120 min por defecto
                try:
                    minutos = int(obtener_parametro('140', default=120))
                except (ValueError, TypeError):
                    minutos = 120
            
            if minutos <= 0:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(minutos * 60)
        
        return self.get_response(request)

class SesionUnicaMiddleware:
    """
    Garantiza que cada usuario-web (Cliente) tenga solo una sesión activa.
    Exento: Admin, staff y Usuarios de Empresa (Taquilleros).
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        rutas_excluidas = ['/login/', '/logout/', '/registro/', '/admin/']
        if any(request.path.startswith(ruta) for ruta in rutas_excluidas):
            return self.get_response(request)
        
        if request.user.is_authenticated:
            user = request.user
            
            # Admin/staff exento
            if user.is_staff or user.is_superuser:
                return self.get_response(request)
            
            # ⭐ EMPLEADOS (TAQUILLEROS) EXENTOS DE LA RESTRICCIÓN
            if getattr(user, 'usuarioempresa', None):
                return self.get_response(request)
            
            # Solo aplica a clientes (usuarios-web)
            cliente = getattr(user, 'cliente', None)
            if not cliente:
                return self.get_response(request)
            
            try:
                from .models import SesionActiva
                from django.utils import timezone
                from django.shortcuts import redirect
                from django.contrib.auth import logout as auth_logout
                from django.contrib import messages
                
                sesion = SesionActiva.objects.filter(user=user).first()
                current_key = request.session.session_key
                
                if sesion and sesion.session_key != current_key:
                    auth_logout(request)
                    messages.warning(
                        request,
                        "Estimado cliente: su cuenta fue abierta en otro dispositivo. "
                        "Por seguridad, esta sesión ha sido cerrada automáticamente."
                    )
                    return redirect('core:login')
                
                if sesion:
                    SesionActiva.objects.filter(pk=sesion.pk).update(
                        ultima_actividad=timezone.now()
                    )
            except Exception:
                pass
        
        return self.get_response(request)

class NoCacheMiddleware:
    """
    Agrega headers anti-caché a todas las páginas HTML.
    
    Esto evita que el navegador (especialmente en celulares)
    guarde las páginas en caché y las muestre al dar "Atrás"
    después de cerrar sesión.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Solo agregar headers a páginas HTML
        content_type = response.get('Content-Type', '')
        if 'text/html' in content_type:
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        
        return response
        
from django.shortcuts import render
from django.utils import timezone

class SuscripcionMiddleware:
    """
    Bloquea el sistema si la suscripción está vencida.
    - Al empleado: Le dice que el sistema está suspendido (para que presione a la empresa a pagar).
    - Al cliente-web: Le dice que hay "mantenimiento" (nunca le dice que la empresa no ha pagado).
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Rutas que NUNCA se bloquean (Admin, Login, API)
        rutas_libres = ['/admin/', '/login/', '/registro/', '/api/']
        if any(request.path.startswith(ruta) for ruta in rutas_libres):
            return self.get_response(request)

        # 2. Rutas donde el cliente-web compra
        rutas_cliente_web = ['/', '/viajes/', '/pasajeros/', '/pago/', '/pasarela-virtual/', '/confirmacion/', '/mis-boletos/', '/ayuda/']
        es_cliente_web = any(request.path.startswith(ruta) for ruta in rutas_cliente_web)

        # 3. Verificar el estado de la suscripción
        try:
            from .models import Suscripcion
            suscripcion = Suscripcion.objects.first() # Asumiendo 1 empresa por proyecto
            
            if suscripcion:
                # Si está inactiva manualmente o vencida
                if not suscripcion.activa or suscripcion.dias_para_vencer() < 0:
                    
                    # Si es cliente-web, mostramos mensaje de "Mantenimiento"
                    if es_cliente_web:
                        return render(request, 'mantenimiento_cliente.html', status=503)
                    
                    # Si es empleado (taquilla), mostramos el bloqueo real
                    if request.user.is_authenticated:
                        es_empleado = getattr(request.user, 'usuarioempresa', None) is not None
                        if es_empleado:
                            return render(request, 'suscripcion_suspendida.html', status=403)
                            
        except Exception:
            pass # Si falla algo, no bloqueamos para no romper el sitio

        return self.get_response(request)
