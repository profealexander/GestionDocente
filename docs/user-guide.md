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

## Modo Jornada

El Modo Jornada guía al docente hora a hora durante su jornada escolar.
Requiere tener el horario registrado en el sistema.

### Cómo iniciar

Toca el botón **📅 Jornada** o escribe `j` en cualquier momento.

```
[Primer período] 07:00–08:30 — TERCERO BT — Matemáticas
¿Llegaste al aula?  [Aquí ✅]  [Saltar ⏭]  [Pausar ⏸]
```

### Controles durante la jornada

| Botón | Acción |
|---|---|
| **Aquí ✅** | Confirma llegada al aula — activa el contexto (curso + materia) |
| **Saltar ⏭** | Salta al siguiente período sin registrar |
| **Siguiente ▶** | Avanza al siguiente período después de registrar |
| **Pausar ⏸** | Pausa la jornada (receso, imprevisto) |
| **Reanudar ▶** | Continúa desde donde quedó |
| **Terminar 🏁** | Finaliza la jornada del día |

### Contexto automático

Cuando el Modo Jornada está activo, **no necesitas especificar el curso**:

```
Tú:  "Faltó Recalde"
Bot: ✅ Recalde — ausente en TERCERO BT (Matemáticas)
```

El curso y la materia del período activo se inyectan automáticamente.

### Notificación matutina

A las 06:00, el bot envía automáticamente el primer período del día
para que el docente esté preparado.

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

### Estados de entrega

| Estado | Cómo decirlo |
|---|---|
| No entregó | "no entregó", "faltó entregar" |
| Entrega tardía | "entregó tarde", "tardó" |
| Entrega parcial | "incompleto", "parcial" |

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
| Esta semana | "esta semana" |
| La semana pasada | "semana pasada" |
| Este mes | "este mes" |
| El mes pasado | "mes pasado" |
| El trimestre | "el trimestre", "trimestre actual" |

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

| Lo que dices | Cursos incluidos |
|---|---|
| "básica elemental" | 2egb, 3egb, 4egb |
| "básica media" | 5egb, 6egb, 7egb |
| "básica superior" | 8egb, 9egb, 10egb |
| "bachillerato" | 1bt, 2bt, 3bt |
| "EGB" | todos los cursos de EGB (2egb al 10egb) |

---

## Preguntas al asistente IA

Para cualquier pregunta general de pedagogía, planificación o materias:

```
¿Cómo explico las fracciones a niños de 8 años?
```
```
Dame ideas para una actividad de ciencias naturales al aire libre
```

El asistente **no tiene acceso a los datos del colegio**. Para eso usa los
comandos de registro y consulta descritos arriba.

---

## Comandos del bot

| Comando | Descripción |
|---|---|
| `/ayuda` | Muestra la ayuda del bot |
| `/cancelar` | Cancela el flujo actual y limpia el estado |
| `/db` | Panel de base de datos (personas, horarios, cargos) |
| `/jornada` | Inicia o retoma la jornada del día *(solo Modo Jornada)* |

---

## Preguntas frecuentes

**¿Puedo escribir con errores de ortografía?**
Sí. El bot usa IA para interpretar el mensaje y un fallback con reglas básicas
si la IA no está disponible.

**¿Puedo enviar mensajes de voz?**
Sí, siempre que `GROQ_API_KEY` esté configurada.

**¿Qué pasa si olvido poner el curso?**
El bot mostrará un teclado con todos los cursos. Si estás en Modo Jornada, el
curso se toma automáticamente del período activo.

**¿Cómo sé el número de tarea?**
El bot responde con "✅ Tarea #N registrada". También puedes consultar
"tareas de [curso]" para ver la lista numerada.

**¿Qué es el trimestre en los reportes?**
Los números de tarea se reinician cada trimestre. El trimestre se calcula
automáticamente según la fecha.

**El bot no me responde, ¿qué hago?**
Verifica que tu ID de Telegram esté en `TELEGRAM_ALLOWED_USERS`. Usa
[@userinfobot](https://t.me/userinfobot) para obtener tu ID.

**¿Qué pasa si el bot se reinicia a media jornada?**
Si Redis está configurado, la sesión de Jornada se recupera automáticamente.
Sin Redis, necesitas volver a tocar 📅 Jornada.
