"""Filtros personalizados para templates."""
from django import template
from core.utils import convertir_a_bs, obtener_tasa_bcv

register = template.Library()


@register.filter
def convertir_bs(monto_usd):
    """Convierte un monto en USD a Bs. formateado."""
    monto_bs = convertir_a_bs(monto_usd)
    if monto_bs is None:
        return "---"
    # Formatear con separador de miles y 2 decimales
    return f"{monto_bs:,.2f}"


@register.filter
def tasa_actual(value=None):
    """Devuelve la tasa BCV actual formateada."""
    tasa = obtener_tasa_bcv()
    if tasa is None:
        return "No configurada"
    return f"{tasa:,.2f}"
    
@register.filter
def hora_am_pm(hora):
    """
    Formatea una hora en formato 12h con a.m./p.m. en minúsculas y con puntos.
    Ej: 19:30 → '07:30 p.m.'
    """
    if not hora:
        return ''
    try:
        h = hora.hour
        m = hora.minute
        
        periodo = 'a.m.' if h < 12 else 'p.m.'
        
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        
        return f"{h12:02d}:{m:02d} {periodo}"
    except (AttributeError, ValueError):
        return str(hora)
