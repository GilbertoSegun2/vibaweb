from django import forms
from django.contrib.auth.models import User
from .models import Cliente


class RegistroForm(forms.Form):
    """Formulario de registro de nuevos clientes"""
    
    # Datos de acceso
    username = forms.CharField(
        max_length=150,
        label="Nombre de usuario",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    
    # Datos personales
    first_name = forms.CharField(
        max_length=100,
        label="Nombres",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        max_length=100,
        label="Apellidos",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    cedula = forms.CharField(
        max_length=20,
        label="Cédula",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    telefono = forms.CharField(
        max_length=20,
        label="Teléfono",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    whatsapp = forms.CharField(
        max_length=20,
        label="WhatsApp",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
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
        cedula = self.cleaned_data.get('cedula')
        if Cliente.objects.filter(cedula=cedula).exists():
            raise forms.ValidationError("Esta cédula ya está registrada.")
        return cedula
    
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
