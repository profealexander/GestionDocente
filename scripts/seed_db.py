"""Seed inicial: grades y subjects."""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]
# Convertir postgres:// → postgresql+asyncpg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+asyncpg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+asyncpg://" + DATABASE_URL[len("postgresql://"):]

engine = create_async_engine(DATABASE_URL)
Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

GRADES = [
    (1,  "INICIAL 1",    1,  "inicial",      "inicial_1"),
    (2,  "INICIAL 2",    2,  "inicial",      "inicial_2"),
    (3,  "PREPARATORIA", 3,  "egb",          "preparatoria"),
    (4,  "SEGUNDO EGB",  4,  "egb",          "basica_elemental"),
    (5,  "TERCERO EGB",  5,  "egb",          "basica_elemental"),
    (6,  "CUARTO EGB",   6,  "egb",          "basica_elemental"),
    (7,  "QUINTO EGB",   7,  "egb",          "basica_media"),
    (8,  "SEXTO EGB",    8,  "egb",          "basica_media"),
    (9,  "SEPTIMO EGB",  9,  "egb",          "basica_media"),
    (10, "OCTAVO EGB",   10, "egb",          "basica_superior"),
    (11, "NOVENO EGB",   11, "egb",          "basica_superior"),
    (12, "DECIMO EGB",   12, "egb",          "basica_superior"),
    (13, "PRIMERO BT",   13, "bachillerato", None),
    (14, "SEGUNDO BT",   14, "bachillerato", None),
    (15, "TERCERO BT",   15, "bachillerato", None),
]

SUBJECTS = [
    ("Lengua y Literatura",            "Lengua y Literatura",                          "basica"),
    ("Matemática",                     "Matemáticas",                                  "basica"),
    ("Ciencias Sociales",              "Ciencias Sociales",                            "basica"),
    ("Ciencias Naturales",             "Ciencias Naturales",                           "basica"),
    ("Educación Cultural y Artística", "Educación Cultural y Artística",               "basica"),
    ("Educación Física",               "Educación Física",                             "basica"),
    ("Lengua Extranjera",              "Inglés",                                       "basica"),
    ("Matemática",                     "Matemática",                                   "bachillerato"),
    ("Ciencias Naturales",             "Física",                                       "bachillerato"),
    ("Ciencias Naturales",             "Química",                                      "bachillerato"),
    ("Ciencias Naturales",             "Biología",                                     "bachillerato"),
    ("Ciencias Sociales",              "Historia",                                     "bachillerato"),
    ("Ciencias Sociales",              "Educación para la Ciudadanía",                 "bachillerato"),
    ("Ciencias Sociales",              "Filosofía",                                    "bachillerato"),
    ("Lengua y Literatura",            "Lengua y Literatura",                          "bachillerato"),
    ("Lengua Extranjera",              "Inglés",                                       "bachillerato"),
    ("Educación Cultural y Artística", "Educación Cultural y Artística",               "bachillerato"),
    ("Educación Física",               "Educación Física",                             "bachillerato"),
    ("Módulo Interdisciplinar",        "Emprendimiento y Gestión",                     "bachillerato"),
    ("Área Técnica",                   "Herramientas Informáticas Empresariales",      "bachillerato"),
    ("Área Técnica",                   "Gestión Contable y Administración Financiera", "bachillerato"),
    ("Área Técnica",                   "Inglés Técnico Aplicado a los Negocios",       "bachillerato"),
    ("General",                        "Asignación",                                   "general"),
]

async def main():
    async with Session() as session:
        # Grades
        count_grades = (await session.execute(text("SELECT COUNT(*) FROM grades"))).scalar()
        if count_grades == 0:
            for gid, name, sort_order, level, sublevel in GRADES:
                await session.execute(text(
                    "INSERT INTO grades (id, name, sort_order, level, sublevel) "
                    "VALUES (:id, :name, :sort_order, :level, :sublevel)"
                ), {"id": gid, "name": name, "sort_order": sort_order, "level": level, "sublevel": sublevel})
            await session.execute(text("SELECT setval('grades_id_seq', 15)"))
            await session.commit()
            print(f"✓ {len(GRADES)} grades insertados")
        else:
            print(f"  grades ya tiene {count_grades} filas — omitiendo")

        # Subjects
        count_subjects = (await session.execute(text("SELECT COUNT(*) FROM subjects"))).scalar()
        if count_subjects == 0:
            for area, name, sublevel in SUBJECTS:
                await session.execute(text(
                    "INSERT INTO subjects (area, name, sublevel) VALUES (:area, :name, :sublevel)"
                ), {"area": area, "name": name, "sublevel": sublevel})
            await session.commit()
            print(f"✓ {len(SUBJECTS)} subjects insertados")
        else:
            print(f"  subjects ya tiene {count_subjects} filas — omitiendo")

    await engine.dispose()
    print("Seed completado.")

asyncio.run(main())
