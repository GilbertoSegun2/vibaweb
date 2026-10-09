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
        

@register.filter
def formato_bs(valor):
    """
    Formatea un número en formato venezolano: 30.884,04
    - Punto como separador de miles
    - Coma como separador decimal
    """
    try:
        numero = float(valor)
        # Formatear con formato US (1,234.56) y luego intercambiar
        formateado = f"{numero:,.2f}"
        # Intercambiar: primero X por los puntos, luego comas, luego X por puntos
        formateado = formateado.replace(',', 'X').replace('.', ',').replace('X', '.')
        return formateado
    except (ValueError, TypeError):
        return valor
        
@register.filter
def formato_cedula(cedula):
    if not cedula:
        return ''
    
    cedula_str = str(cedula).upper().strip()
    
    letra = ''
    if cedula_str and cedula_str[0].isalpha():
        letra = cedula_str[0]
        cedula_str = cedula_str[1:]
    
    # ⭐ LIMPIAR: quitar todo lo que no sea dígito antes de formatear
    solo_numeros = ''.join(c for c in cedula_str if c.isdigit())
    
    if solo_numeros:
        partes = []
        while len(solo_numeros) > 3:
            partes.insert(0, solo_numeros[-3:])
            solo_numeros = solo_numeros[:-3]
        partes.insert(0, solo_numeros)
        numero_formateado = '.'.join(partes)
    else:
        numero_formateado = cedula_str
    
    return f"{letra}-{numero_formateado}" if letra else numero_formateado

@register.filter
def formato_telefono(telefono):
    """
    Muestra un teléfono con formato venezolano.
    Ejemplo: '04141234567' → '0414-1234567'
             '584141234567' → '+58 414-1234567'
    """
    if not telefono:
        return ''
    
    tel = ''.join(c for c in str(telefono) if c.isdigit())
    
    if len(tel) == 11 and tel.startswith('0'):
        # Formato local: 0414-1234567
        return f"{tel[:4]}-{tel[4:]}"
    elif len(tel) == 12 and tel.startswith('58'):
        # Formato internacional: +58 414-1234567
        return f"+58 {tel[2:5]}-{tel[5:]}"
    elif len(tel) == 10:
        # Sin 0 inicial: 414-1234567
        return f"{tel[:3]}-{tel[3:]}"
    else:
        # Si no encaja en ningún patrón, devolver como está
        return tel
