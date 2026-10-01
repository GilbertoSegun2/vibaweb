from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('viajes/', views.buscar_viajes, name='buscar_viajes'),
    path('viajes/<int:viaje_id>/', views.detalle_viaje, name='detalle_viaje'),
    path('registro/', views.registro_usuario, name='registro'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.perfil, name='perfil'),
    path('reservar/', views.reservar_asientos, name='reservar_asientos'),
    path('liberar/', views.liberar_asientos, name='liberar_asientos'),
    path('viajes/<int:viaje_id>/pasajeros/', views.pasajeros, name='pasajeros'),
    path('reservar-temporal/', views.reservar_temporal, name='reservar_temporal'),
    path('renovar-reserva/', views.renovar_reserva, name='renovar_reserva'),
    path('viajes/<int:viaje_id>/pago/', views.pago, name='pago'),
    path('viajes/<int:viaje_id>/pasarela-virtual/', views.pasarela_virtual_view, name='pasarela_virtual'),
    path('confirmacion/<int:transaccion_id>/', views.confirmacion, name='confirmacion'),
]
