/**
 * Máscara de montos para campos de dinero.
 * El usuario escribe dígitos y el campo se formatea automáticamente
 * en formato "27.312,00" (es-VE).
 */
(function() {
    'use strict';

    function aplicarMascara(input) {
        // Cambiar el tipo a text para evitar el spinner
        input.type = 'text';
        input.setAttribute('inputmode', 'numeric');
        input.setAttribute('autocomplete', 'off');
        if (!input.getAttribute('placeholder')) {
            input.setAttribute('placeholder', '0,00');
        }

        // Detectar el valor inicial (si existe) y guardarlo como número
        const valorInicial = input.value.replace(/\D/g, '');
        if (valorInicial) {
            input.dataset.valorReal = (parseInt(valorInicial, 10) / 100).toFixed(2);
            input.value = formatear(parseInt(valorInicial, 10));
        }

        // Al escribir, formatear el valor
        input.addEventListener('input', function(e) {
            let digitos = this.value.replace(/\D/g, '');

            if (digitos === '') {
                this.value = '';
                this.dataset.valorReal = '';
                return;
            }

            // Limitar a 14 dígitos (para evitar overflow)
            if (digitos.length > 14) {
                digitos = digitos.slice(0, 14);
            }

            const centavos = parseInt(digitos, 10);
            this.dataset.valorReal = (centavos / 100).toFixed(2);
            this.value = formatear(centavos);
        });

        // Al perder el foco, si está vacío, limpiar
        input.addEventListener('blur', function() {
            if (this.value === '' || this.value === '0,00') {
                this.value = '';
                this.dataset.valorReal = '';
            }
        });
    }

    function formatear(centavos) {
        const numero = centavos / 100;
        return numero.toLocaleString('es-VE', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    // Aplicar a todos los campos con la clase "mascara-monto"
    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('.mascara-monto').forEach(aplicarMascara);
    });
})();
