import logging
import gspread
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from config import PRECIO_UNITARIO, SABORES, ZONA_HORARIA

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_FILE = "credenciales.json"
SHEET_ID = "1ZnrhQXp7-jNI7dFFExswEF2C-mCJ57LVGgTaIB3-1FI"

@dataclass
class Venta:
    fecha: date
    hora: str
    cantidad: int
    sabor: str
    metodo_pago: str
    precio_unitario: float
    total: float

def _conectar():
    import os, json, tempfile
    gc_json = os.getenv("GOOGLE_CREDENTIALS")
    if gc_json:
        info = json.loads(gc_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

class ExcelManager:
    def __init__(self, ruta):
        self.tz = ZoneInfo(ZONA_HORARIA)
        self.sh = _conectar()
        self.ws = self.sh.sheet1

    def cargar_precios_catalogo(self):
        return {s: PRECIO_UNITARIO for s in SABORES}

    def registrar_venta(self, venta):
        self.ws.append_row([venta.fecha.strftime("%d/%m/%Y"), venta.hora, venta.cantidad, venta.sabor, venta.metodo_pago.capitalize(), venta.precio_unitario, venta.total])
        logger.info("Venta: %sx %s = %.2f", venta.cantidad, venta.sabor, venta.total)

    def listar_ventas(self):
        registros = self.ws.get_all_values()
        ventas = []
        for fila in registros[1:]:
            if not fila or not fila[0]:
                continue
            try:
                ventas.append(Venta(fecha=datetime.strptime(fila[0], "%d/%m/%Y").date(), hora=fila[1], cantidad=int(fila[2]), sabor=fila[3], metodo_pago=fila[4], precio_unitario=float(fila[5]), total=float(fila[6])))
            except:
                pass
        return ventas

    def borrar_ultima_venta(self):
        registros = self.ws.get_all_values()
        if len(registros) < 2:
            return None
        ultima = registros[-1]
        try:
            v = Venta(fecha=datetime.strptime(ultima[0], "%d/%m/%Y").date(), hora=ultima[1], cantidad=int(ultima[2]), sabor=ultima[3], metodo_pago=ultima[4], precio_unitario=float(ultima[5]), total=float(ultima[6]))
            self.ws.delete_rows(len(registros))
            return v
        except:
            return None

    def _ahora(self):
        return datetime.now(self.tz)

    def resumen_periodo(self, desde, hasta):
        ventas = [v for v in self.listar_ventas() if desde <= v.fecha <= hasta]
        total = round(sum(v.total for v in ventas), 2)
        unidades = sum(v.cantidad for v in ventas)
        por_sabor = {}
        for v in ventas:
            d = por_sabor.setdefault(v.sabor, {"unidades": 0, "total": 0.0})
            d["unidades"] += v.cantidad
            d["total"] = round(d["total"] + v.total, 2)
        por_pago = {}
        for v in ventas:
            d = por_pago.setdefault(v.metodo_pago, {"unidades": 0, "total": 0.0})
            d["unidades"] += v.cantidad
            d["total"] = round(d["total"] + v.total, 2)
        return {"total": total, "unidades": unidades, "por_sabor": por_sabor, "por_pago": por_pago, "n_ventas": len(ventas)}

    def resumen_hoy(self):
        hoy = self._ahora().date()
        return self.resumen_periodo(hoy, hoy)

    def resumen_semana(self):
        hoy = self._ahora().date()
        return self.resumen_periodo(hoy - timedelta(days=6), hoy)

    def resumen_mes(self):
        hoy = self._ahora().date()
        return self.resumen_periodo(hoy.replace(day=1), hoy)

    def ultima_venta(self):
        ventas = self.listar_ventas()
        return ventas[-1] if ventas else None


