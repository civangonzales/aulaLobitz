import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.core.exceptions import ValidationError
from academico.models import AIConfiguration


def complete(prompt, *, system_prompt=None, images=None):
    try:
        from cryptography.fernet import Fernet
        config = AIConfiguration.objects.get(pk=1)
        api_key = Fernet(settings.DEEPSEEK_ENCRYPTION_KEY.encode()).decrypt(config.encrypted_api_key.encode()).decode()
    except AIConfiguration.DoesNotExist as exc:
        raise ValidationError("El administrador aún no ha configurado DeepSeek.") from exc
    except Exception as exc:
        raise ValidationError("No se pudo descifrar la configuración de DeepSeek. Verifica la clave del servidor.") from exc
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    content = prompt
    if images:
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": image, "detail": "original"}}
            for image in images
        ]
    messages.append({"role": "user", "content": content})
    body = json.dumps({"model": config.vision_model if images else config.model, "messages": messages, "temperature": 0.3}).encode()
    req = Request(config.base_url.rstrip("/") + "/chat/completions", data=body,
                  headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with urlopen(req, timeout=settings.DEEPSEEK_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read())
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValidationError("La respuesta de IA quedó incompleta. Reduce la cantidad de preguntas o el alcance y vuelve a intentarlo.")
        result = choice["message"]["content"]
        if not isinstance(result, str) or not result.strip():
            raise ValidationError("DeepSeek respondió sin contenido. Vuelve a intentarlo.")
        return result
    except HTTPError as exc:
        if exc.code in (401, 403):
            message = "DeepSeek rechazó la conexión. Pide al administrador revisar la clave API y los permisos del modelo."
        elif exc.code == 429:
            message = "DeepSeek está limitando las solicitudes o la cuenta no tiene saldo disponible. Reintenta más tarde y revisa la cuenta."
        elif images and exc.code == 400:
            message = "DeepSeek no aceptó la imagen. Revisa que el modelo de imágenes configurado admita visión y que el mapa sea legible."
        else:
            message = f"DeepSeek no pudo procesar la solicitud (HTTP {exc.code}). Vuelve a intentarlo."
        raise ValidationError(message) from exc
    except (TimeoutError, URLError) as exc:
        raise ValidationError("No se pudo completar la conexión con DeepSeek a tiempo. Tu material sigue guardado; puedes reintentar.") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValidationError("La respuesta de DeepSeek no tiene el formato esperado. Vuelve a intentarlo.") from exc
