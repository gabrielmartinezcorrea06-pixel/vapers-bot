"""Parser de mensajes en lenguaje natural a registros de venta estructurados."""

import re
from dataclasses import dataclass
from typing import Optional

from thefuzz import fuzz, process
from config import METODOS_PAGO, PRECIO_UNITARIO, SABORES, UMBRAL_FUZZY


@dataclass
class ResultadoParseo:
    """Resultado de parsear un mensaje. Si `error` no es None, el resto puede ser parcial."""
    cantidad: int = 1
    sabor: Optional[str] = None
    metodo_pago: str = "efectivo"
    precio_unitario: float = PRECIO_UNITARIO
    total: float = 0.0
    error: Optional[str] = None
    sugerencia: Optional[str] = None


# Palabras que filtramos antes de buscar el sabor para reducir ruido.
_STOPWORDS = {
    "vaper", "vapers", "vape", "sabor", "de", "un", "una", "uno",
    "vendi", "vendí", "vendido", "por", "en", "con", "el", "la", "los", "las",
    "y", "a", "al", "del",
}


def _normalizar(texto: str) -> str:
    """Pasa a minúsculas y limpia caracteres no alfanuméricos manteniendo espacios."""
    texto = texto.lower().strip()
    # Mantenemos letras, números, espacios, € y separadores decimales (. ,) para precios.
    texto = re.sub(r"[^\w\s€.,]", " ", texto, flags=re.UNICODE)
    return re.sub(r"\s+", " ", texto).strip()


def _extraer_cantidad(texto: str) -> tuple[int, str]:
    """Devuelve (cantidad, texto_sin_cantidad). Por defecto 1.

    Busca el primer dígito entero standalone del texto (no fracciones de precios:
    por eso conviene haber retirado el precio antes). También detecta "un"/"una"/"uno".
    """
    # Primer entero standalone: rodeado por inicio/espacio y por espacio/fin.
    m = re.search(r"(?:^|\s)(\d+)(?=\s|$)", texto)
    if m:
        cantidad = int(m.group(1))
        texto_limpio = (texto[:m.start()] + " " + texto[m.end():]).strip()
        return cantidad, re.sub(r"\s+", " ", texto_limpio)

    # "un"/"una"/"uno" como artículo indefinido (palabra completa).
    m = re.search(r"\b(un|una|uno)\b", texto, flags=re.IGNORECASE)
    if m:
        texto_limpio = (texto[:m.start()] + " " + texto[m.end():]).strip()
        return 1, re.sub(r"\s+", " ", texto_limpio)

    return 1, texto


def _extraer_precio(texto: str) -> tuple[Optional[float], str]:
    """Detecta precios explícitos como "por 6€", "8 euros", "a 7€".

    Devuelve (precio_o_None, texto_sin_precio).
    """
    patrones = [
        r"\bpor\s+(\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?)?\b",
        r"\ba\s+(\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?)\b",
        r"\b(\d+(?:[.,]\d+)?)\s*(?:€|eur|euros?)\b",
    ]
    for patron in patrones:
        m = re.search(patron, texto, flags=re.IGNORECASE)
        if m:
            valor = float(m.group(1).replace(",", "."))
            texto_limpio = (texto[:m.start()] + " " + texto[m.end():]).strip()
            return valor, re.sub(r"\s+", " ", texto_limpio)
    return None, texto


def _extraer_metodo_pago(texto: str) -> tuple[Optional[str], str]:
    """Busca un método de pago conocido en el texto y lo retira."""
    for metodo in METODOS_PAGO:
        patron = rf"\b{re.escape(metodo)}\b"
        if re.search(patron, texto, flags=re.IGNORECASE):
            texto_limpio = re.sub(patron, " ", texto, flags=re.IGNORECASE)
            return metodo, re.sub(r"\s+", " ", texto_limpio).strip()
    return None, texto


def _extraer_sabor(texto: str) -> tuple[Optional[str], int, Optional[str]]:
    """Busca el sabor más parecido al texto restante.

    Devuelve (sabor_canonico, score, sugerencia). Usa rapidfuzz con WRatio que
    funciona bien con frases cortas y permite variaciones de orden y erratas.
    """
    palabras = [p for p in texto.split() if p not in _STOPWORDS]
    candidato = " ".join(palabras).strip()
    if not candidato:
        return None, 0, None

    # Buscamos el mejor match contra el catálogo.
    resultado = process.extractOne(candidato, SABORES, scorer=fuzz.WRatio)
    if resultado is None:
        return None, 0, None

    sabor, score = resultado
    if score >= UMBRAL_FUZZY:
        return sabor, int(score), None
    return None, int(score), sabor


def parsear_mensaje(texto: str) -> dict:
    """Parsea un mensaje libre y devuelve un dict con los campos de la venta.

    Campos del dict resultado:
        cantidad, sabor, metodo_pago, precio_unitario, total, error, sugerencia.
    """
    if not texto or not texto.strip():
        r = ResultadoParseo(error="Mensaje vacío.")
        return r.__dict__

    normalizado = _normalizar(texto)

    # Orden importante: precio antes que cantidad para evitar que el "5" de "5€"
    # se interprete como cantidad de unidades.
    precio_explicito, resto = _extraer_precio(normalizado)
    cantidad, resto = _extraer_cantidad(resto)
    metodo, resto = _extraer_metodo_pago(resto)
    sabor, score, sugerencia = _extraer_sabor(resto)

    if sabor is None:
        r = ResultadoParseo(
            cantidad=cantidad,
            metodo_pago=metodo or "efectivo",
            error=f"No reconocí el sabor (score {score}).",
            sugerencia=sugerencia,
        )
        return r.__dict__

    # Si el usuario indicó un precio total explícito, calculamos el unitario a partir de él.
    if precio_explicito is not None:
        total = precio_explicito
        precio_unitario = round(precio_explicito / cantidad, 2) if cantidad else precio_explicito
    else:
        precio_unitario = PRECIO_UNITARIO
        total = round(precio_unitario * cantidad, 2)

    r = ResultadoParseo(
        cantidad=cantidad,
        sabor=sabor,
        metodo_pago=metodo or "efectivo",
        precio_unitario=precio_unitario,
        total=total,
    )
    return r.__dict__
