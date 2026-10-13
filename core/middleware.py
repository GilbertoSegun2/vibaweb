from .utils import obtener_parametro


class SessionTimeoutMiddleware:
    """
    Ajusta dinámicamente el timeout de la sesión según el parámetro 140.
    
    - Si el parámetro es 0: la sesión muere al cerrar el navegador.
    - Si es mayor a 0: la sesión muere tras N minutos de inactividad.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # ⭐ EXCLUIR rutas de autenticación
        # El login/logout cambian el sessionid durante la petición,
        # y modificar la sesión aquí rompe el guardado.
        rutas_excluidas = ['/login/', '/logout/', '/registro/']
        if any(request.path.startswith(ruta) for ruta in rutas_excluidas):
            return self.get_response(request)
        
        if request.user.is_authenticated:
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
    Garantiza que cada usuario-web tenga solo una sesión activa.
    
    Exento: admin/staff (pueden tener múltiples sesiones)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # ⭐ EXCLUIR rutas que manejan su propia sesión
        rutas_excluidas = ['/login/', '/logout/', '/registro/', '/admin/']
        if any(request.path.startswith(ruta) for ruta in rutas_excluidas):
            return self.get_response(request)
        
        if request.user.is_authenticated:
            user = request.user
            
            # Admin/staff exento
            if user.is_staff or user.is_superuser:
                return self.get_response(request)
            
            # Solo aplica a clientes (usuarios-web)
            cliente = getattr(user, 'cliente', None)
            if not cliente:
                return self.get_response(request)
            
            # Verificar sesión activa
            try:
                from .models import SesionActiva
                from django.utils import timezone
                from django.shortcuts import redirect
                from django.contrib.auth import logout as auth_logout
                from django.contrib import messages
                
                sesion = SesionActiva.objects.filter(user=user).first()
                current_key = request.session.session_key
                
                if sesion and sesion.session_key != current_key:
                    # Otra sesión tomó el control
                    auth_logout(request)
                    messages.warning(
                        request,
                        "Estimado cliente: su cuenta fue abierta en otro dispositivo. "
                        "Por seguridad, esta sesión ha sido cerrada automáticamente. "
                        "Si no reconoce esta acción, por favor contacte a la empresa."
                    )
                    return redirect('core:login')
                
                # Actualizar última actividad
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
        
