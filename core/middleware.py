from .utils import obtener_parametro


class SessionTimeoutMiddleware:
    """
    Ajusta dinámicamente el timeout de la sesión según el parámetro 140.
    
    - Si el parámetro es 0: la sesión muere al cerrar el navegador.
    - Si es mayor a 0: la sesión muere tras N minutos de inactividad.
    - Cada clic del usuario renueva el reloj (SESSION_SAVE_EVERY_REQUEST).
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                minutos = int(obtener_parametro('140', default=120))
            except (ValueError, TypeError):
                minutos = 120  # fallback seguro
            
            if minutos <= 0:
                request.session.set_expiry(0)  # muere al cerrar navegador
            else:
                request.session.set_expiry(minutos * 60)  # muere tras N min
        
        return self.get_response(request)



class SesionUnicaMiddleware:
    """
    Garantiza que cada usuario-web tenga solo una sesión activa.
    
    Si el usuario abre sesión en otro dispositivo, la sesión antigua
    se cierra automáticamente con un mensaje al usuario.
    
    Exento: admin/staff (pueden tener múltiples sesiones)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
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
                        "Si no reconoce esta acción, por favor contactenos."
                    )
                    return redirect('core:login')
                
                # Actualizar última actividad (sin reescribir todo el objeto)
                if sesion:
                    SesionActiva.objects.filter(pk=sesion.pk).update(
                        ultima_actividad=timezone.now()
                    )
            except Exception:
                # Si algo falla, no bloquear la navegación
                pass
        
        return self.get_response(request)
