<script lang="ts">
	import { onMount } from 'svelte';
	import { gradesApi, type Grade } from '$lib/api/grades';
	import { subjectsApi, scoresApi, type Subject, type ScoreMatrix, type ScoreUpsertRow } from '$lib/api/scores';

	// ── Selección ────────────────────────────────────────────────────
	let grades        = $state<Grade[]>([]);
	let subjects      = $state<Subject[]>([]);
	let selectedGrade = $state<Grade | null>(null);
	let selectedSubj  = $state<Subject | null>(null);
	let trimester     = $state(1);

	// ── Tabla ────────────────────────────────────────────────────────
	let matrix     = $state<ScoreMatrix | null>(null);
	// copia local editable: student_id → column_label → valor string
	let localScores = $state<Record<number, Record<string, string>>>({});
	let dirty       = $state(false);

	// ── Nueva columna ────────────────────────────────────────────────
	let newColLabel = $state('');
	let addingCol   = $state(false);

	// ── UI ───────────────────────────────────────────────────────────
	let loading  = $state(false);
	let saving   = $state(false);
	let savedOk  = $state(false);
	let error    = $state('');

	onMount(async () => {
		try {
			[grades, subjects] = await Promise.all([gradesApi.list(), subjectsApi.list()]);
		} catch (e: any) {
			error = e.message;
		}
	});

	// ── Cargar matriz cuando cambia la selección ─────────────────────
	async function loadMatrix() {
		if (!selectedGrade || !selectedSubj) return;
		loading = true;
		error = '';
		dirty = false;
		try {
			matrix = await scoresApi.matrix(selectedGrade.id, selectedSubj.id, trimester);
			// Inicializar copia local
			const initial: Record<number, Record<string, string>> = {};
			for (const s of matrix.students) {
				initial[s.id] = {};
				for (const col of matrix.columns) {
					const v = s.scores[col];
					initial[s.id][col] = v != null ? String(v) : '';
				}
			}
			localScores = initial;
		} catch (e: any) {
			error = e.message;
			matrix = null;
		} finally {
			loading = false;
		}
	}

	function selectGrade(g: Grade) {
		selectedGrade = g;
		selectedSubj = null;
		matrix = null;
		dirty = false;
	}

	function selectSubject(s: Subject) {
		selectedSubj = s;
		loadMatrix();
	}

	function changeTrimester(t: number) {
		trimester = t;
		if (selectedGrade && selectedSubj) loadMatrix();
	}

	function onCellInput(studentId: number, col: string, raw: string) {
		localScores[studentId] = { ...localScores[studentId], [col]: raw };
		dirty = true;
	}

	// ── Guardar ──────────────────────────────────────────────────────
	async function save() {
		if (!matrix || !selectedGrade || !selectedSubj) return;
		saving = true;
		error = '';
		savedOk = false;

		const rows: ScoreUpsertRow[] = [];
		for (const student of matrix.students) {
			for (const col of matrix.columns) {
				const raw = localScores[student.id]?.[col] ?? '';
				if (raw === '') continue;
				const val = parseFloat(raw);
				if (isNaN(val) || val < 0 || val > 10) continue;
				rows.push({
					student_id: student.id,
					subject_id: selectedSubj.id,
					grade_id: selectedGrade.id,
					trimester_num: trimester,
					column_label: col,
					score: Math.round(val * 100) / 100,
				});
			}
		}

		try {
			await scoresApi.bulkUpsert(rows);
			dirty = false;
			savedOk = true;
			setTimeout(() => savedOk = false, 3000);
		} catch (e: any) {
			error = e.message;
		} finally {
			saving = false;
		}
	}

	// ── Agregar columna ──────────────────────────────────────────────
	async function addColumn() {
		const label = newColLabel.trim();
		if (!label || !matrix) return;
		if (matrix.columns.includes(label)) {
			error = `La columna "${label}" ya existe.`;
			return;
		}
		addingCol = true;
		error = '';

		// Insertar con score=0 para el primer estudiante para que la columna aparezca
		// (sólo si hay estudiantes)
		if (matrix.students.length > 0) {
			const first = matrix.students[0];
			try {
				await scoresApi.bulkUpsert([{
					student_id: first.id,
					subject_id: selectedSubj!.id,
					grade_id: selectedGrade!.id,
					trimester_num: trimester,
					column_label: label,
					score: 0,
				}]);
			} catch (e: any) {
				error = e.message;
				addingCol = false;
				return;
			}
		}

		newColLabel = '';
		addingCol = false;
		await loadMatrix();
	}

	// ── Eliminar columna ─────────────────────────────────────────────
	async function deleteColumn(col: string) {
		if (!matrix || !selectedGrade || !selectedSubj) return;
		if (!confirm(`¿Eliminar la columna "${col}" y todas sus notas?`)) return;
		error = '';
		try {
			await scoresApi.deleteColumn(selectedGrade.id, selectedSubj.id, trimester, col);
			await loadMatrix();
		} catch (e: any) {
			error = e.message;
		}
	}

	// ── Promedio por estudiante ──────────────────────────────────────
	function average(studentId: number): string {
		if (!matrix) return '—';
		const vals = matrix.columns
			.map(c => localScores[studentId]?.[c])
			.filter(v => v !== '' && v != null)
			.map(v => parseFloat(v!))
			.filter(v => !isNaN(v));
		if (vals.length === 0) return '—';
		return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
	}

	const TRIMESTERS = [1, 2, 3];
</script>

<div class="page">
	<!-- Header -->
	<div class="page-header">
		<div>
			<h1>Notas</h1>
			{#if selectedGrade && selectedSubj}
				<p class="subtitle">{selectedGrade.name} · {selectedSubj.name} · T{trimester}</p>
			{/if}
		</div>
		{#if matrix && dirty}
			<button class="btn-save" onclick={save} disabled={saving}>
				{saving ? 'Guardando...' : '✓ Guardar'}
			</button>
		{/if}
	</div>

	{#if error}
		<div class="error-banner">{error}</div>
	{/if}
	{#if savedOk}
		<div class="success-banner">✅ Notas guardadas</div>
	{/if}

	<!-- Curso -->
	<div class="section">
		<p class="section-label">Curso</p>
		<div class="chips">
			{#each grades as g}
				<button
					class="chip"
					class:selected={selectedGrade?.id === g.id}
					onclick={() => selectGrade(g)}
				>{g.name}</button>
			{/each}
		</div>
	</div>

	<!-- Materia -->
	{#if selectedGrade}
		<div class="section">
			<p class="section-label">Materia</p>
			<div class="chips chips--wrap">
				{#each subjects as s}
					<button
						class="chip"
						class:selected={selectedSubj?.id === s.id}
						onclick={() => selectSubject(s)}
					>{s.name}</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Trimestre -->
	{#if selectedGrade && selectedSubj}
		<div class="section">
			<p class="section-label">Trimestre</p>
			<div class="chips">
				{#each TRIMESTERS as t}
					<button
						class="chip"
						class:selected={trimester === t}
						onclick={() => changeTrimester(t)}
					>T{t}</button>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tabla -->
	{#if selectedGrade && selectedSubj}
		{#if loading}
			<div class="skeleton-table">
				{#each [1,2,3,4,5] as _}
					<div class="skeleton-row"></div>
				{/each}
			</div>
		{:else if matrix}
			<div class="table-wrapper">
				<table class="gradebook">
					<thead>
						<tr>
							<th class="th-name">Estudiante</th>
							{#each matrix.columns as col}
								<th class="th-score">
									<div class="col-header">
										<span>{col}</span>
										<button
											class="btn-del-col"
											onclick={() => deleteColumn(col)}
											title="Eliminar columna"
										>✕</button>
									</div>
								</th>
							{/each}
							<th class="th-avg">Prom.</th>
							<th class="th-add">
								<div class="add-col">
									<input
										class="input-col"
										bind:value={newColLabel}
										placeholder="Nueva…"
										onkeydown={(e) => e.key === 'Enter' && addColumn()}
										maxlength={50}
									/>
									<button
										class="btn-add-col"
										onclick={addColumn}
										disabled={addingCol || !newColLabel.trim()}
									>+</button>
								</div>
							</th>
						</tr>
					</thead>
					<tbody>
						{#each matrix.students as student, i}
							<tr class:row-odd={i % 2 === 0}>
								<td class="td-name">
									<span class="row-num">{i + 1}</span>
									{student.name}
								</td>
								{#each matrix.columns as col}
									<td class="td-score">
										<input
											class="score-input"
											type="number"
											min="0"
											max="10"
											step="0.01"
											value={localScores[student.id]?.[col] ?? ''}
											oninput={(e) => onCellInput(student.id, col, (e.target as HTMLInputElement).value)}
										/>
									</td>
								{/each}
								<td class="td-avg">{average(student.id)}</td>
								<td></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			{#if matrix.students.length === 0}
				<p class="empty">No hay estudiantes en este curso.</p>
			{:else if matrix.columns.length === 0}
				<p class="hint">Agrega una columna usando el campo "Nueva…" en el encabezado.</p>
			{/if}
		{/if}
	{/if}
</div>

<style>
	.page { max-width: 1100px; margin: 0 auto; }

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 24px;
	}

	h1 {
		font-size: 22px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 4px;
	}

	.subtitle {
		font-size: 13px;
		color: var(--color-muted);
		margin: 0;
	}

	.section { margin-bottom: 24px; }

	.section-label {
		font-size: 11px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.8px;
		color: var(--color-muted-2);
		margin: 0 0 8px;
	}

	/* Chips */
	.chips { display: flex; flex-wrap: wrap; gap: 8px; }
	.chips--wrap { max-height: 140px; overflow-y: auto; }

	.chip {
		padding: 6px 14px;
		border-radius: 20px;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-muted);
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
	}
	.chip:hover { background: var(--color-surface-2); color: var(--color-foreground); }
	.chip.selected {
		background: var(--color-primary-muted);
		border-color: var(--color-primary);
		color: var(--color-primary);
		font-weight: 500;
	}

	/* Table */
	.table-wrapper {
		overflow-x: auto;
		border-radius: 10px;
		border: 1px solid var(--color-border);
	}

	.gradebook {
		width: 100%;
		border-collapse: collapse;
		font-size: 13px;
	}

	.gradebook thead tr {
		background: var(--color-surface-2);
		border-bottom: 1px solid var(--color-border);
	}

	.gradebook th {
		padding: 10px 12px;
		font-weight: 500;
		color: var(--color-muted);
		text-align: left;
		white-space: nowrap;
	}

	.th-name  { min-width: 200px; }
	.th-score { width: 90px; text-align: center; }
	.th-avg   { width: 70px; text-align: center; color: var(--color-muted-2); }
	.th-add   { width: 150px; }

	.col-header {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
	}

	.btn-del-col {
		background: none;
		border: none;
		color: var(--color-muted-2);
		cursor: pointer;
		font-size: 10px;
		padding: 0 2px;
		line-height: 1;
		transition: color 0.15s;
	}
	.btn-del-col:hover { color: var(--color-danger); }

	/* Rows */
	.gradebook tbody tr {
		border-bottom: 1px solid var(--color-border-muted);
		transition: background 0.1s;
	}
	.gradebook tbody tr:last-child { border-bottom: none; }
	.gradebook tbody tr:hover { background: var(--color-surface-2); }
	.row-odd { background: var(--color-surface); }

	.td-name {
		padding: 8px 12px;
		color: var(--color-foreground);
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.row-num {
		font-size: 11px;
		color: var(--color-muted-2);
		width: 18px;
		text-align: right;
		flex-shrink: 0;
	}

	.td-score { padding: 6px 8px; text-align: center; }
	.td-avg   { padding: 8px 12px; text-align: center; font-weight: 500; color: var(--color-primary); }

	.score-input {
		width: 70px;
		padding: 5px 8px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-foreground);
		font-size: 13px;
		text-align: center;
		transition: border-color 0.15s;
		appearance: textfield;
	-moz-appearance: textfield;
	}
	.score-input:focus {
		outline: none;
		border-color: var(--color-primary);
		background: var(--color-surface-2);
	}
	.score-input::-webkit-inner-spin-button,
	.score-input::-webkit-outer-spin-button { -webkit-appearance: none; }

	/* Add column */
	.add-col { display: flex; gap: 4px; align-items: center; }

	.input-col {
		flex: 1;
		min-width: 0;
		padding: 5px 8px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-foreground);
		font-size: 12px;
	}
	.input-col:focus { outline: none; border-color: var(--color-primary); }
	.input-col::placeholder { color: var(--color-muted-2); }

	.btn-add-col {
		padding: 5px 10px;
		border-radius: 6px;
		border: 1px solid var(--color-primary);
		background: var(--color-primary-muted);
		color: var(--color-primary);
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}
	.btn-add-col:hover:not(:disabled) { background: var(--color-primary); color: white; }
	.btn-add-col:disabled { opacity: 0.4; cursor: not-allowed; }

	/* Save button */
	.btn-save {
		padding: 8px 20px;
		border-radius: 8px;
		border: none;
		background: var(--color-primary);
		color: white;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.15s;
	}
	.btn-save:hover:not(:disabled) { background: var(--color-primary-hover); }
	.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

	/* Feedback */
	.error-banner {
		padding: 10px 14px;
		border-radius: 8px;
		background: var(--color-danger-muted);
		color: var(--color-danger);
		font-size: 13px;
		margin-bottom: 16px;
	}
	.success-banner {
		padding: 10px 14px;
		border-radius: 8px;
		background: var(--color-success-muted);
		color: var(--color-success);
		font-size: 13px;
		margin-bottom: 16px;
	}

	.empty, .hint {
		color: var(--color-muted);
		font-size: 13px;
		padding: 16px 0;
	}

	/* Skeleton */
	.skeleton-table { display: flex; flex-direction: column; gap: 6px; }
	.skeleton-row {
		height: 44px;
		border-radius: 8px;
		background: var(--color-surface);
		animation: pulse 1.5s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.4; }
	}
</style>
