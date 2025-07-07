from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from apscheduler.schedulers.background import BackgroundScheduler
from database import citas_collection, historial_collection, encuestas_collection
from datetime import datetime, timedelta
import re
import pytz

app = FastAPI()
usuarios_estado = {}

# 🕒 Inicia el scheduler
scheduler = BackgroundScheduler()
scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    try:
        body = await request.form()
    except:
        body = await request.json()
    mensaje = body.get("Body").strip().lower()
    numero = body.get("From")

    print(f"📩 Mensaje recibido de {numero}: {mensaje}")
    estado = usuarios_estado.get(numero, {"paso": "inicio"})

    if estado["paso"] == "inicio":
        usuarios_estado[numero] = {"paso": "seleccion_servicio"}
        respuesta = (
            "✨ Hola, bienvenida al Consultorio Integral Vida Sana ✨\n\n"
            "Por favor, selecciona el servicio que deseas agendar:\n"
            "1️⃣ Medicina Interna\n"
            "2️⃣ Medicina Ocupacional\n"
            "3️⃣ Tratamientos Estéticos\n\n"
            "Responde con el número de la opción 😉"
        )

    elif estado["paso"] == "seleccion_servicio":
        servicios = {"1": "Medicina Interna", "2": "Medicina Ocupacional", "3": "Tratamientos Estéticos"}
        servicio = servicios.get(mensaje)
        if servicio:
            usuarios_estado[numero]["servicio"] = servicio
            usuarios_estado[numero]["paso"] = "solicitar_fecha"
            respuesta = (
                f"Perfecto, agendaremos tu consulta de *{servicio}* 💉💋\n"
                "¿Tienes una fecha y hora tentativas? Escríbemela así:\n"
                "📅 *25/07 a las 10:30am*"
            )
        else:
            respuesta = "Ups... no entendí tu selección 😅\nPor favor responde con *1, 2 o 3*."

    elif estado["paso"] == "solicitar_fecha":
        if "ver disponibilidad" in mensaje:
            respuesta = "📆 Aquí tienes horarios sugeridos:\n🕘 9:00am\n🕚 11:30am\n🕒 3:00pm"
        else:
            match = re.search(r"(\d{1,2})/(\d{1,2})\s*(a\s*las\s*)?(\d{1,2})(:(\d{2}))?\s*([ap]m)", mensaje)
            if match:
                dia, mes, hora, _, minutos, _, ampm = match.groups()
                hora = int(hora)
                minutos = int(minutos) if minutos else 0
                if ampm == "pm" and hora != 12:
                    hora += 12
                elif ampm == "am" and hora == 12:
                    hora = 0
                año_actual = datetime.now().year
                fecha_hora = datetime(año_actual, int(mes), int(dia), hora, minutos)
                usuarios_estado[numero]["fecha_hora"] = fecha_hora
                usuarios_estado[numero]["paso"] = "confirmar"
                servicio = usuarios_estado[numero]["servicio"]
                respuesta = (
                    f"📌 ¿Confirmas tu cita de *{servicio}* para el *{fecha_hora.strftime('%d/%m a las %I:%M %p')}*?\n"
                    "Responde *sí* para confirmar o *no* para cambiar la hora 💋"
                )
            else:
                respuesta = "Formato inválido 😕. Usa: *25/07 a las 10:30am*"

    elif estado["paso"] == "confirmar":
        if mensaje == "sí":
            servicio = usuarios_estado[numero]["servicio"]
            fecha_hora = usuarios_estado[numero]["fecha_hora"]

            cita_existente = await citas_collection.find_one({"fecha_hora": fecha_hora})
            if cita_existente:
                usuarios_estado[numero]["paso"] = "solicitar_fecha"
                respuesta = (
                    "💔 Lo siento, ese horario ya está reservado.\n"
                    "¿Puedes darme otra fecha y hora tentativas?"
                )
            else:
                nueva_cita = {
                    "numero": numero,
                    "servicio": servicio,
                    "fecha_hora": fecha_hora,
                    "estado": "confirmada"
                }
                await citas_collection.insert_one(nueva_cita)

                # 🔁 Guardar en historial
                await historial_collection.update_one(
                    {"numero": numero},
                    {"$push": {"citas": {
                        "servicio": servicio,
                        "fecha": fecha_hora,
                        "estado": "confirmada"
                    }}},
                    upsert=True
                )

                # 📤 Programar encuesta 1 hora después
                scheduler.add_job(
                    enviar_encuesta_post_cita,
                    "date",
                    run_date=fecha_hora + timedelta(hours=1),
                    args=[numero, servicio, fecha_hora]
                )

                usuarios_estado[numero]["paso"] = "completado"
                respuesta = (
                    f"🎉 ¡Cita confirmada para *{servicio}* el {fecha_hora.strftime('%d/%m a las %I:%M %p')}!\n"
                    "Te esperamos con mucho cariño 💉💖"
                )
                print(f"🔔 NUEVA CITA CONFIRMADA: {numero} - {servicio} - {fecha_hora}")

        elif mensaje == "no":
            usuarios_estado[numero]["paso"] = "solicitar_fecha"
            respuesta = "Entiendo, amor. Entonces dime otra fecha y hora que te convenga 🕒"

        else:
            respuesta = "Responde con *sí* para confirmar o *no* para cambiar la hora, mi cielo 😘"

    elif estado["paso"] == "encuesta":
        try:
            puntuacion = int(mensaje)
            if 1 <= puntuacion <= 5:
                await encuestas_collection.insert_one({
                    "numero": numero,
                    "servicio": estado.get("servicio"),
                    "fecha_cita": estado.get("fecha_hora"),
                    "puntuacion": puntuacion
                })
                await historial_collection.update_one(
                    {"numero": numero, "citas.fecha": estado.get("fecha_hora")},
                    {"$set": {"citas.$.encuesta": puntuacion}}
                )
                usuarios_estado[numero] = {"paso": "inicio"}
                respuesta = "✨ Gracias por tu valoración 💖 ¡Nos ayuda a mejorar!"
            else:
                respuesta = "Responde con un número del 1 al 5, por favor 💋"
        except:
            respuesta = "Responde solo con un número del 1 al 5 🌟"

    else:
        respuesta = "Escribe *hola* para comenzar una nueva cita 🩺✨"

    return PlainTextResponse(content=responder_formato_twilio(respuesta))

def responder_formato_twilio(mensaje: str):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{mensaje}</Message>
</Response>"""

# 🔁 Función de encuesta post-cita
def enviar_encuesta_post_cita(numero: str, servicio: str, fecha_hora: datetime):
    usuarios_estado[numero] = {
        "paso": "encuesta",
        "servicio": servicio,
        "fecha_hora": fecha_hora
    }
    print(f"📨 Enviando encuesta a {numero}...")
    # Este texto solo será procesado si el cliente responde algo en ese momento
    # (porque el bot se activa por entrada de usuario)
