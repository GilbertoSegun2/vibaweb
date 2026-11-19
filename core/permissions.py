from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


ROLES_TAQUILLA_Y_LIQUIDACION = ('taquillero', 'supervisor', 'admin_oficina')
ROLES_SUPERVISION = ('supervisor', 'admin_oficina')
ROLES_ADMIN_OFICINA = ('admin_oficina',)


def obtener_empleado(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    emp = getattr(user, 'usuarioempresa', None)
    if emp and emp.activo:
        return emp
    return None


def empleado_requerido(*roles_permitidos):
    """
    Valida que el usuario sea empleado activo con uno de los roles permitidos
    (o superusuario). Si no tiene rol suficiente, redirige con mensaje claro.
    """
    roles = roles_permitidos or ROLES_TAQUILLA_Y_LIQUIDACION

    def decorador(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            empleado = obtener_empleado(request.user)
            if not empleado:
                messages.error(request, "No tiene permisos para acceder a esta sección.")
                return redirect('core:inicio')

            if empleado.rol not in roles:
                messages.warning(
                    request,
                    f"Su rol ({empleado.get_rol_display()}) no tiene permiso para esta acción."
                )
                return redirect('core:taquilla_inicio')

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorador
