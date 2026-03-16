# Guía de usuario — SchoolAI Bot

Guía de referencia para el docente. Explica qué puedes escribirle al bot,
con ejemplos reales de mensajes.

---

## Cómo funciona

Escríbele al bot como si le hablaras a un asistente. No necesitas memorizar
comandos exactos — el bot entiende lenguaje natural, incluyendo abreviaciones
y errores de tipeo.

También puedes enviar **mensajes de voz** y el bot los transcribirá automáticamente.

Si el bot necesita información que faltó en el mensaje (por ejemplo, el curso),
te mostrará un teclado de opciones para seleccionarlo.

---

## Cursos disponibles

| Abreviación | Curso completo |
|---|---|
| `i1` | Inicial 1 |
| `i2` | Inicial 2 |
| `prep` | Preparatoria |
| `2egb` – `10egb` | Segundo EGB – Décimo EGB |
| `1bt` | Primero Bachillerato |
| `2bt` | Segundo Bachillerato |
| `3bt` | Tercero Bachillerato |

Puedes usar el nombre completo, abreviado o con errores de tipeo.
El bot entiende: "optabo" → Octavo EGB, "pimero bt" → Primero BT.

---

## Registrar asistencia

### Ausencias simples

```
Faltó Juan Pérez de décimo
```
```
Faltaron María García y Pedro López de 2bt
```

### Con fecha específica

```
Ayer faltó Ana Torres de noveno
```
```
El 10/03 faltaron tres estudiantes de 8egb: Carlos, Luis, Sofía
```

### Llegada tarde

```
Llegó tarde Roberto Silva de 1bt
```
```
AT: Fernanda Mora y Diego Cruz de tercero BT
```

### Falta justificada

```
Justificada la ausencia de Valentina Ríos de 7egb
```

### Notas sobre estados

| Estado | Cómo decirlo | Código en DB |
|---|---|---|
| Ausente | "faltó", "no vino", "ausente" | `F` |
| Tarde | "llegó tarde", "tardanza", "AT" | `AT` |
| Justificado | "justificada", "con permiso" | `J` |

---

## Registrar tareas

### Tarea básica

```
Tarea de inglés para tercero BT: traducir el texto de la página 45
```
```
2bt tarea de física resolver ejercicios del capítulo 3
```

### Con fecha de entrega

```
Tarea de matemáticas para décimo EGB: ejercicios 1 al 10 para el viernes
```
```
Primer BT, tarea de química para el 20/03: reporte de laboratorio
```

### Sin materia especificada

```
Tercero BT investigar los tipos de energía renovable para mañana
```

El bot asignará el número de tarea automáticamente (#1, #2, #3...) dentro del
trimestre actual.

---

## Registrar quién no entregó una tarea

### Por número de tarea

```
No entregaron la tarea #3 de 2bt: Carlos Mendoza y Ana Suárez
```
```
Tarea 2 de décimo EGB, entrega parcial: Luis Herrera
```

### Por materia (toma la tarea más reciente de esa materia)

```
No entregó la tarea de inglés de 1bt: Pedro Gómez
```

### Todas las tareas abiertas del curso

```
Décimo EGB, no entregó ninguna tarea: Sofía Castro
```

### Estados de entrega

| Estado | Cómo decirlo |
|---|---|
| No entregó | "no entregó", "faltó entregar", "missing" |
| Entrega tardía | "entregó tarde", "tardó", "late" |
| Entrega parcial | "incompleto", "parcial", "partial" |

---

## Consultar reportes

### Tareas de un curso

```
Dame las tareas de 3bt
```
```
Tareas abiertas de primero bachillerato
```
```
¿Qué tareas tiene décimo EGB esta semana?
```

### Tareas de varios cursos a la vez

```
Dame las tareas de octavo y noveno
```
```
Tareas de todo el bachillerato
```
```
Tareas de básica superior (equivale a 8egb, 9egb, 10egb)
```

### Por período

| Período | Cómo decirlo |
|---|---|
| Hoy | "hoy", "de hoy" |
| Ayer | "ayer" |
| Esta semana | "esta semana", "la semana" |
| La semana pasada | "semana pasada" |
| Este mes | "este mes" |
| El mes pasado | "mes pasado" |
| El trimestre | "el trimestre", "trimestre actual" |

Ejemplos:
```
Tareas de 1bt de esta semana
```
```
Dame el reporte de tareas de bachillerato del mes
```

### Asistencia

```
¿Quién faltó hoy en 2bt?
```
```
Reporte de asistencia de décimo EGB esta semana
```
```
Ausencias de noveno en lo que va del mes
```

---

## Rangos de cursos por nivel

Puedes mencionar el nivel completo y el bot lo expande automáticamente:

| Lo que dices | Cursos incluidos |
|---|---|
| "básica elemental" | 2egb, 3egb, 4egb |
| "básica media" | 5egb, 6egb, 7egb |
| "básica superior" | 8egb, 9egb, 10egb |
| "bachillerato" | 1bt, 2bt, 3bt |
| "EGB" | todos los cursos de EGB (2egb al 10egb) |

---

## Preguntas al asistente IA

Para cualquier pregunta general de pedagogía, planificación o materias,
escríbela directamente:

```
¿Cómo explico las fracciones a niños de 8 años?
```
```
Dame ideas para una actividad de ciencias naturales al aire libre
```
```
¿Cuál es la diferencia entre evaluación formativa y sumativa?
```

El asistente **no tiene acceso a los datos del colegio** (estudiantes, tareas,
asistencia). Para eso usa los comandos de registro y consulta descritos arriba.

---

## Comandos del bot

| Comando | Descripción |
|---|---|
| `/ayuda` | Muestra la ayuda del bot |
| `/cancelar` | Cancela el flujo actual y limpia el estado |
| `/db` | Panel de base de datos (consultas directas) |

---

## Preguntas frecuentes

**¿Puedo escribir con errores de ortografía?**
Sí. El bot usa IA para interpretar el mensaje. Entiende "optabo", "nobeno",
"pimero bt", "sacar resumen", etc.

**¿Puedo enviar mensajes de voz?**
Sí, siempre que `GROQ_API_KEY` esté configurada. El bot transcribe el audio
y lo procesa igual que texto.

**¿Qué pasa si olvido poner el curso?**
El bot te mostrará un teclado con todos los cursos para que selecciones.
Después procesa el mensaje completo.

**¿Cómo sé el número de tarea?**
El bot responde con "✅ Tarea #N registrada" al guardar. También puedes
consultar "tareas de [curso]" para ver la lista con numeración.

**¿Qué es el trimestre en los reportes?**
Los números de tarea se reinician cada trimestre. El trimestre se calcula
automáticamente según la fecha de registro.

**El bot no me responde, ¿qué hago?**
Verifica que tu ID de Telegram esté en `TELEGRAM_ALLOWED_USERS`. Usa
[@userinfobot](https://t.me/userinfobot) para obtener tu ID.
