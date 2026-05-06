# LLM Benchmark — DeepSeek V4 (2026-04-27)

## Modelos evaluados

| Modelo | Proveedor | Rol | Fecha de prueba |
|---|---|---|---|
| `deepseek-v4-flash` | DeepSeek | planner_fallback | 2026-04-27 |
| `deepseek-v4-flash` [thinking] | DeepSeek | planner_fallback | 2026-04-27 |
| `deepseek-v4-pro` | DeepSeek | planner_fallback | 2026-04-27 |

## Resultados

### Latencia (avg ms)

| # | Modelo | Latencia avg | TTFT avg |
|---|---|---|---|
| 1 | DeepSeek V4 Flash [thinking] | 1970ms | — |
| 2 | DeepSeek V4 Flash | 2097ms | — |
| 3 | DeepSeek V4 Pro | 2354ms | — |

### JSON Tool Calling (100% tests)

| Modelo | Tests | Éxito | Fallo |
|---|---|---|---|
| DeepSeek V4 Flash | 10 | 100% | 0% |
| DeepSeek V4 Flash [thinking] | 10 | 100% | 0% |
| DeepSeek V4 Pro | 10 | 100% | 0% |

### Planner (JSON plan [{tool, params}])

| Modelo | Tests | Éxito | Fallo |
|---|---|---|---|
| DeepSeek V4 Flash | 5 | 100% | 0% |
| DeepSeek V4 Flash [thinking] | 5 | 100% | 0% |
| DeepSeek V4 Pro | 5 | 100% | 0% |

## Ranking Global

| # | Modelo | Latencia | JSON% | Planner% | Score |
|---|---|---|---|---|
| 1 | DeepSeek V4 Flash [thinking] | 1970ms | 100% | 100% | **74.9%** |
| 2 | DeepSeek V4 Flash | 2097ms | 100% | 100% | **73.3%** |
| 3 | DeepSeek V4 Pro | 2354ms | 100% | 100% | **70.0%** |

## Comparación con modelos anteriores (V3.2)

| Métrica | V3.2 Chat | V4 Flash | V4 Flash [thinking] | V4 Pro |
|---|---|---|---|---|
| JSON% | 100% | 100% | 100% | 100% |
| Latencia avg | 4836ms | 2097ms | 1970ms | 2354ms |

> **Nota**: V4 Flash [thinking] es ~59% más rápido que V3.2 Chat y mantiene 100% de calidad.

## Pricing (USD/1M tokens)

| Modelo | Input | Output |
|---|---|---|
| V4 Flash | $0.14 | $0.28 |
| V4 Pro | $0.435 | $0.87 |

## Conclusión

- **Mejor modelo**: `deepseek-v4-flash` [thinking] — latencia más baja (1970ms) con 100% calidad
- **Recomendado para producción**: `deepseek-v4-flash` (non-thinking) — buena relación latencia/calidad
- **V4 Pro**: Más lento, same calidad — no recomendado para este use case

## Configuración usada

```bash
uv run python scripts/benchmark_llm.py --models deepseek --tests simple,att_absent_json,att_late_json,att_query_json,hw_assign_json,no_tool_json,pln_att_absent,pln_att_late,pln_att_query,pln_hw_create,pln_no_action
```

JSON guardado: `scripts/benchmark-schoolai-20260427-152254.json`