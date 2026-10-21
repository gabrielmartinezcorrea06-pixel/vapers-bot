"""Configuración global del bot: catálogo de sabores, precios y métodos de pago."""

# Catálogo oficial de sabores. El matcher difuso tolera erratas como "monter mango".
SABORES = [
    "lemon lime",
    "strawberry banana",
    "mixed berry",
    "strawberry watermelon",
    "pina colada",
    "cherry cola",
    "strawberry kiwi",
    "watermelon ice",
    "sex on the beach",
    "monster mango",
]

# Precio unitario por defecto en euros. Se puede sobrescribir desde la hoja "Catálogo" del Excel.
PRECIO_UNITARIO = 13.00

# Métodos de pago aceptados (en minúsculas, el parser normaliza la entrada).
METODOS_PAGO = ["efectivo", "bizum", "transferencia", "tarjeta", "paypal"]

# Umbral mínimo de confianza para el matching difuso de sabores (0-100).
UMBRAL_FUZZY = 75

# Zona horaria para timestamps.
ZONA_HORARIA = "Europe/Madrid"
