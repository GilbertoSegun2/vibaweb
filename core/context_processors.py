# ~ ¿Qué es un context processor? Es una función que Django ejecuta 
# ~ antes de renderizar cualquier template, y que agrega variables 
# ~ al contexto. Así, en lugar de pasar la tasa desde cada vista, Django 
# ~ la pasa automáticamente a todos los templates.

"""Context processors de la app core."""
from .utils import obtener_tasa_bcv


def tasa_bcv(request):
    """
    Agrega la tasa BCV actual a todos los templates.
    Disponible como {{ tasa_bcv }}.
    """
    return {
        'tasa_bcv': obtener_tasa_bcv(),
    }
