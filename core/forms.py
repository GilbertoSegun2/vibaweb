from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .models import Cliente


class RegistroForm(forms.Form):
    """Formulario de registro de nuevos clientes"""
    
    # Datos de acceso
    username = forms.CharField(
        max_length=150,
        label="Nombre de usuario",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
            'autocapitalize': 'off',
            'spellcheck': 'false',
        })
    )
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
        })
    )

    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
            'readonly': 'readonly',
            'onfocus': "this.removeAttribute('readonly');",
        })
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
            'readonly': 'readonly',
            'onfocus': "this.removeAttribute('readonly');",
        })
    )

    # Datos personales
    first_name = forms.CharField(
        max_length=100,
        label="Nombres",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
        })
    )
    last_name = forms.CharField(
        max_length=100,
        label="Apellidos",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
        })
    )
    cedula = forms.CharField(
        max_length=20,
        label="Cédula",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
        })
    )
    telefono = forms.CharField(
        max_length=20,
        label="Teléfono",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
        })
    )
    whatsapp = forms.CharField(
        max_length=20,
        label="WhatsApp",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'autocomplete': 'off',
        })
    )
    
# ... (los métodos clean_cedula, clean_telefono, clean_whatsapp, save)
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nombre de usuario ya está en uso.")
        return username
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Este correo ya está registrado.")
        return email
    
    def clean_cedula(self):
        """
        Normaliza Y valida que no exista.
        - Limpia puntos y guiones
        - Verifica que no esté registrada
        """
        cedula = self.cleaned_data.get('cedula', '')
        if not cedula:
            return cedula
        
        # Normalizar
        cedula_limpia = cedula.upper().strip()
        letra = ''
        if cedula_limpia and cedula_limpia[0].isalpha():
            letra = cedula_limpia[0]
            cedula_limpia = cedula_limpia[1:]
        
        solo_numeros = ''.join(c for c in cedula_limpia if c.isdigit())
        cedula_normalizada = f"{letra}{solo_numeros}" if letra else solo_numeros
        
        # Validar duplicado
        if Cliente.objects.filter(cedula=cedula_normalizada).exists():
            raise forms.ValidationError("Esta cédula ya está registrada.")
        
        return cedula_normalizada
    
    def clean_telefono(self):
        """Normaliza el teléfono: solo dígitos (sin guiones, paréntesis ni espacios)."""
        telefono = self.cleaned_data.get('telefono', '')
        if not telefono:
            return telefono
        return ''.join(c for c in telefono if c.isdigit())
    
    def clean_whatsapp(self):
        """Normaliza el WhatsApp: solo dígitos."""
        whatsapp = self.cleaned_data.get('whatsapp', '')
        if not whatsapp:
            return whatsapp
        return ''.join(c for c in whatsapp if c.isdigit())
        
    def clean_password1(self):
        """Valida que la contraseña cumpla con los requisitos de seguridad."""
        password = self.cleaned_data.get('password1', '')
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                raise forms.ValidationError(e.messages)
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        
        return cleaned_data
    
    def save(self):
        """Crea el User y el Cliente"""
        data = self.cleaned_data
        
        user = User.objects.create_user(
            username=data['username'],
            email=data['email'],
            password=data['password1'],
            first_name=data['first_name'],
            last_name=data['last_name'],
        )
        
        cliente = Cliente.objects.create(
            user=user,
            cedula=data['cedula'],
            telefono=data['telefono'],
            whatsapp=data.get('whatsapp', ''),
        )
        
        return user


class LoginForm(forms.Form):
    """Formulario de inicio de sesión"""
    username = forms.CharField(
        max_length=150,
        label="Usuario o correo",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
class PasajeroForm(forms.Form):
    """Datos de un pasajero (usuario web)"""
    
    nombre = forms.CharField(
        max_length=100,
        label="Nombre completo",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre y apellido'})
    )
    cedula = forms.CharField(
        max_length=20,
        label="Cédula",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'V-12345678 o MENOR'})
    )
    telefono = forms.CharField(
        max_length=20,
        label="Teléfono",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0414-1234567'})
    )
    tipo_pasajero = forms.ChoiceField(
        label="Tipo de pasajero",
        initial='normal',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def clean_cedula(self):
        """Normaliza la cédula: solo dígitos y letra V/E/J/G al inicio (sin puntos ni guiones)."""
        cedula = self.cleaned_data.get('cedula', '')
        if not cedula:
            return cedula
        
        cedula_limpia = cedula.upper().strip()
        letra = ''
        if cedula_limpia and cedula_limpia[0].isalpha():
            letra = cedula_limpia[0]
            cedula_limpia = cedula_limpia[1:]
        
        solo_numeros = ''.join(c for c in cedula_limpia if c.isdigit())
        return f"{letra}{solo_numeros}" if letra else solo_numeros
    
    def clean_telefono(self):
        """Normaliza el teléfono: solo dígitos."""
        telefono = self.cleaned_data.get('telefono', '')
        if not telefono:
            return telefono
        return ''.join(c for c in telefono if c.isdigit())
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .utils import obtener_parametro
        
        # Determinar qué tipos de pasajero se permiten según el parámetro 116
        permite_descuento = obtener_parametro('116', default=False)
        
        if permite_descuento:
            self.fields['tipo_pasajero'].choices = [
                ('normal', 'Normal'),
                ('discapacitado', 'Discapacitado (50% desc.)'),
                ('tercera_edad', 'Tercera edad (50% desc.)'),
            ]
        else:
            self.fields['tipo_pasajero'].choices = [
                ('normal', 'Normal'),
            ]
    
class PagoWebForm(forms.Form):
    """Formulario de pago para usuarios web (Pago Móvil o Transferencia)"""
    
    metodo = forms.ChoiceField(
        label="Método de pago",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .utils import obtener_parametro
        
        permite_pago_movil = obtener_parametro('131', default=True)
        permite_transferencia = obtener_parametro('130', default=False)
        
        metodos = []
        if permite_pago_movil:
            metodos.append(('pago_movil', 'Pago Móvil'))
        if permite_transferencia:
            metodos.append(('transferencia', 'Transferencia bancaria'))
        
        self.fields['metodo'].choices = metodos
    
    
    banco_origen = forms.CharField(
        max_length=50,
        label="Banco de origen",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Banesco'})
    )
    
    telefono_origen = forms.CharField(
        max_length=20,
        label="Teléfono de origen",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 0414-1234567'})
    )
    
    cedula_origen = forms.CharField(
        max_length=20,
        label="Cédula de origen",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: V-12345678'})
    )
    
    referencia = forms.CharField(
        max_length=30,
        label="Número de referencia",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 123456789'})
    )
    
    monto_pagado_bs = forms.DecimalField(
        max_digits=20,
        decimal_places=2,
        label="Monto pagado (Bs.)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 29872.50', 'step': '0.01'})
    )
    
    comprobante = forms.ImageField(
        label="Imagen del comprobante",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'})
    )


class PasarelaVirtualForm(forms.Form):
    # Bloque 1: Datos de la Tarjeta
    numero_tarjeta = forms.CharField(
        max_length=19,
        label="Número de Tarjeta (16 dígitos)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '4152 3200 1234 5678', 'maxlength': '19'})
    )
    vencimiento = forms.CharField(
        max_length=5,
        label="Fecha de Vencimiento (MM/AA)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'MM/AA', 'maxlength': '5'})
    )
    cvv = forms.CharField(
        max_length=4,
        label="CVV / CVC",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '123', 'maxlength': '4'})
    )

    # Bloque 2: Datos del Tarjetahabiente
    nombre_tarjeta = forms.CharField(
        max_length=100,
        label="Nombre impreso en la tarjeta",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'JUAN PÉREZ'})
    )
    tipo_documento = forms.ChoiceField(
        choices=[('V', 'V'), ('E', 'E'), ('J', 'J'), ('G', 'G')],
        label="Tipo Doc.",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    cedula_tarjeta = forms.CharField(
        max_length=15,
        label="Cédula o RIF",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678'})
    )

    # Bloque 3: Autenticación Bancaria Avanzada (El Toque Venezolano)
    tipo_cuenta = forms.ChoiceField(
        choices=[('corriente', 'Cuenta Corriente'), ('ahorro', 'Cuenta Ahorros')],
        label="Tipo de Cuenta",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    clave_sms = forms.CharField(
        max_length=10,
        label="Clave Dinámica (SMS / Token)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Código recibido por SMS'})
    )
