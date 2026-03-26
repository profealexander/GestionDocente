"""Green API WhatsApp sender.

Setup (one-time, done by school admin):
  1. Register at green-api.com
  2. Create an instance and scan QR with the school's WhatsApp number.
  3. Copy idInstance + apiTokenInstance to .env:
       GREEN_API_INSTANCE=1101234567
       GREEN_API_TOKEN=your_token_here

Sending requires only the recipient's phone number — no activation needed on their end.
Phone format: international without '+', e.g. 593962385813 (Ecuador).
"""

import httpx
from loguru import logger

_BASE = "https://api.green-api.com"


def _chat_id(phone: str) -> str:
    """Convert +593XXXXXXXXX or 593XXXXXXXXX to WhatsApp chatId format."""
    return phone.lstrip("+") + "@c.us"


async def send_whatsapp(instance_id: str, token: str, phone: str, message: str) -> bool:
    """Send a WhatsApp message via Green API. Returns True on success."""
    url = f"{_BASE}/waInstance{instance_id}/sendMessage/{token}"
    payload = {"chatId": _chat_id(phone), "message": message}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
        ok = resp.status_code == 200 and resp.json().get("idMessage")
        if ok:
            logger.info(f"[whatsapp] enviado a {phone}")
        else:
            logger.warning(
                f"[whatsapp] fallo phone={phone} status={resp.status_code} body={resp.text[:200]}",
            )
        return bool(ok)
    except Exception as exc:
        logger.error(f"[whatsapp] error phone={phone}: {exc}")
        return False


async def send_whatsapp_pdf(
    instance_id: str,
    token: str,
    phone: str,
    pdf_bytes: bytes,
    file_name: str,
    caption: str = "",
) -> bool:
    """Send a PDF file via Green API SendFileByUpload. Returns True on success."""
    url = f"https://media.green-api.com/waInstance{instance_id}/sendFileByUpload/{token}"
    chat_id_val = _chat_id(phone)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                data={"chatId": chat_id_val, "caption": caption},
                files={"file": (file_name, pdf_bytes, "application/pdf")},
            )
        ok = resp.status_code == 200 and resp.json().get("idMessage")
        if ok:
            logger.info(f"[whatsapp] PDF enviado a {phone}")
        else:
            logger.warning(
                f"[whatsapp] fallo PDF phone={phone} "
                f"status={resp.status_code} body={resp.text[:200]}",
            )
        return bool(ok)
    except Exception as exc:
        logger.error(f"[whatsapp] error PDF phone={phone}: {exc}")
        return False


def format_homework_message(
    guardian_name: str,
    student_name: str,
    grade_name: str,
    subject: str,
    hw_seq: int,
    delivery_date: str,
) -> str:
    return (
        f"Estimado/a {guardian_name},\n"
        f"Le informamos que {student_name} de {grade_name} "
        f"no entregó la tarea #{hw_seq} de {subject}"
        f"{' (vence ' + delivery_date + ')' if delivery_date else ''}.\n"
        f"— SchoolAI"
    )
