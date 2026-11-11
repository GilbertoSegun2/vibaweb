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

    # ⭐ FLUJO DE RECUPERACIÓN DE CONTRASEÑA
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
    # PROCESO DE COMPRA Y RESERVAS (WEB)
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
    path('taquilla/confirmacion/<int:transaccion_id>/', views.taquilla_confirmacion, name='taquilla_confirmacion'),
    path('taquilla/viaje/<int:viaje_id>/cerrar-venta/', views.taquilla_cerrar_venta, name='taquilla_cerrar_venta'),
    path('taquilla/liquidacion/<int:liquidacion_id>/', views.taquilla_liquidacion_detalle, name='taquilla_liquidacion_detalle'),
    path('taquilla/consultar-boleto/', views.taquilla_consultar_boleto, name='taquilla_consultar_boleto'),
    path('taquilla/api/liberar-reservas-usuario/', views.liberar_reservas_usuario_api, name='liberar_reservas_usuario_api'),
    path('taquilla/api/buscar-pasajero/', views.taquilla_buscar_pasajero, name='taquilla_buscar_pasajero'),
    
    # ============================================================
    # MÓDULO DE ABORDAJE Y CHEQUEO QR
    # ============================================================
    path('taquilla/escaner/', views.taquilla_escaner, name='taquilla_escaner'),
    path('taquilla/api/validar-qr/', views.api_validar_qr, name='api_validar_qr'),
    
    # Liberar Puestos para Lista de Espera
    path('taquilla/api/boletos-vendidos/', views.taquilla_api_boletos_vendidos, name='taquilla_api_boletos_vendidos'),
    path('taquilla/api/liberar-puestos-vendidos/', views.taquilla_api_liberar_puestos_vendidos, name='taquilla_api_liberar_puestos_vendidos'),
    path('taquilla/api/asientos-disponibles-bloquear/', views.taquilla_api_asientos_disponibles_bloquear, name='taquilla_api_asientos_disponibles_bloquear'),
    path('taquilla/api/bloquear-asientos/', views.taquilla_api_bloquear_asientos, name='taquilla_api_bloquear_asientos'),
    path('taquilla/api/asientos-bloqueados/', views.taquilla_api_asientos_bloqueados, name='taquilla_api_asientos_bloqueados'),
    path('taquilla/api/desbloquear-asientos/', views.taquilla_api_desbloquear_asientos, name='taquilla_api_desbloquear_asientos'),
    
    # Transferencia de Asiento
    path('taquilla/api/buscar-boleto/', views.taquilla_buscar_boleto, name='taquilla_buscar_boleto'),
    path('taquilla/api/transferir/', views.taquilla_ejecutar_transferencia, name='taquilla_ejecutar_transferencia'),
    
    # Reprogramación de Viaje
    path('taquilla/api/buscar-boleto-reprogramar/', views.taquilla_buscar_boleto_reprogramar, name='taquilla_buscar_boleto_reprogramar'),
    path('taquilla/viaje/<int:viaje_id>/reprogramar/<int:boleto_id>/', views.taquilla_reprogramar_cobro, name='taquilla_reprogramar_cobro'),
    path('taquilla/api/bloquear-asiento-reprogramar/', views.taquilla_bloquear_asiento_reprogramar, name='taquilla_bloquear_asiento_reprogramar'),
    path('taquilla/api/liberar-asiento-reprogramar/', views.taquilla_liberar_asiento_reprogramar, name='taquilla_liberar_asiento_reprogramar'),

    # ============================================================
    # UTILIDADES Y APIS
    # ============================================================
    path('ayuda/', views.ayuda, name='ayuda'),
    path('api/session-check/', views.session_check, name='session_check'),
    path('api/heartbeat/', views.heartbeat, name='heartbeat'),
    path('api/destinos-populares/', views.api_destinos_populares, name='api_destinos_populares'),
    path('api/buscar-oficinas/', views.api_buscar_oficinas, name='api_buscar_oficinas'),
    
    path('taquilla/liquidar/', views.taquilla_liquidar, name='taquilla_liquidar'),
    path('taquilla/api/datos-liquidacion/', views.api_datos_liquidacion, name='api_datos_liquidacion'),
]
