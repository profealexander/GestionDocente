-- 1. Primero ejecuta teachers.sql para ver los ids

-- 2. Editar whatsapp de un docente
UPDATE public.teachers
SET whatsapp_phone = '+593962385813'
WHERE id = 1;