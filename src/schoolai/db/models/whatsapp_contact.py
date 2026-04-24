from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class WhatsAppContact(Base):
    __tablename__ = "whatsapp_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False,
    )
    phone: Mapped[str] = mapped_column(String, nullable=False)
    callmebot_apikey: Mapped[str | None] = mapped_column(String, nullable=True)
    label: Mapped[str | None] = mapped_column(String, nullable=True)  # "celular", "trabajo", etc.
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    person: Mapped["Person"] = relationship("Person", back_populates="whatsapp_contacts")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<WhatsAppContact person_id={self.person_id} "
            f"phone={self.phone} primary={self.is_primary}>"
        )
