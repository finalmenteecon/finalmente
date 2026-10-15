# Finalmente · bot de la cartelera

Lee la [cartelera pública de ALEs y optativas](https://www.econ.unicen.edu.ar/alumnos/ale/ofertas-ale-y-optativas) de la Facultad de Ciencias Económicas de la UNICEN cada 5 minutos, guarda cada publicación y avisa las nuevas por Telegram.

Lo que la Facultad saca de la cartelera, acá queda guardado.

## Cómo funciona

- Cada publicación se reconoce por su contenido. Si la Facultad edita una tarjeta (cambia el aula, reabre la inscripción), sale como novedad.
- La primera vez que corre guarda todo lo que ya está publicado sin avisar, para no mandar al canal cuarenta publicaciones viejas de golpe.
- Si aparecen más de 5 novedades juntas no publica nada y avisa: casi siempre significa que cambió la página, no que salieron cinco ALEs en cinco minutos.
- Para anotarte en algo, siempre SIU Guaraní. El bot no pide ni usa credenciales de nadie.

## Configuración

Corre con GitHub Actions (`.github/workflows/cartelera.yml`). Necesita estos secretos del repositorio:

| Secreto | Qué es |
|---|---|
| `TELEGRAM_TOKEN` | El token del bot |
| `TELEGRAM_CHAT_ID` | El canal donde publica |
| `SUPABASE_URL` | La dirección del proyecto de Supabase |
| `SUPABASE_KEY` | La clave secreta del proyecto |
| `TELEGRAM_ADMIN_CHAT_ID` | Opcional: a quién avisarle si se activa el freno de mano |

La tabla se crea con `supabase.sql`.

Para ver cómo saldrían los mensajes, sin tocar la base ni el canal:

```
pip install -r requirements.txt
python finalmente_bot.py --prueba
```
