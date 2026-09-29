"""Context processors de la app core."""
from .utils import obtener_tasa_bcv
from django.utils import timezone
from datetime import datetime, timedelta


def tasa_bcv(request):
    """Agrega la tasa BCV actual a todos los templates."""
    return {
        'tasa_bcv': obtener_tasa_bcv(),
    }


def expiracion_reserva(request):
    """Agrega la fecha de expiración de la reserva (si existe)."""
    reserva_inicio_str = request.session.get('reserva_inicio')
    if not reserva_inicio_str:
        return {'expiracion_iso': None}
    
    try:
        reserva_inicio = datetime.fromisoformat(reserva_inicio_str)
        from .utils import obtener_parametro
        minutos = int(obtener_parametro('101', default=10))
        expiracion = reserva_inicio + timedelta(minutes=minutos)
        return {'expiracion_iso': expiracion.isoformat()}
    except (ValueError, TypeError):
        return {'expiracion_iso': None}
