# -*- coding: utf-8 -*-
"""Finalmente · bot de la cartelera de ALEs y optativas.

Lee la cartelera pública de la Facultad, guarda cada publicación en la base
(el archivo histórico) y avisa por Telegram las que son nuevas.

Corre solo, cada 5 minutos, desde GitHub Actions. Necesita estas variables:
  TELEGRAM_TOKEN          token del bot (BotFather)
  TELEGRAM_CHAT_ID        el canal donde publica
  SUPABASE_URL            https://<proyecto>.supabase.co
  SUPABASE_KEY            clave secreta del proyecto (nunca la pública)
  TELEGRAM_ADMIN_CHAT_ID  opcional: tu chat privado con el bot, para alertas

Para probar sin tocar nada:  python finalmente_bot.py --prueba
"""
import hashlib
import html
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

URL = "https://www.econ.unicen.edu.ar/alumnos/ale/ofertas-ale-y-optativas"
UA = "Mozilla/5.0 (compatible; FinalmenteBot/1.0; +mailto:contacto@finalmente.app)"

PAGINAS_POR_CORRIDA = 2     # las 20 publicaciones más nuevas alcanzan para no perder nada
PAGINAS_MAXIMAS = 15        # tope de la primera corrida, que guarda el historial entero
FRENO_DE_MANO = 5           # más novedades juntas que esto casi siempre es el parser roto
LARGO_DESCRIPCION = 700
LARGO_CAMPO = 350


# ------------------------------------------------------------------ la cartelera
def bajar_pagina(n):
    r = requests.get(URL, params={"page": n} if n else None, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    return r.text


def _limpio(t):
    return re.sub(r"\s+", " ", t or "").strip()


def _nombre_propio(t):
    """'Lucía ELISSONDO' -> 'Lucía Elissondo'."""
    return " ".join(p.capitalize() if p.isupper() and len(p) > 1 else p for p in t.split())


def leer_tarjetas(pagina_html):
    """Devuelve una lista de publicaciones, de la más nueva a la más vieja."""
    s = BeautifulSoup(pagina_html, "html.parser")
    tarjetas = []
    for li in s.select("main .view-content ul.list-group > li"):
        h3, h2 = li.find("h3"), li.find("h2")
        encabezado = _limpio((h3 or h2).get_text(" ")) if (h3 or h2) else ""
        m = re.match(r"^([A-Z]{2,3}\d+)\s+(.*)$", encabezado)
        codigo, titulo = (m.group(1), m.group(2)) if m else ("", encabezado)

        campos = {}
        for f in li.select("[class*='field--name-']"):
            clase = next((c for c in f.get("class", []) if c.startswith("field--name-")), None)
            if not clase:
                continue
            nombre = clase[len("field--name-"):]
            if nombre.startswith("field-"):
                nombre = nombre[len("field-"):]
            nombre = nombre.strip("-")
            if nombre in campos:
                continue
            items = f.select(".field__item")
            if items:
                valor = " ".join(_limpio(i.get_text(" ")) for i in items)
            else:
                valor = _limpio(f.get_text(" "))
                etiqueta = f.select_one(".field__label")
                if etiqueta:
                    valor = _limpio(valor.replace(_limpio(etiqueta.get_text(" ")), "", 1))
            if nombre in ("docente-a-cargo", "responsable", "responsable-otro"):
                valor = _nombre_propio(valor)
            if valor:
                campos[nombre] = valor

        if "modalidad-ale" in campos:
            tipo = "ALE"
        elif codigo.startswith("MO"):
            tipo = "Optativa"
        else:
            tipo = "Otro"

        huella = hashlib.sha256(
            json.dumps({"codigo": codigo, "titulo": titulo, "campos": campos},
                       ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        tarjetas.append({
            "huella": huella, "codigo": codigo, "titulo": titulo or "(sin título)",
            "tipo": tipo, "campos": campos, "html_crudo": str(li),
        })
    return tarjetas


def leer_cartelera(paginas):
    vistas, todas = set(), []
    for n in range(paginas):
        tarjetas = leer_tarjetas(bajar_pagina(n))
        if not tarjetas:
            break
        for t in tarjetas:
            if t["huella"] not in vistas:
                vistas.add(t["huella"])
                todas.append(t)
        if n + 1 < paginas:
            time.sleep(1.5)  # sin apuro: la Facultad no tiene por qué notar que existimos
    return todas


# ------------------------------------------------------------------ el mensaje
def _corto(t, n):
    t = _limpio(t)
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def armar_mensaje(t, es_novedad):
    c, e = t["campos"], html.escape
    if es_novedad:
        cabeza = "NOVEDAD · " + {"Optativa": "OPTATIVA", "ALE": "ALE"}.get(t["tipo"], "CARTELERA")
    elif t["tipo"] == "Optativa":
        cabeza = "NUEVA OPTATIVA"
    elif t["tipo"] == "ALE":
        cabeza = "NUEVA ALE"
    else:
        cabeza = "NUEVO EN LA CARTELERA"
    if t["tipo"] == "ALE" and c.get("modalidad-ale"):
        cabeza += " · " + c["modalidad-ale"]

    nombre = (t["codigo"] + " · " if t["codigo"] else "") + t["titulo"]
    lineas = ["<b>%s</b>" % e(cabeza), "<b>%s</b>" % e(nombre), ""]

    persona = c.get("docente-a-cargo") or c.get("responsable")
    if persona:
        if c.get("responsable-otro"):
            persona += ", " + c["responsable-otro"]
        lineas.append("%s: %s" % ("Docente" if t["tipo"] == "Optativa" else "Responsable", e(persona)))
    for clave, etiqueta in (("fecha-lugar-y-horario", "Cuándo y dónde"), ("horas-ale", "Horas"),
                            ("inscripcion", "Inscripción"), ("requisitos", "Requisitos")):
        if c.get(clave):
            lineas.append("<b>%s:</b> %s" % (etiqueta, e(_corto(c[clave], LARGO_CAMPO))))
    minimo = re.findall(r"\d+", c.get("cupo-minimo", ""))
    maximo = re.findall(r"\d+", c.get("cupo-maximo", ""))
    if minimo or maximo:
        a, b = (minimo or maximo)[0], (maximo or minimo)[0]
        rango = a if a == b else "%s a %s" % (a, b)
        lineas.append("<b>Cupo:</b> %s %s" % (rango, "alumno" if rango == "1" else "alumnos"))
    if c.get("body"):
        lineas += ["", e(_corto(c["body"], LARGO_DESCRIPCION))]
    lineas += ["", "Te anotás por SIU Guaraní.", '<a href="%s">Ver en la cartelera de la Facultad</a>' % URL]
    return "\n".join(lineas)


# ------------------------------------------------------------------ la base
class ErrorBase(Exception):
    """Un problema de configuración de Supabase, explicado en castellano."""


class Base:
    def __init__(self, url, clave):
        url, clave = url.strip(), clave.strip()
        # el panel de Supabase a veces muestra la dirección con /rest/v1/ al final: se acepta igual
        url = re.sub(r"/rest/v1/?$", "", url.rstrip("/"))
        if not re.match(r"^https://[a-z0-9-]+\.supabase\.co/?$", url):
            raise ErrorBase(
                "SUPABASE_URL no tiene la forma https://<proyecto>.supabase.co. Si la copiaste de la barra del "
                "navegador (supabase.com/dashboard/...), esa es la dirección del panel; la del proyecto está en "
                "Project Settings > Data API, o en el botón Connect.")
        if clave.startswith("sb_publishable_"):
            raise ErrorBase("SUPABASE_KEY es la clave pública (publishable). Tiene que ser la secreta: sb_secret_...")
        self.api = url.rstrip("/") + "/rest/v1/publicaciones"
        self.h = {"apikey": clave, "Content-Type": "application/json"}
        if clave.startswith("eyJ"):  # las claves viejas son JWT y van también como Bearer
            self.h["Authorization"] = "Bearer " + clave

    def _pedir(self, metodo, **kw):
        try:
            r = requests.request(metodo, self.api, timeout=30, **kw)
        except requests.RequestException as err:
            raise ErrorBase("No pude conectarme a Supabase (%s). Revisá SUPABASE_URL." % type(err).__name__)
        if r.ok:
            return r
        try:
            d = r.json()
        except ValueError:
            d = {}
        codigo, detalle = d.get("code", ""), d.get("message") or r.text[:200]
        if codigo == "PGRST205" or "does not exist" in detalle or "schema cache" in detalle:
            pista = ("La tabla publicaciones no existe en este proyecto: corré supabase.sql en el SQL Editor "
                     "del MISMO proyecto cuya URL cargaste.")
        elif r.status_code == 401:
            pista = "La clave no sirve: tiene que ser la secreta (sb_secret_... o service_role), copiada entera."
        elif r.status_code == 403 or codigo == "42501":
            pista = "La clave no tiene permiso sobre la tabla: tiene que ser la secreta, no la publishable."
        elif r.status_code == 404:
            pista = "Supabase no encontró la dirección: revisá que SUPABASE_URL sea la del proyecto."
        else:
            pista = ""
        raise ErrorBase("Supabase respondió %d %s: %s. %s" % (r.status_code, codigo, detalle, pista))

    def _get(self, params):
        return self._pedir("GET", headers=self.h, params=params).json()

    def vacia(self):
        return len(self._get({"select": "id", "limit": "1"})) == 0

    def huellas_existentes(self, huellas):
        if not huellas:
            return set()
        filas = self._get({"select": "huella", "huella": "in.(%s)" % ",".join(huellas)})
        return {f["huella"] for f in filas}

    def codigos_vistos(self, codigos):
        codigos = [c for c in codigos if c]
        if not codigos:
            return set()
        filas = self._get({"select": "codigo", "codigo": "in.(%s)" % ",".join(codigos)})
        return {f["codigo"] for f in filas}

    def guardar(self, tarjetas, estado):
        if not tarjetas:
            return
        filas = [dict(huella=t["huella"], codigo=t["codigo"] or None, titulo=t["titulo"], tipo=t["tipo"],
                      campos=t["campos"], html_crudo=t["html_crudo"], fuente=URL, estado=estado)
                 for t in tarjetas]
        h = dict(self.h, Prefer="resolution=ignore-duplicates,return=minimal")
        self._pedir("POST", headers=h, params={"on_conflict": "huella"}, data=json.dumps(filas))


# ------------------------------------------------------------------ Telegram
def enviar_telegram(token, chat_id, texto):
    r = requests.post(
        "https://api.telegram.org/bot%s/sendMessage" % token,
        json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML",
              "link_preview_options": {"is_disabled": True}},
        timeout=20,
    )
    datos = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not datos.get("ok"):
        raise RuntimeError("Telegram rechazó el mensaje: %s" % datos.get("description", r.status_code))


# ------------------------------------------------------------------ la corrida
def prueba():
    tarjetas = leer_tarjetas(bajar_pagina(0))
    print("Leí %d publicaciones en la primera página.\n" % len(tarjetas))
    for t in tarjetas[:3]:
        print(armar_mensaje(t, es_novedad=False))
        print("\n" + "-" * 60 + "\n")


def corrida():
    falta = [v for v in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "SUPABASE_URL", "SUPABASE_KEY") if not os.environ.get(v)]
    if falta:
        sys.exit("Faltan variables: " + ", ".join(falta))
    token, canal = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    admin = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    base = Base(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    primera = base.vacia()
    try:
        tarjetas = leer_cartelera(PAGINAS_MAXIMAS if primera else PAGINAS_POR_CORRIDA)
    except requests.RequestException as err:
        # si la página de la Facultad está caída, no es un problema del bot: se reintenta en 5 minutos
        print("La cartelera no respondió (%s). Pruebo en la próxima corrida." % err)
        return
    if not tarjetas:
        sys.exit("La página respondió pero no encontré ninguna publicación: puede que hayan cambiado el diseño.")

    if primera:
        base.guardar(tarjetas, "silenciosa")
        print("Primera corrida: guardé %d publicaciones en el archivo, sin avisar." % len(tarjetas))
        return

    conocidas = base.huellas_existentes([t["huella"] for t in tarjetas])
    nuevas = [t for t in tarjetas if t["huella"] not in conocidas]
    if not nuevas:
        print("Sin novedades (%d publicaciones revisadas)." % len(tarjetas))
        return

    if len(nuevas) > FRENO_DE_MANO:
        base.guardar(nuevas, "retenida")
        aviso = ("Freno de mano: aparecieron %d novedades juntas y no las publiqué. "
                 "Casi siempre es que cambió la página. Revisá antes de mandarlas." % len(nuevas))
        if admin:
            enviar_telegram(token, admin, aviso)
        sys.exit(aviso)

    vistos = base.codigos_vistos([t["codigo"] for t in nuevas])
    for t in reversed(nuevas):  # la más vieja primero, así el canal queda en orden
        enviar_telegram(token, canal, armar_mensaje(t, es_novedad=t["codigo"] in vistos))
        base.guardar([t], "publicada")
        print("Publicada: %s %s" % (t["codigo"], t["titulo"]))
        time.sleep(1)


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    else:
        try:
            corrida()
        except ErrorBase as err:
            sys.exit("PROBLEMA CON SUPABASE: %s" % err)
