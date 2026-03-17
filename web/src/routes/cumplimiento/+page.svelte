<script lang="ts">
	import { onMount } from 'svelte';
	import { gradesApi, type Grade, type Student } from '$lib/api/grades';
	import { api } from '$lib/api/client';

	interface Homework {
		id: number;
		sequence_num: number;
		description: string;
		subject_name: string | null;
		delivery_date: string | null;
	}

	// null = sin marcar, true = entregó, false = no entregó
	type CellState = null | true | false;

	// ── Estado ──────────────────────────────────────────────────────
	let grades        = $state<Grade[]>([]);
	let selectedGrade = $state<Grade | null>(null);
	let students      = $state<Student[]>([]);
	let homeworks     = $state<Homework[]>([]);
	let cells         = $state<Record<string, CellState>>({});   // `${studentId}:${hwId}`

	let loadingGrades = $state(true);
	let loadingData   = $state(false);
	let saving        = $state(false);
	let savedOk       = $state(false);
	let error         = $state('');

	onMount(async () => {
		try {
			grades = await gradesApi.list();
		} catch (e: any) { error = e.message; }
		finally { loadingGrades = false; }
	});

	async function selectGrade(grade: Grade) {
		selectedGrade = grade;
		students = [];
		homeworks = [];
		cells = {};
		loadingData = true;
		error = '';
		try {
			[students, homeworks] = await Promise.all([
				gradesApi.students(grade.id),
				api.get<Homework[]>(`/homework?grade_id=${grade.id}&is_open=true`),
			]);
			for (const s of students)
				for (const h of homeworks)
					cells[`${s.id}:${h.id}`] = null;
		} catch (e: any) { error = e.message; }
		finally { loadingData = false; }
	}

	function toggle(studentId: number, hwId: number) {
		const key = `${studentId}:${hwId}`;
		const cur = cells[key];
		cells[key] = cur === null ? true : cur === true ? false : null;
	}

	async function save() {
		if (!selectedGrade) return;
		saving = true;
		error = '';
		savedOk = false;
		try {
			const requests = homeworks.map(hw => {
				const nonCompleters = students
					.filter(s => cells[`${s.id}:${hw.id}`] === false)
					.map(s => s.id);
				if (nonCompleters.length === 0) return Promise.resolve();
				return api.post(`/homework/${hw.id}/report`, {
					student_ids: nonCompleters,
					status: 'missing',
				});
			});
			await Promise.all(requests);
			savedOk = true;
			setTimeout(() => savedOk = false, 3000);
		} catch (e: any) { error = e.message; }
		finally { saving = false; }
	}

	function hwCounts(hwId: number) {
		const delivered    = students.filter(s => cells[`${s.id}:${hwId}`] === true).length;
		const notDelivered = students.filter(s => cells[`${s.id}:${hwId}`] === false).length;
		return { delivered, notDelivered };
	}

	function studentCounts(studentId: number) {
		const delivered    = homeworks.filter(h => cells[`${studentId}:${h.id}`] === true).length;
		const notDelivered = homeworks.filter(h => cells[`${studentId}:${h.id}`] === false).length;
		return { delivered, notDelivered };
	}

	const hasData = $derived(students.length > 0 && homeworks.length > 0);
</script>

<div class="page">
	<!-- Header -->
	<div class="page-header">
		<div>
			<h1>Cumplimiento</h1>
			<p class="subtitle">Marca quién entregó cada tarea</p>
		</div>
		{#if hasData}
			<button class="btn-save" onclick={save} disabled={saving}>
				{saving ? 'Guardando...' : '✓ Guardar reporte'}
			</button>
		{/if}
	</div>

	{#if error}<div class="error-banner">{error}</div>{/if}
	{#if savedOk}<div class="success-banner">✅ Reporte guardado correctamente</div>{/if}

	<!-- Leyenda -->
	{#if hasData}
		<div class="legend">
			<span class="leg-item"><span class="cell-demo delivered">✓</span> Entregó</span>
			<span class="leg-item"><span class="cell-demo missing">✗</span> No entregó</span>
			<span class="leg-item"><span class="cell-demo unmarked">–</span> Sin marcar</span>
			<span class="leg-hint">Toca cada celda para cambiar el estado</span>
		</div>
	{/if}

	<!-- Selector de curso -->
	<div class="section">
		<p class="section-label">Curso</p>
		{#if loadingGrades}
			<div class="skeleton-row">
				{#each [1,2,3,4] as _}<div class="skeleton-chip"></div>{/each}
			</div>
		{:else}
			<div class="grade-chips">
				{#each grades as grade}
					<button
						class="grade-chip"
						class:selected={selectedGrade?.id === grade.id}
						onclick={() => selectGrade(grade)}
					>{grade.name}</button>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Tabla cruzada -->
	{#if selectedGrade}
		{#if loadingData}
			<div class="loading-table">Cargando datos...</div>
		{:else if students.length === 0}
			<p class="empty">Sin estudiantes en este curso.</p>
		{:else if homeworks.length === 0}
			<p class="empty">Sin tareas abiertas para este curso.</p>
		{:else}
			<div class="table-wrap">
				<table class="matrix">
					<thead>
						<tr>
							<th class="col-name">Estudiante</th>
							{#each homeworks as hw}
								{@const c = hwCounts(hw.id)}
								<th class="col-hw" title={hw.description}>
									<div class="hw-header">
										<span class="hw-seq">#{hw.sequence_num}</span>
										<span class="hw-subj">{hw.subject_name ?? '—'}</span>
										{#if hw.delivery_date}
											<span class="hw-date">
												{new Date(hw.delivery_date + 'T00:00:00').toLocaleDateString('es-EC', { day:'numeric', month:'short' })}
											</span>
										{/if}
										<div class="hw-mini-counts">
											{#if c.delivered > 0}<span class="mini delivered">✓{c.delivered}</span>{/if}
											{#if c.notDelivered > 0}<span class="mini missing">✗{c.notDelivered}</span>{/if}
										</div>
									</div>
								</th>
							{/each}
							<th class="col-summary">Total</th>
						</tr>
					</thead>
					<tbody>
						{#each students as student, i}
							{@const sc = studentCounts(student.id)}
							<tr class:row-alt={i % 2 === 1}>
								<td class="cell-name">{student.full_name}</td>
								{#each homeworks as hw}
									{@const state = cells[`${student.id}:${hw.id}`]}
									<td class="cell-toggle">
										<button
											class="toggle-btn"
											class:delivered={state === true}
											class:missing={state === false}
											class:unmarked={state === null}
											onclick={() => toggle(student.id, hw.id)}
										>
											{state === true ? '✓' : state === false ? '✗' : '–'}
										</button>
									</td>
								{/each}
								<td class="cell-summary">
									{#if sc.delivered > 0}<span class="sum-badge delivered">{sc.delivered}✓</span>{/if}
									{#if sc.notDelivered > 0}<span class="sum-badge missing">{sc.notDelivered}✗</span>{/if}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{/if}
</div>

<style>
	.page { max-width: 100%; }

	.page-header {
		display: flex; justify-content: space-between;
		align-items: flex-start; margin-bottom: 20px;
	}

	h1 { font-size: 22px; font-weight: 600; color: var(--color-foreground); margin: 0 0 4px; }
	.subtitle { font-size: 13px; color: var(--color-muted); margin: 0; }

	.legend {
		display: flex; align-items: center; gap: 16px;
		margin-bottom: 20px; font-size: 12px; color: var(--color-muted);
	}
	.leg-item { display: flex; align-items: center; gap: 6px; }
	.leg-hint { margin-left: auto; font-size: 11px; color: var(--color-muted-2); }

	.cell-demo {
		display: inline-flex; align-items: center; justify-content: center;
		width: 24px; height: 24px; border-radius: 6px;
		font-size: 12px; font-weight: 600;
	}
	.cell-demo.delivered { background: var(--color-success-muted); color: var(--color-success); }
	.cell-demo.missing   { background: var(--color-danger-muted);  color: var(--color-danger);  }
	.cell-demo.unmarked  { background: var(--color-surface-2);     color: var(--color-muted-2); }

	.section { margin-bottom: 24px; }
	.section-label {
		font-size: 11px; font-weight: 500; text-transform: uppercase;
		letter-spacing: 0.8px; color: var(--color-muted-2); margin: 0 0 10px;
	}

	.grade-chips { display: flex; flex-wrap: wrap; gap: 8px; }
	.grade-chip {
		padding: 6px 14px; border-radius: 20px;
		border: 1px solid var(--color-border); background: var(--color-surface);
		color: var(--color-muted); font-size: 13px; cursor: pointer; transition: all 0.15s;
	}
	.grade-chip:hover { background: var(--color-surface-2); color: var(--color-foreground); }
	.grade-chip.selected {
		background: var(--color-primary-muted); border-color: var(--color-primary);
		color: var(--color-primary); font-weight: 500;
	}

	.table-wrap { overflow-x: auto; border-radius: 12px; border: 1px solid var(--color-border); }

	.matrix { width: 100%; border-collapse: collapse; font-size: 13px; }

	thead th {
		background: var(--color-surface); border-bottom: 1px solid var(--color-border);
		padding: 10px 8px; text-align: center;
		position: sticky; top: 0; z-index: 1;
	}

	.col-name {
		text-align: left !important; min-width: 180px;
		position: sticky; left: 0; background: var(--color-surface);
		z-index: 2 !important; border-right: 1px solid var(--color-border);
	}
	.col-hw { min-width: 90px; }
	.col-summary { min-width: 80px; }

	.hw-header { display: flex; flex-direction: column; align-items: center; gap: 2px; }
	.hw-seq { font-size: 12px; font-weight: 600; color: var(--color-primary); }
	.hw-subj {
		font-size: 11px; color: var(--color-foreground); font-weight: 500;
		max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.hw-date { font-size: 10px; color: var(--color-muted-2); }
	.hw-mini-counts { display: flex; gap: 4px; margin-top: 4px; }
	.mini { font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 8px; }
	.mini.delivered { background: var(--color-success-muted); color: var(--color-success); }
	.mini.missing   { background: var(--color-danger-muted);  color: var(--color-danger);  }

	tbody tr { border-bottom: 1px solid var(--color-border-muted); transition: background 0.1s; }
	tbody tr:hover { background: var(--color-surface-2) !important; }
	tbody tr.row-alt { background: var(--color-surface); }

	.cell-name {
		padding: 10px 14px; color: var(--color-foreground);
		position: sticky; left: 0; background: inherit;
		border-right: 1px solid var(--color-border-muted); white-space: nowrap;
	}

	.cell-toggle { padding: 6px; text-align: center; }

	.toggle-btn {
		width: 34px; height: 34px; border-radius: 8px;
		border: 1px solid var(--color-border);
		font-size: 14px; font-weight: 700; cursor: pointer; transition: all 0.12s;
	}
	.toggle-btn.unmarked  { background: transparent; color: var(--color-muted-2); }
	.toggle-btn.unmarked:hover { background: var(--color-surface-3); color: var(--color-muted); }
	.toggle-btn.delivered { background: var(--color-success-muted); border-color: var(--color-success); color: var(--color-success); }
	.toggle-btn.missing   { background: var(--color-danger-muted);  border-color: var(--color-danger);  color: var(--color-danger);  }

	.cell-summary { padding: 6px 10px; text-align: center; white-space: nowrap; }
	.sum-badge {
		display: inline-block; font-size: 11px; font-weight: 600;
		padding: 2px 6px; border-radius: 8px; margin: 1px;
	}
	.sum-badge.delivered { background: var(--color-success-muted); color: var(--color-success); }
	.sum-badge.missing   { background: var(--color-danger-muted);  color: var(--color-danger);  }

	.btn-save {
		padding: 8px 20px; border-radius: 8px; border: none;
		background: var(--color-primary); color: white;
		font-size: 13px; font-weight: 500; cursor: pointer; transition: background 0.15s;
	}
	.btn-save:hover:not(:disabled) { background: var(--color-primary-hover); }
	.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

	.error-banner {
		padding: 10px 14px; border-radius: 8px;
		background: var(--color-danger-muted); color: var(--color-danger);
		font-size: 13px; margin-bottom: 16px;
	}
	.success-banner {
		padding: 10px 14px; border-radius: 8px;
		background: var(--color-success-muted); color: var(--color-success);
		font-size: 13px; margin-bottom: 16px;
	}

	.skeleton-row { display: flex; gap: 8px; }
	.skeleton-chip {
		width: 90px; height: 32px; border-radius: 20px;
		background: var(--color-surface-2); animation: pulse 1.5s infinite;
	}
	.loading-table { padding: 40px; text-align: center; color: var(--color-muted); font-size: 13px; }
	.empty { color: var(--color-muted); font-size: 13px; }

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.4; }
	}
</style>
