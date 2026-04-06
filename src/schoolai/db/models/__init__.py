from schoolai.db.models.attendance import Attendance  # noqa: F401
from schoolai.db.models.teacher_absence import TeacherAbsence  # noqa: F401
from schoolai.db.models.llm_usage import LLMUsage  # noqa: F401
from schoolai.db.models.context_document import ContextDocument  # noqa: F401
from schoolai.db.models.reminder import Reminder  # noqa: F401
from schoolai.db.models.cuota import Actividad, ActividadPago, ActividadParticipante  # noqa: F401
from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.db.models.homework_submission import HomeworkSubmission
from schoolai.db.models.person import Person  # noqa: F401
from schoolai.db.models.student import Student  # noqa: F401
from schoolai.db.models.student_representative import StudentRepresentative  # noqa: F401
from schoolai.db.models.subject import Subject
from schoolai.db.models.teacher import Schedule, Teacher, TeacherPosition  # noqa: F401
from schoolai.db.models.whatsapp_contact import WhatsAppContact  # noqa: F401

__all__ = [
    "Actividad",
    "ContextDocument",
    "Reminder",
    "ActividadParticipante",
    "ActividadPago",
    "Attendance",
    "Grade",
    "Homework",
    "HomeworkSubmission",
    "Person",
    "Schedule",
    "Student",
    "StudentRepresentative",
    "Subject",
    "Teacher",
    "TeacherPosition",
    "LLMUsage",
    "TeacherAbsence",
    "WhatsAppContact",
]
