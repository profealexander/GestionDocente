<script lang="ts">
	import { onMount } from 'svelte';
	import { gradesApi, type Grade, type Student } from '$lib/api/grades';
	import { attendanceApi, type AttendanceStatus } from '$lib/api/attendance';

	// ── Estado ──────────────────────────────────────────────────────
	let grades = $state<Grade[]>([]);
	let selectedGrade = $state<Grade | null>(null);
	let students = $state<Student[]>([]);
	let statuses = $state<Record<number, AttendanceStatus>>({});
	let loadingGrades = $state(true);
	let loadingStudents = $state(false);
	let saving = $state(false);
	let savedOk = $state(false);
	let error = $state('');

	const today = new Date().toISOString().split('T')[0];
	const todayLabel = new Date().toLocaleDateString('es-EC', {
		weekday: 'long', day: 'numeric', month: 'long'
	});

	// ── Cargar cursos ────────────────────────────────────────────────
	onMount(async () => {
		try {
			grades = await gradesApi.list();
		} catch (e: any) {
			error = e.message;
		} finally {
			loadingGrades = false;
		}
	});

	async function selectGrade(grade: Grade) {
		selectedGrade = grade;
		students = [];
		statuses = {};
		loadingStudents = true;
		error = '';
		try {
			students = await gradesApi.students(grade.id);
			// Todos presentes por defecto
			for (const s of students) statuses[s.id] = 'present';
		} catch (e: any) {
			error = e.message;
		} finally {
			loadingStudents = false;
		}
	}

	function setStatus(studentId: number, status: AttendanceStatus) {
		statuses[studentId] = status;
	}

	// ── Contadores ───────────────────────────────────────────────────
	const counts = $derived({
		present:   students.filter(s => statuses[s.id] === 'present').length,
		absent:    students.filter(s => statuses[s.id] === 'absent').length,
		late:      students.filter(s => statuses[s.id] === 'late').length,
		justified: students.filter(s => statuses[s.id] === 'justified').length,
	});

	async function save() {
		if (!selectedGrade) return;
		saving = true;
		error = '';
		savedOk = false;
		try {
			const records = students.map(s => ({
				student_id: s.id,
				status: statuses[s.id] ?? 'present',
			}));
			await attendanceApi.save({ grade_id: selectedGrade.id, date: today, records });
			savedOk = true;
			setTimeout(() => savedOk = false, 3000);
		} catch (e: any) {
			error = e.message;
		} finally {
			saving = false;
		}
	}
</script>

<div class="page">
	<!-- Header -->
	<div class="page-header">
		<div>
			<h1>Asistencia</h1>
			<p class="date-label">{todayLabel}</p>
		</div>
		{#if selectedGrade && students.length > 0}
			<button class="btn-save" onclick={save} disabled={saving}>
				{saving ? 'Guardando...' : '✓ Guardar'}
			</button>
		{/if}
	</div>

	{#if error}
		<div class="error-banner">{error}</div>
	{/if}

	{#if savedOk}
		<div class="success-banner">✅ Asistencia guardada correctamente</div>
	{/if}

	<!-- Selector de curso -->
	<div class="section">
		<p class="section-label">Seleccionar curso</p>
		{#if loadingGrades}
			<div class="skeleton-row">
				{#each [1,2,3,4,5,6] as _}
					<div class="skeleton-chip"></div>
				{/each}
			</div>
		{:else}
			<div class="grade-chips">
				{#each grades as grade}
					<button
						class="grade-chip"
						class:selected={selectedGrade?.id === grade.id}
						onclick={() => selectGrade(grade)}
					>
						{grade.name}
					</button>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Lista de estudiantes -->
	{#if selectedGrade}
		<div class="section">
			<!-- Resumen -->
			{#if students.length > 0}
				<div class="summary-bar">
					<span class="badge present">✓ {counts.present} presentes</span>
					{#if counts.absent > 0}
						<span class="badge absent">✗ {counts.absent} faltas</span>
					{/if}
					{#if counts.late > 0}
						<span class="badge late">⏱ {counts.late} atrasos</span>
					{/if}
					{#if counts.justified > 0}
						<span class="badge justified">📋 {counts.justified} justificados</span>
					{/if}
				</div>
			{/if}

			{#if loadingStudents}
				<div class="student-list">
					{#each [1,2,3,4,5] as _}
						<div class="skeleton-student"></div>
					{/each}
				</div>
			{:else if students.length === 0}
				<p class="empty">No hay estudiantes en este curso.</p>
			{:else}
				<div class="student-list">
					{#each students as student, i}
						<div class="student-row" class:not-present={statuses[student.id] !== 'present'}>
							<span class="student-num">{i + 1}</span>
							<span class="student-name">{student.full_name}</span>
							<div class="status-buttons">
								<button
									class="status-btn present"
									class:active={statuses[student.id] === 'present'}
									onclick={() => setStatus(student.id, 'present')}
									title="Presente"
								>P</button>
								<button
									class="status-btn absent"
									class:active={statuses[student.id] === 'absent'}
									onclick={() => setStatus(student.id, 'absent')}
									title="Falta"
								>F</button>
								<button
									class="status-btn late"
									class:active={statuses[student.id] === 'late'}
									onclick={() => setStatus(student.id, 'late')}
									title="Atraso"
								>A</button>
								<button
									class="status-btn justified"
									class:active={statuses[student.id] === 'justified'}
									onclick={() => setStatus(student.id, 'justified')}
									title="Justificado"
								>J</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.page { max-width: 860px; margin: 0 auto; }

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 28px;
	}

	h1 {
		font-size: 22px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 4px;
	}

	.date-label {
		font-size: 13px;
		color: var(--color-muted);
		margin: 0;
		text-transform: capitalize;
	}

	.section { margin-bottom: 28px; }

	.section-label {
		font-size: 11px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.8px;
		color: var(--color-muted-2);
		margin: 0 0 10px;
	}

	/* Grade chips */
	.grade-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}

	.grade-chip {
		padding: 6px 14px;
		border-radius: 20px;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-muted);
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.grade-chip:hover { background: var(--color-surface-2); color: var(--color-foreground); }
	.grade-chip.selected {
		background: var(--color-primary-muted);
		border-color: var(--color-primary);
		color: var(--color-primary);
		font-weight: 500;
	}

	/* Summary bar */
	.summary-bar {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}

	.badge {
		padding: 4px 10px;
		border-radius: 12px;
		font-size: 12px;
		font-weight: 500;
	}

	.badge.present   { background: var(--color-success-muted); color: var(--color-success); }
	.badge.absent    { background: var(--color-danger-muted);  color: var(--color-danger);  }
	.badge.late      { background: rgba(245,158,11,0.15);       color: var(--color-warning); }
	.badge.justified { background: var(--color-surface-2);      color: var(--color-muted);   }

	/* Student list */
	.student-list {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.student-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 14px;
		border-radius: 8px;
		background: var(--color-surface);
		border: 1px solid var(--color-border-muted);
		transition: background 0.1s;
	}

	.student-row.not-present {
		background: var(--color-surface-2);
	}

	.student-num {
		font-size: 12px;
		color: var(--color-muted-2);
		width: 22px;
		text-align: right;
		flex-shrink: 0;
	}

	.student-name {
		flex: 1;
		font-size: 14px;
		color: var(--color-foreground);
	}

	.status-buttons {
		display: flex;
		gap: 4px;
	}

	.status-btn {
		width: 30px;
		height: 30px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: transparent;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.12s;
		color: var(--color-muted-2);
	}

	.status-btn:hover { border-color: var(--color-muted); color: var(--color-foreground); }

	.status-btn.present.active  { background: var(--color-success-muted); border-color: var(--color-success); color: var(--color-success); }
	.status-btn.absent.active   { background: var(--color-danger-muted);  border-color: var(--color-danger);  color: var(--color-danger);  }
	.status-btn.late.active     { background: rgba(245,158,11,0.15);       border-color: var(--color-warning);  color: var(--color-warning); }
	.status-btn.justified.active{ background: var(--color-surface-3);      border-color: var(--color-muted);    color: var(--color-foreground); }

	/* Buttons */
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

	/* Skeletons */
	.skeleton-row { display: flex; gap: 8px; flex-wrap: wrap; }
	.skeleton-chip {
		width: 90px; height: 32px;
		border-radius: 20px;
		background: var(--color-surface-2);
		animation: pulse 1.5s infinite;
	}

	.skeleton-student {
		height: 50px;
		border-radius: 8px;
		background: var(--color-surface);
		animation: pulse 1.5s infinite;
	}

	.empty { color: var(--color-muted); font-size: 13px; }

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.4; }
	}
</style>
