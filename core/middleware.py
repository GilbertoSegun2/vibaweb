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
