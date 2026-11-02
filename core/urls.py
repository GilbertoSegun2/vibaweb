from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

urlpatterns = [
    # ============================================================
    # VISTAS PÚBLICAS Y PRINCIPALES
    # ============================================================
    path('', views.inicio, name='inicio'),
    path('viajes/', views.buscar_viajes, name='buscar_viajes'),
    path('viajes/<int:viaje_id>/', views.detalle_viaje, name='detalle_viaje'),
    
    # ============================================================
    # AUTENTICACIÓN Y SEGURIDAD
    # ============================================================
    path('registro/', views.registro_usuario, name='registro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.perfil, name='perfil'),
    path('verificar-email/', views.verificar_email, name='verificar_email'),
    path('cancelar-registro/', views.cancelar_registro, name='cancelar_registro'),
    path('timeout-logout/', views.timeout_logout_view, name='timeout_logout'),
    path('desbloquear/solicitar/', views.solicitar_desbloqueo_login, name='solicitar_desbloqueo'),
    path('desbloquear/confirmar/', views.confirmar_desbloqueo_view, name='confirmar_desbloqueo'),

    # ⭐ FLUJO DE RECUPERACIÓN DE CONTRASEÑA (Con current_app='core')
    path('recuperar-clave/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        html_email_template_name='registration/password_reset_email.html',
        success_url='/recuperar-clave/enviado/',
        extra_context={'current_app': 'core'}
    ), name='password_reset'),
    
    path('recuperar-clave/enviado/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
        extra_context={'current_app': 'core'}
    ), name='password_reset_done'),
    
    path('recuperar-clave/confirmar/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/recuperar-clave/completado/',
        extra_context={'current_app': 'core'}
    ), name='password_reset_confirm'),
    
    path('recuperar-clave/completado/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
        extra_context={'current_app': 'core'}
    ), name='password_reset_complete'),

    # ============================================================
    # PROCESO DE COMPRA Y RESERVAS
    # ============================================================
    path('reservar/', views.reservar_asientos, name='reservar_asientos'),
    path('liberar/', views.liberar_asientos, name='liberar_asientos'),
    path('reservar-temporal/', views.reservar_temporal, name='reservar_temporal'),
    path('renovar-reserva/', views.renovar_reserva, name='renovar_reserva'),
    path('viajes/<int:viaje_id>/pasajeros/', views.pasajeros, name='pasajeros'),
    path('viajes/<int:viaje_id>/seleccionar-pago/', views.seleccionar_metodo_pago, name='seleccionar_metodo_pago'),
    path('viajes/<int:viaje_id>/pago/', views.pago, name='pago'),
    path('viajes/<int:viaje_id>/pasarela-virtual/', views.pasarela_virtual_view, name='pasarela_virtual'),
    path('confirmacion/<int:transaccion_id>/', views.confirmacion, name='confirmacion'),
    path('mis-boletos/', views.mis_boletos, name='mis_boletos'),
    
    # ============================================================
    # TAQUILLA (EMPLEADOS)
    # ============================================================
    path('taquilla/', views.taquilla_inicio, name='taquilla_inicio'),
    path('taquilla/viaje/<int:viaje_id>/', views.taquilla_mapa, name='taquilla_mapa'),
    path('taquilla/viaje/<int:viaje_id>/cobrar/', views.taquilla_cobrar, name='taquilla_cobrar'),
    
    # ============================================================
    # UTILIDADES Y APIS
    # ============================================================
    path('ayuda/', views.ayuda, name='ayuda'),
    path('api/session-check/', views.session_check, name='session_check'),
    path('api/heartbeat/', views.heartbeat, name='heartbeat'),
    path('api/destinos-populares/', views.api_destinos_populares, name='api_destinos_populares'),
    path('api/buscar-oficinas/', views.api_buscar_oficinas, name='api_buscar_oficinas'),
]
