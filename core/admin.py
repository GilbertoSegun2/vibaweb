from django.contrib import admin
from .models import Oficina, Empresa, Parametro, Bus, Tarifa, Ruta, Cliente, Viaje, Asiento, Boleto, Credito, MovimientoAsiento, PlantillaBus, PlantillaAsiento



@admin.register(Oficina)
class OficinaAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'telefono', 'activa')
    list_filter = ('activa',)
    search_fields = ('codigo', 'nombre')
    ordering = ('nombre',)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'rif', 'telefono', 'activa')
    list_filter = ('activa',)
    search_fields = ('nombre', 'rif')
    ordering = ('nombre',)
    

@admin.register(Parametro)
class ParametroAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion', 'tipo', 'valor_numerico', 'valor_texto', 'activo')
    list_filter = ('tipo', 'activo')
    search_fields = ('codigo', 'descripcion')
    ordering = ('codigo',)


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ('placa', 'modelo', 'tipo', 'empresa', 'capacidad', 'puestos_descuento_max', 'activo')
    list_filter = ('tipo', 'activo', 'empresa')
    search_fields = ('placa', 'modelo')
    ordering = ('placa',)
    fieldsets = (
        ('Información básica', {
            'fields': ('empresa', 'placa', 'modelo', 'tipo', 'capacidad', 'activo')
        }),
        ('Configuración de asientos', {
            'fields': ('plantilla',),
            'description': 'Selecciona la plantilla que define la distribución de asientos del bus.'
        }),
        ('Descuentos', {
            'fields': ('puestos_descuento_max',),
            'description': 'Si se deja vacío, se usa el parámetro 110 (general).'
        }),
        ('Otros', {
            'fields': ('observacion',)
        }),
    )


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ('origen', 'destino', 'monto_usd', 'seguro_usd', 'activa')
    list_filter = ('activa', 'origen', 'destino')
    search_fields = ('origen__codigo', 'origen__nombre', 'destino__codigo', 'destino__nombre')
    ordering = ('origen', 'destino')


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'origen', 'activa')
    list_filter = ('activa', 'origen')
    search_fields = ('nombre', 'origen__codigo', 'origen__nombre')
    filter_horizontal = ('destinos',)
    ordering = ('nombre',)
    
    
@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('cedula', 'get_nombre_completo', 'telefono', 'whatsapp', 'es_discapacitado', 'es_tercera_edad')
    search_fields = ('cedula', 'user__username', 'user__first_name', 'user__last_name', 'telefono')
    list_filter = ('es_discapacitado', 'es_tercera_edad')
    ordering = ('cedula',)
    raw_id_fields = ('user',)
    
    def get_nombre_completo(self, obj):
        return obj.user.get_full_name() or obj.user.username
    get_nombre_completo.short_description = 'Nombre'


@admin.register(Viaje)
class ViajeAdmin(admin.ModelAdmin):
    list_display = ('id', 'ruta', 'bus', 'fecha', 'hora', 'precio_usd', 'estado', 'cerrado_venta')
    list_filter = ('estado', 'cerrado_venta', 'fecha', 'ruta')
    search_fields = ('ruta__nombre', 'bus__placa')
    ordering = ('-fecha', '-hora')
    # date_hierarchy = 'fecha'
    raw_id_fields = ('ruta', 'bus', 'suspendido_por')
    readonly_fields = ('precio_usd', 'seguro_usd')
    
    fieldsets = (
        ('Información del viaje', {
            'fields': ('ruta', 'bus', 'fecha', 'hora', 'estado')
        }),
        ('Precio (heredado de la tarifa)', {
            'fields': ('precio_usd', 'seguro_usd'),
            'description': 'Estos valores se heredan automáticamente de la tarifa. Para cambiarlos, edita la tarifa correspondiente.'
        }),
        ('Control de venta', {
            'fields': ('cerrado_venta', 'observacion')
        }),
        ('Suspensión', {
            'fields': ('motivo_suspension', 'fecha_suspension', 'suspendido_por'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Asiento)
class AsientoAdmin(admin.ModelAdmin):
    list_display = ('viaje', 'numero', 'fila', 'columna', 'piso', 'lado', 'estado', 'reservado_hasta')
    list_filter = ('estado', 'piso', 'lado')
    search_fields = ('viaje__ruta__nombre', 'numero')
    ordering = ('viaje', 'piso', 'fila', 'columna')
    raw_id_fields = ('viaje',)


@admin.register(Boleto)
class BoletoAdmin(admin.ModelAdmin):
    list_display = ('codigo_qr', 'pasajero_nombre', 'pasajero_cedula', 'viaje', 'asiento', 'monto_total_usd', 'estado', 'fecha_venta')
    list_filter = ('estado', 'tipo_pasajero', 'viaje__ruta')
    search_fields = ('codigo_qr', 'pasajero_cedula', 'pasajero_nombre')
    ordering = ('-fecha_venta',)
    # date_hierarchy = 'fecha_venta'
    raw_id_fields = ('viaje', 'asiento', 'vendido_por', 'chequeado_por', 'liberado_por')
    readonly_fields = ('fecha_venta',)


@admin.register(Credito)
class CreditoAdmin(admin.ModelAdmin):
    list_display = ('cedula', 'nombre', 'saldo_tarifa_usd', 'saldo_seguro_usd', 'get_saldo_total', 'fecha_vencimiento', 'estado')
    list_filter = ('estado', 'fecha_vencimiento')
    search_fields = ('cedula', 'nombre')
    ordering = ('-fecha_creacion',)
    # date_hierarchy = 'fecha_creacion'
    raw_id_fields = ('boleto_origen',)
    
    def get_saldo_total(self, obj):
        return f"${obj.saldo_total_usd}"
    get_saldo_total.short_description = 'Saldo total'


@admin.register(MovimientoAsiento)
class MovimientoAsientoAdmin(admin.ModelAdmin):
    list_display = ('asiento', 'tipo', 'estado_anterior', 'estado_nuevo', 'usuario', 'fecha_hora', 'motivo')
    list_filter = ('tipo', 'fecha_hora', 'usuario')
    search_fields = ('asiento__numero', 'asiento__viaje__ruta__nombre', 'motivo')
    ordering = ('-fecha_hora',)
    # date_hierarchy = 'fecha_hora'
    raw_id_fields = ('asiento', 'usuario', 'boleto_relacionado')
    readonly_fields = ('fecha_hora',)
    

@admin.register(PlantillaBus)
class PlantillaBusAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'capacidad', 'pisos', 'activa')
    list_filter = ('tipo', 'pisos', 'activa')
    search_fields = ('nombre',)
    ordering = ('nombre',)


@admin.register(PlantillaAsiento)
class PlantillaAsientoAdmin(admin.ModelAdmin):
    list_display = ('plantilla', 'piso', 'fila', 'columna', 'numero', 'lado', 'tipo')
    list_filter = ('plantilla', 'piso', 'tipo', 'lado')
    search_fields = ('plantilla__nombre', 'numero')
    ordering = ('plantilla', 'piso', 'fila', 'columna')
    raw_id_fields = ('plantilla',)
    
from .models import Transaccion, Pago


from .models import Transaccion, Pago


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'cliente', 'viaje', 'cantidad_boletos', 'monto_total_usd', 'monto_total_bs', 'estado', 'fecha_creacion')
    list_filter = ('estado', 'fecha_creacion', 'viaje__ruta')
    search_fields = ('codigo', 'cliente__cedula', 'cliente__user__username')
    ordering = ('-fecha_creacion',)
    # date_hierarchy = 'fecha_creacion'
    raw_id_fields = ('cliente', 'viaje', 'confirmada_por')
    readonly_fields = ('fecha_creacion', 'fecha_confirmacion', 'fecha_cancelacion')


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaccion', 'metodo', 'monto_usd', 'monto_bs', 'referencia', 'estado', 'fecha_pago')
    list_filter = ('metodo', 'estado', 'fecha_pago')
    search_fields = ('transaccion__codigo', 'referencia', 'banco_origen')
    ordering = ('-fecha_pago',)
    # date_hierarchy = 'fecha_pago'
    raw_id_fields = ('transaccion', 'confirmado_por')
    readonly_fields = ('fecha_pago',)
