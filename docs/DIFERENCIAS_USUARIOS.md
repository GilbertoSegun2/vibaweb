# DIFERENCIAS ENTRE USUARIO-WEB Y USUARIO-EMPRESA

**Proyecto**: Viba-Web (Venta Integrada de Boletos Automatizados - Web)
**Última actualización**: 23/09/2026

---

## 📌 Definiciones

- **Usuario-Web**: Cliente que compra boletos por internet desde su dispositivo.
- **Usuario-Empresa**: Personal de la empresa (taquilleros, supervisores, admins de oficina) que vende boletos desde las taquillas del terminal.

---

## 📊 Tabla comparativa

| Aspecto | Usuario-Web | Usuario-Empresa |
|---------|-------------|-----------------|
| **Registro** | Se registra solo en la web (con verificación por email) | Lo registra el departamento administrativo de la empresa |
| **Estados** | Activo, Suspendido, Retirado | Activo, Suspendido, Retirado |
| **Roles** | Solo Cliente | Taquillero, Supervisor, Administrador de Oficina |
| **Métodos de pago** | Solo Pago Móvil y Transferencia | Todos (Pago Móvil, Transferencia, Efectivo USD, Efectivo Bs., Punto de Venta) |
| **Multipago** | No (un solo pago por transacción) | Sí (N pagos por transacción) |
| **Descuentos (3ra edad / discapacitado)** | No (a menos que parámetro 116 = Sí) | Sí, hasta el cupo del bus (campo `puestos_descuento_max` o parámetro 110) |
| **Compra preferencial** | Limitada por parámetro 116 | Ilimitada dentro del cupo |
| **Puede vender después de la hora de salida** | No | Sí |
| **Puede vender menos de N horas antes de la salida** | No (parámetro 117) | Sí |
| **Puede aumentar cupo de descuentos** | No | Solo el Supervisor |
| **Puede reservar (sin pago)** | No (solo bloqueo temporal de 30 segundos) | Sí, reserva permanente (a nombre del solicitante) |
| **Puede ver el sitio público** | Sí | No (tiene menú especial de taquilla) |
| **Puede comprar para sí mismo** | Sí | Sí |
| **Puede comprar para otras personas** | Sí | Sí |
| **Imprime boletos** | No (los recibe por email/WhatsApp) | Sí (impresión directa en taquilla) |
| **Ve el QR del boleto** | Sí (en email/WhatsApp) | Sí (al imprimir) |
| **Puede ver boletos viejos** | No (solo boletos activos/futuros) | Sí (histórico completo de su oficina) |
| **Puede cancelar una compra** | No | Sí (con autorización del supervisor) |
| **Puede consultar boletos web pendientes de imprimir** | No | Sí |
| **Tooltip con datos del pasajero** | No | Sí (ver detalles abajo) |
| **Puede ver salidas de fechas anteriores** | No | Sí |
| **Menú de la web** | Menú de cliente (Inicio, Buscar Viajes, Mi Perfil, Mis Boletos activos) | Menú de empresa (Inicio, Taquilla, Ventas, Reportes, Admin) |

---

## 🎯 Tooltip del mapa de asientos (solo usuario-empresa)

Cuando el usuario-empresa pasa el mouse por encima de un asiento **sin hacer clic**, debe ver:

### Para asiento vendido:
- **Nombre del pasajero** que va en ese puesto
- **Número de boleto** (código QR o número interno)
- **Cédula del pasajero**
- **Tipo de pasajero** (normal, 3ra edad, discapacitado)

### Para asiento reservado:
- **Nombre de quién reservó**
- **Fecha y hora de la reserva**
- **Motivo o nota de la reserva** (si existe)

### Para asiento disponible:
- Solo el número del puesto y su lado (ventana/pasillo)

**⚠️ Importante**: este tooltip **NO se muestra en el sitio público** (usuario-web). Solo lo ven los usuarios-empresa logueados con permisos.

---

## 📅 Regla de visibilidad de fechas

**Ningún usuario (ni web ni empresa) puede ver salidas de fechas anteriores a la fecha actual del sistema.**

| Usuario | Fechas que puede ver |
|---------|----------------------|
| **Usuario-web** | Fecha actual y futuras |
| **Usuario-empresa** (taquillero, supervisor) | Fecha actual y futuras |
| **Administrador de la empresa** | Histórico completo (pasado, presente y futuro) |

**Excepción**: si un supervisor necesita vender un boleto para una fecha pasada (caso excepcional y autorizado), debe hacerlo desde el panel de administración con permisos especiales.

**Implementación**:
- Las vistas `buscar_viajes` y `detalle_viaje` filtran por `fecha__gte=timezone.now().date()`.
- Esto aplica **tanto para usuario-web como usuario-empresa**.
- **Solo los administradores** (grupo "Administradores" o superusuarios) pueden ver fechas anteriores.
- En el admin de Django, el administrador puede ver todo (es automático).

**Importante**:
- Los viajes de fechas pasadas **existen en la base de datos** (para reportes y auditoría).
- Simplemente **no se muestran** en las vistas públicas ni en las de taquilla.
- Si el admin necesita consultarlos, los ve desde el admin de Django.

---

## 🔐 Reglas de negocio específicas

### Para usuario-web:
1. Solo puede ver **boletos activos** (fecha de viaje futura)
2. **No puede cancelar** una compra (debe ir al terminal)
3. **No puede comprar preferencial** (a menos que parámetro 116 = Sí)
4. **No puede comprar después de la salida** del bus
5. **No puede comprar menos de N horas antes** de la salida (parámetro 117)
6. Su bloqueo de asientos es **temporal** (30 segundos renovables hasta 10 minutos)
7. Recibe su boleto por **email o WhatsApp** con código QR
8. Al llegar al terminal, **presenta el QR** para imprimir el boleto

### Para usuario-empresa:
1. Ve el **sitio público** con menú especial de taquilla
2. Puede **vender a cualquier hora**, incluso después de la salida
3. Puede **vender con descuento** (hasta el cupo del bus)
4. Puede **reservar puestos** (reserva permanente, no temporal)
5. Puede **imprimir boletos** directamente en taquilla
6. Puede **consultar boletos web pendientes** de imprimir
7. **Ve el tooltip** con datos de pasajeros al pasar el mouse
8. Solo el **supervisor** puede aumentar el cupo de descuentos

### Para supervisor (rol dentro de usuario-empresa):
1. Todo lo del usuario-empresa
2. Puede **aumentar el cupo de descuentos** por bus
3. Puede **autorizar reservas** permanentes
4. Puede **ver reportes** de su oficina
5. Puede **cancelar boletos** con autorización

---

## 🔐 Parámetros relacionados

| Código | Descripción | Valor por defecto |
|--------|-------------|-------------------|
| **101** | Minutos de reserva inicial (usuario-web) | 4 |
| **110** | Máximo de puestos con descuento por bus | 5 |
| **111** | Minutos para llenar datos de pasajeros | 10 |
| **112** | Minutos para completar el pago | 10 |
| **113** | Duración del bloqueo corto (segundos) | 30 |
| **114** | Intervalo de renovación del bloqueo (segundos) | 20 |
| **115** | Tiempo de inactividad antes de dejar de renovar (segundos) | 120 |
| **116** | Permitir compra web con descuento (Sí/No) | No |
| **117** | Horas mínimas antes de la salida para comprar (usuario-web) | 2 |

---

## 📝 Notas adicionales

- Los métodos de pago **Efectivo USD, Efectivo Bs. y Punto de Venta** son **exclusivos de usuario-empresa**.
- El **multipago** es exclusivo de usuario-empresa.
- El **tooltip con datos de pasajeros** es exclusivo de usuario-empresa.
- La **impresión directa de boletos** es exclusiva de usuario-empresa.
- El usuario-web **NO puede cancelar** una compra. Debe ir al terminal.
- El usuario-web **solo ve boletos activos** (futuros).

---

**Este documento debe actualizarse cada vez que se agregue una nueva regla de negocio.**
