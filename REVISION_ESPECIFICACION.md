# Revisión de Aula Flujo

Fecha: 20 de octubre de 2026. Fuente: «Texto pegado(2).txt», especificación de 35 puntos adjunta por el usuario.

## Resultado

Se corrigieron omisiones funcionales, acceso a archivos, validaciones y manejo de fallos. La migración 0006 se aplicó en la instalación local. Se conservaron las cantidades de usuarios, ciclos, cursos, sesiones, archivos, resultados y exámenes existentes. Todos los archivos originales siguen presentes.

## Contraste de requisitos

«Implementado» describe código y pruebas locales. Las llamadas reales a DeepSeek y la entrega SMTP requieren configuración y comprobación con la cuenta del usuario.

| Puntos | Requisito | Estado después de la revisión |
|---|---|---|
| 1 | Login por correo y recuperar contraseña | Implementado. Enlace temporal de un solo uso; SMTP pendiente de configuración para correo real. |
| 2 | Cuenta administradora única | Acciones administrativas limitadas a civangonzales@gmail.com. El comando inicial conserva una contraseña ya existente. |
| 3 | Alta, modificación, lista y eliminación de usuarios | Implementado. Correos duplicados rechazados y cuenta administradora protegida. |
| 4–5 | Crear, modificar y eliminar ciclos | Implementado, con validación de duplicados y confirmación antes de eliminar. |
| 6 | Cursos con código de hasta cuatro caracteres y edición | Implementado; también se añadió eliminación con confirmación. |
| 7–8 | Tipos de sesión; número, título, fecha y edición | Implementado. Número obligatorio para clase, práctica y examen. |
| 9 | Skill de mapas desde clase, PDF o YouTube | Markdown independiente y conectado. PDF y transcripciones funcionan; YouTube requiere cargar su transcripción. No hay importación directa del enlace. |
| 10 | Transcripción, fecha, resumen y mapa automáticos, apertura y borrado | Implementado. Un fallo de IA conserva el archivo y permite reintentar. |
| 11 y 17 | Carga y revisión de mapas del alumno, con historial | Implementado para imágenes. Registros de cargas y revisiones conservados al eliminar una imagen. Integración de visión probada con respuesta simulada. |
| 12 | Diapositivas múltiples, fecha, apertura y eliminación | Implementado. Se añaden varios archivos mediante cargas sucesivas. |
| 13 | Modelos opcionales del profesor | Implementado. Se usan como referencia de estilo. |
| 14–15 | Exámenes de clase, ambos tipos y niveles, corrección y bitácora | Implementado. Corregidos tiempo medido y validación de alternativas, rúbricas, puntajes e identificadores de corrección. |
| 16 | Lecturas PDF con resumen y mapa automáticos | Implementado para PDF con texto seleccionable. El selector distingue lectura PDF e imagen de mapa. |
| 18–19 | Exámenes de lectura y bitácora | Implementado mediante el flujo común de evaluación. |
| 20–21 | Práctica con número, fecha, alcance y modelos propios | Implementado. Alcance obligatorio de clases o lecturas del mismo curso. |
| 22–23 | Exámenes de práctica y bitácora | Implementado; conserva tipos, dificultad, respuestas y resultados. |
| 24–25 | Examen con número, fecha, alcance y modelos propios | Implementado. |
| 26–27 | Exámenes sobre el alcance y bitácora | Implementado. |
| 28 | Skill y profesor de ensayo | Markdown independiente; tipos académicos, orientación y tipo personalizado. |
| 29 | Tipo, PDF, camino y consultas del ensayo | Implementado. Las consultas usan los PDF de esa sesión. |
| 30–31 | Reemplazar Word y revisar ensayo según tipo | Implementado. Resultados anteriores conservados y aviso cuando cambian los datos relevantes. |
| 32–33 | Tarea con descripción, consigna PDF, adjuntos y sesiones de apoyo opcionales | Implementado. Fuentes de apoyo limitadas al mismo curso. |
| 34 | Recomendaciones para la tarea | Implementado y conectado a un nuevo Markdown. Usa consigna, adjuntos y sesiones asociadas. |
| 35 | Navegación entre ciclos, cursos y sesiones | Implementado, con enlaces de regreso y acciones de edición y eliminación. |

## Problemas adicionales corregidos

- El servidor de desarrollo exponía documentos por URL de medios. Ahora comprueba el propietario en las rutas nuevas y antiguas.
- Las búsquedas de cursos o sesiones ajenos podían terminar en error de servidor. Ahora responden con 404.
- La espera de la corrección de IA se contaba como duración del examen. Ahora se mide desde la primera apertura hasta la entrega.
- Un fallo de corrección dejaba el formulario vacío. Ahora conserva el texto enviado y sigue ocultando la clave de respuestas.
- Se aceptaban porcentajes fuera de rango e identificadores repetidos de corrección. Ahora se rechazan antes de guardar.
- El recorte del contexto podía omitir por completo las últimas fuentes. Ahora se reparte espacio entre documentos y se señala el recorte.
- El resumen y el mapa se guardan juntos en una transacción.
- Modificar un ensayo o reemplazar su borrador eliminaba resultados anteriores. Ahora se conservan y se avisa cuando pueden estar desactualizados.
- Se añadieron límites de formato y tamaño, limpieza de archivos al eliminar contenedores y protección frente al envío repetido de formularios de IA.
- `.env` se lee al iniciar, conservando las claves existentes.

## Verificación

37 pruebas automatizadas correctas: exámenes, corrección abierta, alcances, ensayos, recuperación de contraseña con enlace de un solo uso, permisos entre alumnos, edición, eliminación, carga automática, mapas e historial, y tareas.

La ejecución final bloqueó las conexiones de red de Python y utilizó una base de datos de prueba. DeepSeek y el envío de correo se simularon. Se verificó también la sintaxis de JavaScript. No se realizó inspección visual en navegador.

## Configuración y límites

1. Configurar SMTP y comprobar la llegada de un correo real. Sin SMTP, el correo local aparece en la terminal.
2. Comprobar con la cuenta del usuario una revisión real de imagen. La documentación oficial consultada indica `deepseek-flash` como modelo con visión: https://api-docs.deepseek.com/guides/vision/
3. Los PDF escaneados necesitan OCR y YouTube necesita una transcripción cargada. No se incorporó OCR ni descarga directa de videos o subtítulos.
4. La calidad de las preguntas, mapas y retroalimentación reales debe comprobarse con material académico. Las pruebas validan flujo y formato, no la calidad de las respuestas del proveedor.
5. Las llamadas de IA siguen siendo síncronas. Se muestra actividad, sin inventar un porcentaje de avance.

Los paquetes entregados contienen código, instrucciones y documentación. Excluyen claves, base de datos, materiales de alumnos, entorno virtual y copias de seguridad.
