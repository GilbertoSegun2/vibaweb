from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Oficina(models.Model):
    """Oficinas de la empresa (terminales, agencias, etc.)"""
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código")
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    direccion = models.TextField(blank=True, verbose_name="Dirección")
    telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Oficina"
        verbose_name_plural = "Oficinas"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class Empresa(models.Model):
    """Empresas dueñas de los buses (accionistas)"""
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    rif = models.CharField(max_length=20, unique=True, verbose_name="RIF")
    telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono")
    banco = models.CharField(max_length=50, blank=True, verbose_name="Banco")
    telefono_pago = models.CharField(max_length=20, blank=True, verbose_name="Teléfono Pago Móvil")
    cedula_pago = models.CharField(max_length=20, blank=True, verbose_name="Cédula Pago Móvil")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.rif})"


class Parametro(models.Model):
    """Parámetros configurables del sistema (seguro, tiempos, colores, etc.)"""
    TIPOS = [
        ('numero', 'Numérico'),
        ('texto', 'Texto'),
        ('booleano', 'Sí/No'),
    ]
    
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código")
    descripcion = models.CharField(max_length=200, verbose_name="Descripción")
    tipo = models.CharField(max_length=10, choices=TIPOS, default='numero', verbose_name="Tipo")
    valor_numerico = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True, verbose_name="Valor numérico")
    valor_texto = models.CharField(max_length=200, blank=True, verbose_name="Valor texto")
    valor_booleano = models.BooleanField(null=True, blank=True, verbose_name="Valor Sí/No")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Parámetro"
        verbose_name_plural = "Parámetros"
        ordering = ['codigo']

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"
   
   
        
class Bus(models.Model):
    """Buses de la flota, con su configuración de asientos en JSON"""
    TIPOS = [
        ('doble_piso', 'Doble Piso'),
        ('yutong', 'Yutong'),
        ('poltrona', 'Poltrona'),
        ('ejecutivo', 'Ejecutivo'),
        ('otro', 'Otro'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, verbose_name="Empresa")
    placa = models.CharField(max_length=15, unique=True, verbose_name="Placa")
    modelo = models.CharField(max_length=50, verbose_name="Modelo")
    tipo = models.CharField(max_length=20, choices=TIPOS, default='otro', verbose_name="Tipo")
    capacidad = models.PositiveIntegerField(verbose_name="Capacidad total")
    puestos_descuento_max = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Máximo de puestos con descuento",
        help_text="Si se deja vacío, se usa el valor del parámetro 110"
    )
    configuracion_asientos = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración de asientos (obsoleto)",
        help_text="Campo obsoleto. Se mantiene por compatibilidad. Usar 'plantilla'."
    )
    plantilla = models.ForeignKey(
        'PlantillaBus',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='buses',
        verbose_name="Plantilla de asientos"
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Bus"
        verbose_name_plural = "Buses"
        ordering = ['placa']

    def __str__(self):
        return f"{self.placa} - {self.modelo} ({self.capacidad} puestos)"


class Tarifa(models.Model):
    """Tarifas entre oficinas origen y destino (en USD)"""
    origen = models.ForeignKey(
        Oficina,
        related_name='tarifas_origen',
        on_delete=models.PROTECT,
        verbose_name="Oficina origen"
    )
    destino = models.ForeignKey(
        Oficina,
        related_name='tarifas_destino',
        on_delete=models.PROTECT,
        verbose_name="Oficina destino"
    )
    monto_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto USD")
    seguro_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Seguro USD"
    )
    seguro_opcional = models.BooleanField(default=True, verbose_name="¿Seguro opcional?")
    activa = models.BooleanField(default=True, verbose_name="Activa")
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Tarifa"
        verbose_name_plural = "Tarifas"
        ordering = ['origen', 'destino']
        unique_together = ('origen', 'destino')

    def __str__(self):
        return f"{self.origen.codigo} → {self.destino.codigo}: ${self.monto_usd}"


class Ruta(models.Model):
    """Agrupación de tarifas desde una oficina origen hacia varias oficinas destino"""
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre") # <-- Agregado unique=True
    origen = models.ForeignKey(
        Oficina,
        related_name='rutas_origen',
        on_delete=models.PROTECT,
        verbose_name="Oficina origen"
    )
    destinos = models.ManyToManyField(
        Oficina,
        related_name='rutas_destino',
        verbose_name="Oficinas destino"
    )
    activa = models.BooleanField(default=True, verbose_name="Activa")
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Ruta"
        verbose_name_plural = "Rutas"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} (desde {self.origen.codigo})"
        
        

class Cliente(models.Model):
    """Perfil extendido del usuario registrado"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Usuario")
    cedula = models.CharField(max_length=20, unique=True, verbose_name="Cédula")
    telefono = models.CharField(max_length=20, verbose_name="Teléfono")
    whatsapp = models.CharField(max_length=20, blank=True, verbose_name="WhatsApp")
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name="Fecha de nacimiento")
    direccion = models.TextField(blank=True, verbose_name="Dirección")
    es_discapacitado = models.BooleanField(default=False, verbose_name="¿Discapacitado?")
    es_tercera_edad = models.BooleanField(default=False, verbose_name="¿Tercera edad?")
    fecha_registro = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de registro")

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['cedula']

    def __str__(self):
        return f"{self.cedula} - {self.user.get_full_name() or self.user.username}"


class Viaje(models.Model):
    """Un viaje programado: bus + ruta + fecha + hora"""
    ESTADOS = [
        ('programado', 'Programado'),
        ('suspendido', 'Suspendido'),
        ('reprogramado', 'Reprogramado'),
        ('en_curso', 'En curso'),
        ('finalizado', 'Finalizado'),
        ('cancelado', 'Cancelado'),
    ]

    ruta = models.ForeignKey(Ruta, on_delete=models.PROTECT, verbose_name="Ruta")
    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, verbose_name="Bus")
    fecha = models.DateField(verbose_name="Fecha")
    hora = models.TimeField(verbose_name="Hora de salida")
    precio_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Precio USD")
    seguro_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Seguro USD")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='programado', verbose_name="Estado")
    cerrado_venta = models.BooleanField(default=False, verbose_name="Venta cerrada")
    
    # Suspensión
    motivo_suspension = models.CharField(max_length=200, blank=True, verbose_name="Motivo de suspensión")
    fecha_suspension = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de suspensión")
    suspendido_por = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='viajes_suspendidos', verbose_name="Suspendido por"
    )
    
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        verbose_name = "Viaje"
        verbose_name_plural = "Viajes"
        ordering = ['fecha', 'hora']
        indexes = [
            models.Index(fields=['fecha', 'estado']),
        ]

    def __str__(self):
        return f"{self.ruta.nombre} - {self.fecha} {self.hora} - {self.bus.placa}"

    def save(self, *args, **kwargs):
        """
        Al crear un viaje nuevo, genera sus asientos automáticamente.
        El precio se calcula al momento de la venta, según la tarifa origen-destino.
        """
        # Si el precio es None, ponerlo en 0 (por si el admin no lo envía)
        if self.precio_usd is None:
            self.precio_usd = 0
        if self.seguro_usd is None:
            self.seguro_usd = 0
        
        es_nuevo = self.pk is None
        super().save(*args, **kwargs)
        
        if es_nuevo:
            from .utils import generar_asientos_para_viaje
            generar_asientos_para_viaje(self)

class Asiento(models.Model):
    """Asiento (o posición especial) de un viaje"""
    ESTADOS = [
        ('disponible', 'Disponible'),
        ('reservado', 'Reservado'),
        ('vendido', 'Vendido'),
        ('bloqueado', 'Bloqueado'),
    ]
    TIPOS = [
        ('asiento', 'Asiento'),
        ('escalera', 'Escalera'),
        ('baño', 'Baño'),
        ('vacio', 'Vacío'),
    ]

    viaje = models.ForeignKey(Viaje, related_name='asientos', on_delete=models.CASCADE, verbose_name="Viaje")
    numero = models.CharField(max_length=5, blank=True, verbose_name="Número")
    fila = models.PositiveIntegerField(verbose_name="Fila")
    columna = models.PositiveIntegerField(verbose_name="Columna")
    piso = models.PositiveIntegerField(default=1, verbose_name="Piso")
    lado = models.CharField(
        max_length=10,
        choices=[('ventana', 'Ventana'), ('pasillo', 'Pasillo')],
        blank=True,
        verbose_name="Lado"
    )
    tipo = models.CharField(max_length=20, choices=TIPOS, default='asiento', verbose_name="Tipo")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='disponible', verbose_name="Estado")
    reservado_hasta = models.DateTimeField(null=True, blank=True, verbose_name="Reservado hasta")
    reservado_por = models.ForeignKey(
        'Cliente',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='asientos_reservados',
        verbose_name="Reservado por"
    )

    class Meta:
        verbose_name = "Asiento"
        verbose_name_plural = "Asientos"
        ordering = ['viaje', 'piso', 'fila', 'columna']
        indexes = [
            models.Index(fields=['viaje', 'estado']),
        ]

    def __str__(self):
        if self.tipo == 'asiento':
            return f"Asiento {self.numero} - Viaje {self.viaje.id}"
        return f"{self.get_tipo_display()} (f{self.fila}c{self.columna}) - Viaje {self.viaje.id}"

class Transaccion(models.Model):
    """Una compra de boletos (agrupa varios boletos y sus pagos)"""
    ESTADOS = [
        ('pendiente_pago', 'Pendiente de pago'),
        ('pendiente_verificacion', 'Pago cargado, pendiente de verificación'),
        ('confirmada', 'Confirmada'),
        ('rechazada', 'Rechazada'),
        ('cancelada', 'Cancelada'),
    ]

    codigo = models.CharField(max_length=30, unique=True, verbose_name="Código")
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT,
        related_name='transacciones', verbose_name="Cliente"
    )
    viaje = models.ForeignKey(
        Viaje, on_delete=models.PROTECT,
        related_name='transacciones', verbose_name="Viaje"
    )

    # Montos
    cantidad_boletos = models.PositiveIntegerField(verbose_name="Cantidad de boletos")
    monto_total_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto total USD")
    monto_total_bs = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="Monto total Bs.")
    tasa_bcv = models.DecimalField(max_digits=20, decimal_places=4, default=0, verbose_name="Tasa BCV")

    # Estado
    estado = models.CharField(max_length=30, choices=ESTADOS, default='pendiente_pago', verbose_name="Estado")

    # Fechas
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_confirmacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de confirmación")
    fecha_cancelacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de cancelación")

    # Auditoría
    confirmada_por = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='transacciones_confirmadas', verbose_name="Confirmada por"
    )
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Transacción"
        verbose_name_plural = "Transacciones"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.codigo} - {self.cliente} - ${self.monto_total_usd}"

class Boleto(models.Model):
    """Boleto vendido a un pasajero para un viaje y asiento específico"""
    ESTADOS = [
        ('vendido', 'Vendido'),
        ('usado', 'Usado'),
        ('cancelado', 'Cancelado con crédito'),
        ('no_show', 'No se presentó'),
        ('reprogramado', 'Reprogramado'),
    ]
    
    TIPOS_PASAJERO = [
        ('normal', 'Normal'),
        ('discapacitado', 'Discapacitado'),
        ('tercera_edad', 'Tercera edad'),
        ('cortesia', 'Cortesía'),
    ]
    
    # Relaciones principales
    transaccion = models.ForeignKey(
        Transaccion, on_delete=models.PROTECT,
        related_name='boletos', null=True, blank=True,
        verbose_name="Transacción"
    )
    viaje = models.ForeignKey(Viaje, on_delete=models.PROTECT, related_name='boletos', verbose_name="Viaje")
    asiento = models.ForeignKey(Asiento, on_delete=models.PROTECT, verbose_name="Asiento")
    
    # Datos del pasajero (desnormalizados para histórico)
    pasajero_cedula = models.CharField(max_length=20, db_index=True, verbose_name="Cédula del pasajero")
    pasajero_nombre = models.CharField(max_length=100, verbose_name="Nombre del pasajero")
    pasajero_telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono del pasajero")
    pasajero_whatsapp = models.CharField(max_length=20, blank=True, verbose_name="WhatsApp del pasajero")
    
    # Tipo y descuento
    tipo_pasajero = models.CharField(max_length=20, choices=TIPOS_PASAJERO, default='normal', verbose_name="Tipo de pasajero")
    porcentaje_descuento = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="% Descuento")
    
    # Montos
    monto_tarifa_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto tarifa USD")
    monto_seguro_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Monto seguro USD")
    monto_descuento_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Monto descuento USD")
    monto_total_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto total USD")
    
    # Tasa BCV al momento de la venta (histórico)
    tasa_bcv = models.DecimalField(max_digits=20, decimal_places=4, default=0, verbose_name="Tasa BCV")
    monto_total_bs = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="Monto total Bs.")
    
    # Código QR único
    codigo_qr = models.CharField(max_length=50, unique=True, verbose_name="Código QR")
    
    # Estados y fechas
    estado = models.CharField(max_length=20, choices=ESTADOS, default='vendido', verbose_name="Estado")
    fecha_venta = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de venta")
    fecha_chequeo = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de chequeo")
    
    # Auditoría
    vendido_por = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='boletos_vendidos', verbose_name="Vendido por")
    chequeado_por = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='boletos_chequeados', verbose_name="Chequeado por")
    liberado_por = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='boletos_liberados', verbose_name="Liberado por")
    
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Boleto"
        verbose_name_plural = "Boletos"
        ordering = ['-fecha_venta']
        indexes = [
            models.Index(fields=['codigo_qr']),
            models.Index(fields=['pasajero_cedula']),
            models.Index(fields=['viaje', 'estado']),
        ]

    def __str__(self):
        return f"Boleto {self.codigo_qr} - {self.pasajero_nombre}"


class Credito(models.Model):
    """Crédito a favor de un cliente por cancelación o no-show"""
    ESTADOS = [
        ('vigente', 'Vigente'),
        ('parcial', 'Usado parcialmente'),
        ('usado', 'Usado totalmente'),
        ('vencido', 'Vencido'),
    ]

    # Datos del cliente
    cedula = models.CharField(max_length=20, db_index=True, verbose_name="Cédula")
    nombre = models.CharField(max_length=100, verbose_name="Nombre del cliente")

    # Montos separados
    monto_tarifa_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Tarifa original USD")
    monto_seguro_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Seguro original USD")
    saldo_tarifa_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Saldo tarifa USD")
    saldo_seguro_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Saldo seguro USD")

    # Fechas
    fecha_creacion = models.DateField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_vencimiento = models.DateField(verbose_name="Fecha de vencimiento")

    # Origen
    boleto_origen = models.ForeignKey(
        Boleto, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='creditos_generados',
        verbose_name="Boleto que originó el crédito"
    )

    # Estado
    estado = models.CharField(max_length=20, choices=ESTADOS, default='vigente', verbose_name="Estado")
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Crédito"
        verbose_name_plural = "Créditos"
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['cedula', 'estado']),
        ]

    def __str__(self):
        return f"{self.cedula} - ${self.saldo_total_usd} - {self.estado}"

    @property
    def saldo_total_usd(self):
        return (self.saldo_tarifa_usd or 0) + (self.saldo_seguro_usd or 0)


class MovimientoAsiento(models.Model):
    """Registro histórico de todos los cambios de estado de un asiento"""
    TIPOS = [
        ('venta', 'Venta'),
        ('reserva', 'Reserva temporal'),
        ('liberacion_reserva', 'Liberación por vencimiento'),
        ('cancelacion', 'Cancelación por el pasajero'),
        ('no_show', 'No se presentó'),
        ('reprogramacion', 'Reprogramación'),
        ('bloqueo', 'Bloqueado por admin'),
        ('desbloqueo', 'Desbloqueado por admin'),
        ('liberacion_manual', 'Liberación manual'),
    ]

    asiento = models.ForeignKey(Asiento, on_delete=models.PROTECT, related_name='movimientos', verbose_name="Asiento")
    tipo = models.CharField(max_length=30, choices=TIPOS, verbose_name="Tipo de movimiento")
    estado_anterior = models.CharField(max_length=20, verbose_name="Estado anterior")
    estado_nuevo = models.CharField(max_length=20, verbose_name="Estado nuevo")
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, verbose_name="Usuario")
    fecha_hora = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y hora")
    motivo = models.CharField(max_length=200, blank=True, verbose_name="Motivo")
    boleto_relacionado = models.ForeignKey(Boleto, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Boleto relacionado")

    class Meta:
        verbose_name = "Movimiento de Asiento"
        verbose_name_plural = "Movimientos de Asientos"
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['asiento', '-fecha_hora']),
            models.Index(fields=['usuario', '-fecha_hora']),
        ]

    def __str__(self):
        return f"{self.asiento} - {self.tipo} - {self.fecha_hora}"

class Pago(models.Model):
    """Pago de una transacción (Pago Móvil, transferencia, efectivo, etc.)"""
    METODOS = [
        ('pago_movil', 'Pago Móvil'),
        ('transferencia', 'Transferencia bancaria'),
        ('efectivo_usd', 'Efectivo USD'),
        ('efectivo_bs', 'Efectivo Bs.'),
        ('punto_venta', 'Punto de venta'),
    ]
    ESTADOS = [
        ('pendiente', 'Pendiente de verificación'),
        ('confirmado', 'Confirmado'),
        ('rechazado', 'Rechazado'),
    ]

    transaccion = models.ForeignKey(
        Transaccion, on_delete=models.CASCADE,
        related_name='pagos', verbose_name="Transacción"
    )

    # Datos del pago
    metodo = models.CharField(max_length=50, choices=METODOS, verbose_name="Método de pago")
    monto_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto USD")
    monto_bs = models.DecimalField(max_digits=20, decimal_places=2, default=0, verbose_name="Monto Bs.")
    tasa_bcv = models.DecimalField(max_digits=20, decimal_places=4, default=0, verbose_name="Tasa BCV")

    # Datos específicos del Pago Móvil
    banco_origen = models.CharField(max_length=50, blank=True, verbose_name="Banco de origen")
    telefono_origen = models.CharField(max_length=20, blank=True, verbose_name="Teléfono de origen")
    cedula_origen = models.CharField(max_length=20, blank=True, verbose_name="Cédula de origen")
    referencia = models.CharField(max_length=30, blank=True, verbose_name="Número de referencia")

    # Comprobante
    comprobante = models.ImageField(
        upload_to='comprobantes/%Y/%m/', blank=True, null=True,
        verbose_name="Imagen del comprobante"
    )

    # Estado
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente', verbose_name="Estado")
    fecha_pago = models.DateTimeField(auto_now_add=True, verbose_name="Fecha del pago")
    fecha_confirmacion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de confirmación")

    # Auditoría
    confirmado_por = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='pagos_confirmados', verbose_name="Confirmado por"
    )
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Pago"
        verbose_name_plural = "Pagos"
        ordering = ['-fecha_pago']

    def __str__(self):
        return f"Pago {self.id} - {self.get_metodo_display()} - ${self.monto_usd}"

class PlantillaBus(models.Model):
    """Plantilla de distribución de asientos para un tipo de bus"""
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre")
    tipo = models.CharField(max_length=20, choices=Bus.TIPOS, verbose_name="Tipo de bus")
    capacidad = models.PositiveIntegerField(verbose_name="Capacidad total")
    pisos = models.PositiveIntegerField(default=1, verbose_name="Cantidad de pisos")
    activa = models.BooleanField(default=True, verbose_name="Activa")
    observacion = models.CharField(max_length=200, blank=True, verbose_name="Observación")

    class Meta:
        verbose_name = "Plantilla de Bus"
        verbose_name_plural = "Plantillas de Buses"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.capacidad} puestos)"


class PlantillaAsiento(models.Model):
    """Cada posición dentro de una plantilla de bus (asiento, escalera, baño, etc.)"""
    TIPOS = [
        ('asiento', 'Asiento'),
        ('escalera', 'Escalera'),
        ('baño', 'Baño'),
        ('conductor', 'Conductor'),
        ('vacio', 'Vacío'),
    ]
    LADOS = [
        ('ventana', 'Ventana'),
        ('pasillo', 'Pasillo'),
        ('', 'No aplica'),
    ]

    plantilla = models.ForeignKey(
        PlantillaBus, related_name='posiciones', on_delete=models.CASCADE,
        verbose_name="Plantilla"
    )
    numero = models.CharField(max_length=5, blank=True, verbose_name="Número de asiento")
    fila = models.PositiveIntegerField(verbose_name="Fila")
    columna = models.PositiveIntegerField(verbose_name="Columna")
    piso = models.PositiveIntegerField(default=1, verbose_name="Piso")
    lado = models.CharField(max_length=10, choices=LADOS, blank=True, verbose_name="Lado")
    tipo = models.CharField(max_length=20, choices=TIPOS, default='asiento', verbose_name="Tipo")

    class Meta:
        verbose_name = "Posición de Plantilla"
        verbose_name_plural = "Posiciones de Plantilla"
        ordering = ['plantilla', 'piso', 'fila', 'columna']
        unique_together = ('plantilla', 'piso', 'fila', 'columna')

    def __str__(self):
        if self.tipo == 'asiento':
            return f"{self.plantilla.nombre} - Asiento {self.numero}"
        return f"{self.plantilla.nombre} - {self.get_tipo_display()} (f{self.fila}c{self.columna})"
