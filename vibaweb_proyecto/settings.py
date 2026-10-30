"""
Django settings for vibaweb_proyecto project.
...
"""

from pathlib import Path
import os
import dj_database_url
from decouple import config, Csv
import urllib.parse as urlparse
from urllib.parse import urlparse

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-+m#(j1y6f$v=)7q0w$e4c^z!s@l^&j*8g5r_2&x=!k9#b3p+t')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost', cast=Csv())

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    
    # Terceros
    'pwa',
    'import_export',
    
    # Local
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # ⭐ MIDDLEWARES PERSONALIZADOS DE VIBA-WEB
    'core.middleware.SesionUnicaMiddleware',      # Controla sesión única
    'core.middleware.SessionTimeoutMiddleware',   # Controla inactividad
    'core.middleware.NoCacheMiddleware',          # Evita caché en páginas protegidas
    'core.middleware.LimpiarMensajesMiddleware',  # ⭐ NUEVO: Limpia mensajes viejos
    'core.middleware.LimpiarMensajesMiddleware',
]

AUTO_LOGOUT_DELAY = 120  # 15 minutos * 60 segundos
ROOT_URLCONF = 'vibaweb_proyecto.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.personalizacion',
                'core.context_processors.tasa_bcv',  # ⭐ AGREGAR ESTA LÍNEA
            ],
        },
    },
]

WSGI_APPLICATION = 'vibaweb_proyecto.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# Si estamos en producción (Railway) usa la URL de la base de datos
if 'DATABASE_URL' in os.environ:
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, conn_health_checks=True)
    }
else:
    # Base de datos local (desarrollo)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME', default='vibaweb_db'),
            'USER': config('DB_USER', default='root'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='3307'),
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'es-ve'

TIME_ZONE = 'America/Caracas'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================================
# SEGURIDAD: CONFIGURACIÓN DE SESIONES (Estilo Bancario)
# ============================================================

# ⭐ COOKIE PURA: La sesión muere cuando el usuario cierra el navegador
# Solo vive en la memoria RAM. Si cierra la ventana, la cookie desaparece.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ⭐ SEGURIDAD: La cookie solo se puede leer desde el servidor (no desde JavaScript)
# Protege contra ataques XSS.
SESSION_COOKIE_HTTPONLY = True

# ⭐ SEGURIDAD: La cookie solo viaja por HTTPS.
# En local (http://127.0.0.1) esto rompe el login, así que solo se activa en producción.
if not DEBUG:
    SESSION_COOKIE_SECURE = True

# Tiempo máximo de inactividad absoluta (2 horas por defecto)
# El middleware personalizado (SessionTimeoutMiddleware) se encarga de los 10/5 minutos.
SESSION_COOKIE_AGE = 7200

# ============================================================
# CONFIGURACIÓN CSRF (Para formularios y AJAX)
# ============================================================
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS', 
    default='http://127.0.0.1:8000,http://localhost:8000', 
    cast=Csv()
)

# Si estamos en producción (Railway), permitir el dominio real
if 'RAILWAY_ENVIRONMENT' in os.environ:
    CSRF_TRUSTED_ORIGINS += [
        'https://boletoexpreso.com',
        'https://www.boletoexpreso.com',
        'https://web-production-d0d92.up.railway.app',
    ]
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'None'

# ============================================================
# CONFIGURACIÓN PWA (django-pwa)
# ============================================================
PWA_APP_NAME = 'Viba-Web'
PWA_APP_DESCRIPTION = 'Venta de boletos de autobús en línea'
PWA_APP_THEME_COLOR = '#003366'
PWA_APP_BACKGROUND_COLOR = '#ffffff'
PWA_APP_DISPLAY = 'standalone'
PWA_APP_SCOPE = '/'
PWA_APP_ORIENTATION = 'portrait'
PWA_APP_START_URL = '/'
PWA_APP_STATUS_BAR_COLOR = 'default'
PWA_APP_ICONS = [
    {
        'src': '/static/img/pwa/icon-192x192.png',
        'sizes': '192x192'
    },
    {
        'src': '/static/img/pwa/icon-512x512.png',
        'sizes': '512x512'
    }
]
PWA_APP_ICONS_APPLE = [
    {
        'src': '/static/img/pwa/icon-192x192.png',
        'sizes': '192x192'
    }
]
PWA_APP_SPLASH_SCREEN = [
    {
        'src': '/static/img/pwa/icon-512x512.png',
        'media': '(device-width: 320px) and (device-height: 568px) and (-webkit-device-pixel-ratio: 2)'
    }
]
PWA_APP_DIR = 'ltr'
PWA_APP_LANG = 'es-VE'
PWA_SERVICE_WORKER_PATH = os.path.join(BASE_DIR, 'static/js', 'serviceworker.js')

# ============================================================
# LOGGING (Para depuración en producción)
# ============================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# ============================================================
# CONFIGURACIÓN DE CORREO ELECTRÓNICO (Resend / SMTP)
# ============================================================
# ~ EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# ~ EMAIL_HOST = 'smtp.resend.com'
# ~ EMAIL_PORT = 587
# ~ EMAIL_USE_TLS = True
# ~ EMAIL_HOST_USER = 'resend'
# ~ EMAIL_HOST_PASSWORD = config('RESEND_API_KEY', default='')
# ~ DEFAULT_FROM_EMAIL = 'Viba-Web <info@boletoexpreso.com>'
# ============================================================
# CONFIGURACIÓN DE CORREO (Resend / SMTP)
# ============================================================
EMAIL_BACKEND = 'core.email_backend.UnsafeEmailBackend'
EMAIL_HOST = 'smtp.resend.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'resend'
EMAIL_HOST_PASSWORD = config('RESEND_API_KEY', default='')
DEFAULT_FROM_EMAIL = 'Viba-Web <info@boletoexpreso.com>'

# ============================================================
# REDIRECCIÓN DE LOGIN
# ============================================================
LOGIN_URL = '/login/'
