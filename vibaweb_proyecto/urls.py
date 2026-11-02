from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('pwa.urls')),
    
    # ⭐ SOLUCIÓN GLOBAL: Registramos esta ruta aquí para que las vistas 
    # internas de Django la encuentren de inmediato al armar el correo.
    path('recuperar-clave/confirmar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/recuperar-clave/completado/'
    ), name='password_reset_confirm'),

    path('', include('core.urls')),
]

# Servir archivos media y static en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
