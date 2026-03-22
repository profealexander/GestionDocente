from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("people.id"), nullable=False, unique=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    whatsapp_phone: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    person: Mapped["Person"] = relationship("Person", lazy="joined")  # noqa: F821
    schedules: Mapped[list["Schedule"]] = relationship("Schedule", back_populates="teacher", cascade="all, delete-orphan")  # noqa: F821
    positions: Mapped[list["TeacherPosition"]] = relationship("TeacherPosition", back_populates="teacher", cascade="all, delete-orphan")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Teacher id={self.id} person_id={self.person_id}>"


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 0=Lunes … 4=Viernes
    period_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)    # 1, 2, 3 …
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)       # "07:00"
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)         # "08:30"
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("grades.id"), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="schedules")  # noqa: F821
    grade: Mapped["Grade"] = relationship("Grade", lazy="joined")      # noqa: F821
    subject: Mapped["Subject"] = relationship("Subject", lazy="joined")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Schedule teacher={self.teacher_id} day={self.day_of_week} period={self.period_num}>"


class TeacherPosition(Base):
    __tablename__ = "teacher_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id"), nullable=False)
    position_type: Mapped[str] = mapped_column(String(20), nullable=False)  # tutor|jefe_area|jefe_subnivel|comision|cargo
    grade_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("grades.id"), nullable=True)
    subnivel: Mapped[str | None] = mapped_column(String(20), nullable=True)  # inicial|basica|media|bachillerato
    area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)   # cargo value or comision name
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="positions")  # noqa: F821
    grade: Mapped["Grade | None"] = relationship("Grade", lazy="joined")  # noqa: F821

    def __repr__(self) -> str:
        return f"<TeacherPosition teacher={self.teacher_id} type={self.position_type!r}>"
