SELECT t.id,
       p.first_name || ' ' || p.last_name AS nombre,
       t.telegram_id,
       t.is_active,
       t.username,
       t.whatsapp_phone
FROM public.teachers t
JOIN public.people p ON p.id = t.person_id
LIMIT 1000;
