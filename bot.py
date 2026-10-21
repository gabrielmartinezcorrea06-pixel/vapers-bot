"""Bot de Telegram para registrar ventas de vapers en un Excel.

Comandos:
    /start, /help, /sabores, /hoy, /semana, /mes, /ultima, /deshacer, /excel.

Mensajes de texto libres se parsean a una venta con `parser.parsear_mensaje`.
"""

import logging
from keep_alive import keep_alive
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import SABORES, ZONA_HORARIA
from excel_manager import ExcelManager, Venta
from parser import parsear_mensaje

# ---------------------------- Logging --------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
# Bajamos el ruido de la librería http subyacente.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("vapers-bot")

# ---------------------------- Config ---------------------------------------

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AUTHORIZED_ID_RAW = os.getenv("TELEGRAM_AUTHORIZED_USER_ID", "").strip()
EXCEL_PATH = os.getenv("EXCEL_PATH", "ventas_vapers.xlsx")

try:
    AUTHORIZED_ID = int(AUTHORIZED_ID_RAW) if AUTHORIZED_ID_RAW else None
except ValueError:
    AUTHORIZED_ID = None
    logger.error("TELEGRAM_AUTHORIZED_USER_ID no es un entero válido: %r", AUTHORIZED_ID_RAW)

TZ = ZoneInfo(ZONA_HORARIA)
excel = ExcelManager(EXCEL_PATH)

# ---------------------------- Helpers --------------------------------------


def _autorizado(update: Update) -> bool:
    """True si el usuario que envía el mensaje es el autorizado en .env."""
    if AUTHORIZED_ID is None:
        # Sin user id configurado, por seguridad rechazamos a todos.
        return False
    user = update.effective_user
    return user is not None and user.id == AUTHORIZED_ID


async def _rechazar(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("🚫 No autorizado.")


def _fmt_eur(n: float) -> str:
    """Formatea un número como euros con coma decimal."""
    return f"{n:,.2f}€".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_resumen(titulo: str, resumen: dict) -> str:
    """Construye el texto Markdown de un resumen."""
    lineas = [f"📊 *{titulo}*",
              f"Ventas: {resumen['n_ventas']}",
              f"Unidades: {resumen['unidades']}",
              f"Total: {_fmt_eur(resumen['total'])}"]
    if resumen["por_sabor"]:
        lineas.append("\n*Por sabor:*")
        for sabor, datos in sorted(resumen["por_sabor"].items(), key=lambda x: -x[1]["total"]):
            lineas.append(f"• {sabor}: {datos['unidades']}u · {_fmt_eur(datos['total'])}")
    if resumen["por_pago"]:
        lineas.append("\n*Por método de pago:*")
        for metodo, datos in sorted(resumen["por_pago"].items(), key=lambda x: -x[1]["total"]):
            lineas.append(f"• {metodo}: {datos['unidades']}u · {_fmt_eur(datos['total'])}")
    return "\n".join(lineas)


# ---------------------------- Handlers -------------------------------------


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de ventas de vapers.\n\n"
        "Escríbeme algo como:\n"
        "  • `1 vaper sabor lemon lime en efectivo`\n"
        "  • `2 strawberry banana bizum`\n"
        "  • `vendí un mixed berry por 6€`\n\n"
        "Comandos: /help /sabores /hoy /semana /mes /ultima /deshacer /excel",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    await update.message.reply_text(
        "*Cómo usarme*\n\n"
        "Envíame un mensaje describiendo la venta. Detecto cantidad, sabor, "
        "método de pago y un precio total opcional.\n\n"
        "*Ejemplos:*\n"
        "• `1 vaper sabor lemon lime en efectivo`\n"
        "• `2 strawberry banana bizum`\n"
        "• `vendí un mixed berry por 6€ en efectivo`\n"
        "• `3 sex on the beach transferencia`\n"
        "• `monter mango efectivo` (acepta erratas)\n\n"
        "*Comandos:*\n"
        "/sabores - lista de sabores\n"
        "/hoy - resumen del día\n"
        "/semana - últimos 7 días\n"
        "/mes - mes actual\n"
        "/ultima - última venta\n"
        "/deshacer - borra la última venta\n"
        "/excel - envía el Excel",
        parse_mode="Markdown",
    )


async def cmd_sabores(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    texto = "🍓 *Sabores disponibles:*\n" + "\n".join(f"• {s}" for s in SABORES)
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_hoy(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    resumen = excel.resumen_hoy()
    await update.message.reply_text(_fmt_resumen("Hoy", resumen), parse_mode="Markdown")


async def cmd_semana(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    resumen = excel.resumen_semana()
    await update.message.reply_text(_fmt_resumen("Últimos 7 días", resumen), parse_mode="Markdown")


async def cmd_mes(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    resumen = excel.resumen_mes()
    await update.message.reply_text(_fmt_resumen("Mes actual", resumen), parse_mode="Markdown")


async def cmd_ultima(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    v = excel.ultima_venta()
    if v is None:
        await update.message.reply_text("Aún no hay ventas registradas.")
        return
    await update.message.reply_text(
        f"🧾 *Última venta*\n"
        f"{v.fecha.strftime('%d/%m/%Y')} {v.hora}\n"
        f"{v.cantidad}x {v.sabor}\n"
        f"Pago: {v.metodo_pago}\n"
        f"Total: {_fmt_eur(v.total)}",
        parse_mode="Markdown",
    )


async def cmd_deshacer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    # Confirmación simple en dos pasos vía estado en context.user_data.
    if context.user_data.get("confirmar_deshacer"):
        context.user_data["confirmar_deshacer"] = False
        try:
            v = excel.borrar_ultima_venta()
        except PermissionError:
            await update.message.reply_text(
                "⚠️ No puedo escribir en el Excel: cierra el archivo si lo tienes abierto."
            )
            return
        if v is None:
            await update.message.reply_text("No había ventas que borrar.")
        else:
            await update.message.reply_text(
                f"🗑 Borrada: {v.cantidad}x {v.sabor} ({_fmt_eur(v.total)})"
            )
        return

    v = excel.ultima_venta()
    if v is None:
        await update.message.reply_text("No hay ventas que deshacer.")
        return
    context.user_data["confirmar_deshacer"] = True
    await update.message.reply_text(
        f"⚠️ ¿Seguro que quieres borrar la última venta?\n"
        f"  {v.cantidad}x {v.sabor} · {_fmt_eur(v.total)}\n\n"
        f"Envía /deshacer otra vez para confirmar.",
    )


async def cmd_excel(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        return await _rechazar(update)
    enlace = "https://docs.google.com/spreadsheets/d/1ZnrhQXp7-jNI7dFFExswEF2C-mCJ57LVGgTaIB3-1FI/edit"
    await update.message.reply_text(f"📊 Puedes ver las ventas en tiempo real aquí:\n{enlace}")


async def msg_libre(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Trata cualquier mensaje de texto no-comando como una venta a parsear."""
    if not _autorizado(update):
        return await _rechazar(update)

    texto = update.message.text or ""
    res = parsear_mensaje(texto)

    if res.get("error"):
        sugerencia = res.get("sugerencia")
        if sugerencia:
            msg = f"❓ No reconocí el sabor. ¿Querías decir *{sugerencia}*?\n"
        else:
            msg = "❓ No pude interpretar el mensaje.\n"
        msg += "Usa /sabores para ver el catálogo o /help para ejemplos."
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    ahora = datetime.now(TZ)
    venta = Venta(
        fecha=ahora.date(),
        hora=ahora.strftime("%H:%M"),
        cantidad=res["cantidad"],
        sabor=res["sabor"],
        metodo_pago=res["metodo_pago"],
        precio_unitario=res["precio_unitario"],
        total=res["total"],
    )
    try:
        excel.registrar_venta(venta)
    except PermissionError:
        logger.exception("Permiso denegado al escribir Excel")
        await update.message.reply_text(
            "⚠️ No puedo escribir en el Excel. ¿Lo tienes abierto en otra ventana? "
            "Ciérralo y vuelve a enviar el mensaje."
        )
        return
    except Exception:
        logger.exception("Error al registrar venta")
        await update.message.reply_text("⚠️ Error inesperado al registrar la venta. Revisa bot.log.")
        return

    resumen = excel.resumen_hoy()
    await update.message.reply_text(
        f"✅ *Venta registrada*\n"
        f"🍓 {venta.cantidad}x {venta.sabor}\n"
        f"💰 Pago: {venta.metodo_pago}\n"
        f"💵 Total: {_fmt_eur(venta.total)}\n"
        f"📊 Hoy: {resumen['unidades']} unidades · {_fmt_eur(resumen['total'])}",
        parse_mode="Markdown",
    )


async def err_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Captura excepciones no manejadas dentro de los handlers."""
    logger.exception("Excepción en handler", exc_info=context.error)


# ---------------------------- Main -----------------------------------------


def main() -> None:
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env")
    if AUTHORIZED_ID is None:
        logger.warning(
            "TELEGRAM_AUTHORIZED_USER_ID no configurado: el bot rechazará a todos los usuarios."
        )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("sabores", cmd_sabores))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(CommandHandler("mes", cmd_mes))
    app.add_handler(CommandHandler("ultima", cmd_ultima))
    app.add_handler(CommandHandler("deshacer", cmd_deshacer))
    app.add_handler(CommandHandler("excel", cmd_excel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_libre))
    app.add_error_handler(err_handler)

    logger.info("Bot arrancando. Excel en %s", EXCEL_PATH)
    keep_alive()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
