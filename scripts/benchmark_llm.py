"""
Benchmark de latencia para proveedores LLM usados en SchoolAI.
Mide tiempo de respuesta de Gemini, GLM y Groq con un prompt simple.

Uso:
    uv run python scripts/benchmark_llm.py
"""

import asyncio
import time
from src.schoolai.skills.llm.client import LLMClient


PROMPT = "Responde solo con 'ok'."
MODELS = [
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.5-flash",
    "zai/glm-4.7-flash",
    "groq/llama-3.3-70b-versatile",
    "groq/llama-3.1-8b-instant",
]
RUNS = 3  # repeticiones por modelo para promediar


async def measure(model: str) -> list[float]:
    client = LLMClient(model=model)
    times = []
    for i in range(RUNS):
        start = time.perf_counter()
        try:
            await client.complete([{"role": "user", "content": PROMPT}])
            elapsed = time.perf_counter() - start
            times.append(elapsed)
            print(f"  run {i+1}: {elapsed:.2f}s")
        except Exception as e:
            print(f"  run {i+1}: ERROR — {e}")
    return times


async def main():
    print(f"\n{'═'*50}")
    print(f"  Benchmark LLM — SchoolAI")
    print(f"  {RUNS} runs por modelo")
    print(f"{'═'*50}\n")

    results = {}
    for model in MODELS:
        print(f"▶ {model}")
        times = await measure(model)
        if times:
            avg = sum(times) / len(times)
            results[model] = avg
            print(f"  promedio: {avg:.2f}s\n")
        else:
            print(f"  sin resultados\n")

    print(f"{'═'*50}")
    print("  RANKING (más rápido primero)")
    print(f"{'═'*50}")
    for model, avg in sorted(results.items(), key=lambda x: x[1]):
        bar = "█" * int(avg * 10)
        print(f"  {avg:.2f}s  {bar}  {model}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
