import os

def generar_arbol(ruta_dir, prefijo=""):
    # Filtros opcionales para ignorar carpetas pesadas u ocultas (ej. entorno virtual, caché)
    ignorar = {'.git', '__pycache__', 'env', 'venv', '.idea', '.vscode'}
    
    try:
        elementos = sorted(os.listdir(ruta_dir))
    except PermissionError:
        return

    # Filtrar elementos que no queremos mostrar
    elementos = [e for e in elementos if e not in ignorar]
    
    for i, elemento in enumerate(elementos):
        ruta_completa = os.path.join(ruta_dir, elemento)
        es_ultimo = (i == len(elementos) - 1)
        
        # Seleccionar el caracter conector adecuado
        conector = "└── " if es_ultimo else "├── "
        
        # Imprimir la línea actual
        print(f"{prefijo}{conector}{elemento}")
        
        # Si es un directorio, hacer la llamada recursiva sumando el prefijo visual
        if os.path.isdir(ruta_completa):
            nuevo_prefijo = prefijo + ("    " if es_ultimo else "│   ")
            generar_arbol(ruta_completa, nuevo_prefijo)

if __name__ == "__main__":
    # Obtiene el nombre de la carpeta raíz actual
    raiz = os.path.basename(os.getcwd())
    print(f"{raiz}/")
    generar_arbol(".")
