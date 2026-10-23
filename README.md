# aulaLobitz — aplicación Django por capas

## Arquitectura

- `academico/presentation`: vistas, formularios y rutas HTTP.
- `academico/application`: casos de uso y coordinación de transacciones.
- `academico/domain`: reglas de negocio y validaciones.
- `academico/infrastructure`: acceso a datos y cliente DeepSeek.
- `academico/models.py`: entidades persistidas por Django ORM.
- `templates/` y `static/`: interfaz web.

La jerarquía académica es `Usuario → Ciclo → Curso → Sesión`. Cada sesión conserva sus archivos, resultados generados y evaluaciones.

## Instrucciones de IA (skills de aulaLobitz)

Las instrucciones reutilizables para DeepSeek están en archivos Markdown dentro de `academico/skills/`:

| Archivo | Operación |
|---|---|
| `resumen_academico.md` | Síntesis fiel y estructurada de las fuentes de estudio. |
| `mapas_conceptuales.md` | Creación de mapas conceptuales con conceptos y frases de enlace. |
| `ensayos.md` | Orientación, consultas y revisión de ensayos según el tipo elegido. |
| `creacion_examenes.md` | Diseño de exámenes de alternativas o preguntas abiertas, según nivel y alcance. |
| `evaluacion_respuestas_abiertas.md` | Calificación formativa de respuestas abiertas con rúbrica y referencia. |
| `recomendaciones_tareas.md` | Plan de trabajo basado en la consigna y los materiales de apoyo. |

Django carga los archivos necesarios para cada operación y los envía a DeepSeek como mensaje de sistema; el material de estudio y la solicitud del alumno se envían aparte como mensaje de usuario. Mantén estos archivos dentro del paquete al copiar o instalar la aplicación.

## Ejecutar en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` antes de iniciar:

- `DJANGO_SECRET_KEY`: clave larga y aleatoria de Django.
- `DEEPSEEK_ENCRYPTION_KEY`: genera una con `py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- Cambia `BOOTSTRAP_ADMIN_PASSWORD` antes de crear la cuenta. El valor `123456` solo documenta la contraseña inicial solicitada y no debe usarse en una instalación expuesta.

Django lee `.env` automáticamente. Conserva tus claves existentes; no es necesario volver a generarlas ni cargarlas manualmente en CMD. Si ya usabas esta instalación, solo necesitas reiniciar el servidor. La migración de esta revisión ya se aplicó aquí.

En CMD, desde la carpeta que contiene `manage.py`:

```cmd
cd /d "D:\OneDrive\Conocimiento\IA AI\Estudio Universidad"
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

Para crear el administrador en una instalación nueva, ejecuta antes `manage.py bootstrap_admin`. La contraseña inicial está en `.env`; el comando conserva una contraseña ya existente salvo que uses expresamente `--reset-password`.

Abre `http://127.0.0.1:8000/`. Inicia sesión con el correo superusuario. Desde **Conexión DeepSeek**, introduce la API Key, URL base y modelo. La clave se cifra con Fernet en la base de datos y las solicitudes salen desde Django, nunca desde el navegador.

## Alcance actual

Incluye login por correo, recuperación de contraseña, alta/edición/eliminación de alumnos, ciclos, cursos y sesiones. Las eliminaciones muestran confirmación; los archivos solo pueden abrirse si pertenecen al alumno autenticado.

Clases y lecturas generan automáticamente resumen y mapa al cargar la transcripción o PDF. El botón de generación permite reintentar o actualizar. También admiten imágenes de mapas del alumno, revisión con visión e historial de cargas y retroalimentación.

Los exámenes mantienen formatos, niveles, bitácora y corrección. La espera de la IA no se suma al tiempo de resolución. Si falla una corrección, las respuestas escritas permanecen en pantalla.

Ensayos mantienen orientación, consultas sobre sus PDF, borrador Word reemplazable y revisión. Las tareas admiten consigna PDF, adjuntos, clases o lecturas de apoyo opcionales y recomendaciones basadas en esos materiales.

Consulta `REVISION_ESPECIFICACION.md` para el contraste con los 35 puntos y los límites de la revisión. Las operaciones de IA siguen siendo síncronas y el indicador muestra actividad, sin porcentaje exacto.

## Configuración de correo e imágenes

Para entregar correos reales configura `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL` y `DEFAULT_FROM_EMAIL` en `.env`. Sin `EMAIL_HOST`, los mensajes se muestran en la terminal y no llegan a una bandeja real. No actives TLS y SSL simultáneamente. El enlace de recuperación dura una hora y solo puede usarse una vez.

La conexión DeepSeek incluye un modelo de imágenes independiente, por defecto `deepseek-flash`. El modelo de texto guardado se conserva. La revisión de mapas envía imagen y fuentes al modelo de visión. Consulta https://api-docs.deepseek.com/guides/vision/ . Las llamadas reales dependen de los modelos disponibles y del saldo de la cuenta.

Los PDF escaneados requieren OCR. Para YouTube se carga su transcripción `.txt`; no se importa directamente un enlace. Si se supera el contexto de la IA, se reparte espacio entre las fuentes y se indica qué texto se recortó.

## Datos y distribución

Los archivos siguen en `media/study/AAAA/MM/` y la base de desarrollo en `db.sqlite3`. Los paquetes excluyen `.env`, base de datos, documentos del alumno, entorno virtual y copias de seguridad. Para respaldar una instalación completa conserva por separado `.env`, `db.sqlite3` y `media/`.

## Comprobar sin red

```cmd
.venv\Scripts\python.exe -S scripts\check_offline.py
```

El ejecutor bloquea conexiones de Python y omite los hooks de `site`; simula DeepSeek y correo. En esta revisión pasaron 37 pruebas. Las pantallas se verificaron a través de formularios, vistas y HTML; no se realizó inspección visual en navegador.

## Alcance de las sesiones de práctica y examen
En cada práctica o examen se seleccionan una o varias sesiones de clase o lectura del mismo curso. Sus materiales son las fuentes para generar preguntas. En la práctica se puede subir un modelo de práctica del profesor y en el examen un examen modelo; estas sesiones no admiten transcripciones propias.
