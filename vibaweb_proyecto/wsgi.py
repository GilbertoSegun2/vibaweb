"""
WSGI config for vibaweb_proyecto project.

⭐ IMPORTANTE: El monkey patch de gevent DEBE ejecutarse ANTES
de cualquier otra importación. Esto convierte las librerías
bloqueantes (MySQL, socket, etc.) en cooperativas para que
gevent pueda cambiar de tarea mientras esperan.
"""

# ⭐ MONKEY PATCH - PRIMERA LÍNEA, ANTES DE TODO
from gevent import monkey
monkey.patch_all()

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vibaweb_proyecto.settings')

application = get_wsgi_application()
