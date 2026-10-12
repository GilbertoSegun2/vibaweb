"""
WSGI config for vibaweb_proyecto project.

⭐ IMPORTANTE:
- El monkey patch de gevent SOLO se aplica en Linux (Railway).
- En Windows (desarrollo local), se salta porque:
  1. `runserver` usa threading y el patch lo rompe
  2. gunicorn (con gevent) no funciona en Windows de todas formas
"""

import os

# ⭐ Monkey patch SOLO en Linux (producción)
if os.name != 'nt':  # 'nt' = Windows, 'posix' = Linux/Mac
    from gevent import monkey
    monkey.patch_all()

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vibaweb_proyecto.settings')

application = get_wsgi_application()
