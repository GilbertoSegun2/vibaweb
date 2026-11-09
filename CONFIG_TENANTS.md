# 🚌 Configuración de Tenants - Viba-Web (SaaS Multi-Empresa)

Este archivo sirve como guía de referencia rápida para configurar y alternar entre los distintos clientes (tenants) de la plataforma en el Panel de Administración de Django:

👉 **Ruta del Admin:** `http://127.0.0.1:8000/admin/core/parametro/`

---

## 1. Expresos Mérida C.A.

> **Uso:** Configuración para la empresa Expresos Mérida.

| Código Parámetro | Nombre en Admin / Descripción | Valor a Guardar (Texto) |
| :--- | :--- | :--- |
| **200** | Carpeta de la empresa (slug) | `expresos_merida` |
| **150** | Logo de la empresa | `logo_merida.png` |
| **152** | Color primario (Navbar) | `#0F75BB` |
| **153** | Color secundario (Botones/Destacados) | `#26AAE1` |
| **160** | Título principal de bienvenida | `Expresos Mérida C.A.` |
| **161** | Subtítulo de bienvenida | `Compra tus boletos de autobús de forma rápida y segura` |

---

## 2. Transporte Marino Guerrero C.A.

> **Uso:** Configuración para la empresa Marino Guerrero (Diseño Oscuro).

| Código Parámetro | Nombre en Admin / Descripción | Valor a Guardar (Texto) |
| :--- | :--- | :--- |
| **200** | Carpeta de la empresa (slug) | `marino_guerrero` |
| **150** | Logo de la empresa | `` |
| **152** | Color primario (Navbar / Fondo) | `#2b2b2b` |
| **153** | Color secundario (Detalles / Acentos) | `#000000` |
| **160** | Título principal de bienvenida | `Planificar tus viajes nunca ha sido tan fácil` |
| **161** | Subtítulo de bienvenida | `Compra tus boletos de autobús de forma rápida y segura` |

---

## 3. Expresos Aerovías de Venezuela C.A.

> **Uso:** Configuración para cuando integremos Expresos Aerovías.

| Código Parámetro | Nombre en Admin / Descripción | Valor a Guardar (Texto) |
| :--- | :--- | :--- |
| **200** | Carpeta de la empresa (slug) | `aerovias_venezuela` |
| **150** | Logo de la empresa | `logo_aerovias.png` |
| **152** | Color primario | *(Definir color institucional)* |
| **153** | Color secundario | *(Definir color secundario)* |
| **160** | Título principal de bienvenida | `Expresos Aerovías de Venezuela C.A.` |
| **161** | Subtítulo de bienvenida | `Compra tus boletos de autobús de forma rápida y segura` |

---

### 💡 Instrucciones para cambiar de empresa en 10 segundos:

1. Entra a `http://127.0.0.1:8000/admin/core/parametro/`.
2. Busca el **Parámetro 200** y cámbiale el `valor_texto` al slug de la empresa que quieres mostrar (ej: `expresos_merida` o `marino_guerrero`).
3. Actualiza los parámetros **150, 152, 153, 160 y 161** según la tabla de esa empresa.
4. Recarga la página web principal con `Ctrl + F5`.




### 💡 Pie de Pagina, siempre leer:

Crear la carpeta templates/nombre_empresa/ con su inicio.html y partials/_hero.html.

En el Admin, crear el Parámetro 200 con el nombre de la carpeta.

Configurar los parámetros 1 (nombre), 150 (logo), 152/153 (colores), 160/161 (textos).

Crear las Oficinas, Rutas, Tarifas y Buses en el Admin.

¡Listo! El sistema ya está operando para esa empresa.
