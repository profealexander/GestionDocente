<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';
	import { gradesApi, type Grade, type Student } from '$lib/api/grades';

	// ── Estado ───────────────────────────────────────────────────────
	let grades      = $state<Grade[]>([]);
	let students    = $state<Student[]>([]);
	let tab         = $state<'individual' | 'masivo' | 'lista'>('individual');
	let filterGrade = $state(0);
	let loading     = $state(false);
	let sortMode    = $state<'apellidos' | 'nombres'>('apellidos');
	let msg         = $state('');
	let msgType     = $state<'ok' | 'err'>('ok');

	// Individual form
	let form = $state({ first_name: '', last_name: '', second_last_name: '', grade_id: 0, section: 'A' });

	// Bulk
	let bulkText  = $state('');
	let bulkGrade = $state(0);
	let bulkSection = $state('A');

	onMount(async () => {
		grades = await gradesApi.list();
	});

	async function loadStudents() {
		if (!filterGrade) return;
		loading = true;
		try {
			const res = await api.get<any[]>(`/students/?grade_id=${filterGrade}&status=active`);
			students = res.map((s: any) => ({ id: s.id, full_name: s.full_name }));
		} finally {
			loading = false;
		}
	}

	$effect(() => { if (filterGrade) loadStudents(); });

	// La API devuelve "APELLIDO1 APELLIDO2 NOMBRE1 NOMBRE2" (full_name del modelo)
	// Reordenamos para mostrar según la preferencia
	function formatName(full_name: string, mode: 'apellidos' | 'nombres'): string {
		if (mode === 'apellidos') return full_name; // ya viene APELLIDO NOMBRE
		// Invertir: mostrar como NOMBRE APELLIDO
		const parts = full_name.trim().split(/\s+/);
		if (parts.length >= 4) return `${parts[2]} ${parts[3]} ${parts[0]} ${parts[1]}`;
		if (parts.length === 3) return `${parts[2]} ${parts[0]} ${parts[1]}`;
		if (parts.length === 2) return `${parts[1]} ${parts[0]}`;
		return full_name;
	}

	const sortedStudents = $derived(
		[...students].sort((a, b) => {
			const na = formatName(a.full_name, sortMode);
			const nb = formatName(b.full_name, sortMode);
			return na.localeCompare(nb, 'es');
		})
	);

	function notify(text: string, type: 'ok' | 'err' = 'ok') {
		msg = text; msgType = type;
		setTimeout(() => msg = '', 4000);
	}

	// ── Individual ───────────────────────────────────────────────────
	async function saveIndividual() {
		if (!form.first_name || !form.last_name || !form.grade_id) {
			return notify('Completa nombre, apellido y curso.', 'err');
		}
		try {
			await api.post('/students/', form);
			notify('Estudiante creado correctamente.');
			form = { first_name: '', last_name: '', second_last_name: '', grade_id: form.grade_id, section: form.section };
			if (filterGrade === form.grade_id) loadStudents();
		} catch (e: any) { notify(e.message, 'err'); }
	}

	// ── Masivo ───────────────────────────────────────────────────────
	async function saveBulk() {
		if (!bulkGrade || !bulkText.trim()) {
			return notify('Selecciona un curso y pega la lista de nombres.', 'err');
		}
		const lines = bulkText.trim().split('\n').map(l => l.trim()).filter(Boolean);
		const students_list = lines.map(l => ({ full_name: l, grade_id: bulkGrade, section: bulkSection }));
		try {
			const res = await api.post<{ message: string }>('/students/bulk/', { students: students_list });
			notify(res.message);
			bulkText = '';
			if (filterGrade === bulkGrade) loadStudents();
		} catch (e: any) { notify(e.message, 'err'); }
	}

	// ── Desactivar ───────────────────────────────────────────────────
	async function deactivate(id: number, name: string) {
		if (!confirm(`¿Desactivar a ${name}?`)) return;
		try {
			await api.put(`/students/${id}`, { status: 'inactive' });
			students = students.filter(s => s.id !== id);
			notify('Estudiante desactivado.');
		} catch (e: any) { notify(e.message, 'err'); }
	}
</script>

<div class="page">
	<div class="page-header">
		<div>
			<h1>Gestión de Estudiantes</h1>
			<p class="subtitle">Carga individual o masiva de estudiantes</p>
		</div>
	</div>

	{#if msg}
		<div class="banner {msgType}">{msg}</div>
	{/if}

	<!-- Tabs -->
	<div class="tabs">
		<button class="tab" class:active={tab === 'individual'} onclick={() => tab = 'individual'}>
			➕ Individual
		</button>
		<button class="tab" class:active={tab === 'masivo'} onclick={() => tab = 'masivo'}>
			📋 Carga masiva
		</button>
		<button class="tab" class:active={tab === 'lista'} onclick={() => tab = 'lista'}>
			👥 Ver lista
		</button>
	</div>

	<!-- ── Tab: Individual ── -->
	{#if tab === 'individual'}
		<div class="card">
			<p class="card-title">Nuevo estudiante</p>
			<div class="form-grid">
				<div class="field">
					<label>Primer apellido *</label>
					<input bind:value={form.last_name} placeholder="ESPEJO" />
				</div>
				<div class="field">
					<label>Segundo apellido</label>
					<input bind:value={form.second_last_name} placeholder="TORRES" />
				</div>
				<div class="field">
					<label>Nombres *</label>
					<input bind:value={form.first_name} placeholder="JUAN CARLOS" />
				</div>
				<div class="field">
					<label>Curso *</label>
					<select bind:value={form.grade_id}>
						<option value={0}>Seleccionar...</option>
						{#each grades as g}
							<option value={g.id}>{g.name}</option>
						{/each}
					</select>
				</div>
				<div class="field">
					<label>Sección</label>
					<input bind:value={form.section} placeholder="A" maxlength="5" />
				</div>
			</div>
			<button class="btn-primary" onclick={saveIndividual}>Guardar estudiante</button>
		</div>
	{/if}

	<!-- ── Tab: Masivo ── -->
	{#if tab === 'masivo'}
		<div class="card">
			<p class="card-title">Importación masiva</p>
			<p class="hint">
				Pega una lista de nombres, <strong>uno por línea</strong>.<br />
				Formato: <code>APELLIDO1 APELLIDO2 NOMBRE1 NOMBRE2</code><br />
				Las primeras dos palabras son los apellidos, el resto son los nombres.
			</p>

			<div class="form-row">
				<div class="field" style="flex:1">
					<label>Curso *</label>
					<select bind:value={bulkGrade}>
						<option value={0}>Seleccionar...</option>
						{#each grades as g}
							<option value={g.id}>{g.name}</option>
						{/each}
					</select>
				</div>
				<div class="field" style="width:100px">
					<label>Sección</label>
					<input bind:value={bulkSection} placeholder="A" maxlength="5" />
				</div>
			</div>

			<div class="field">
				<label>Lista de nombres ({bulkText.trim().split('\n').filter(Boolean).length} nombres)</label>
				<textarea
					bind:value={bulkText}
					rows={12}
					placeholder="ESPEJO TORRES JUAN CARLOS&#10;RODRIGUEZ MORA ANA LUCIA&#10;GOMEZ VILLA PEDRO LUIS&#10;..."
				></textarea>
			</div>

			<button class="btn-primary" onclick={saveBulk}>
				Importar {bulkText.trim().split('\n').filter(Boolean).length} estudiantes
			</button>
		</div>
	{/if}

	<!-- ── Tab: Lista ── -->
	{#if tab === 'lista'}
		<div class="card">
			<div class="list-header">
				<p class="card-title" style="margin:0">Estudiantes activos</p>
				<select bind:value={filterGrade} style="width:200px">
					<option value={0}>Seleccionar curso...</option>
					{#each grades as g}
						<option value={g.id}>{g.name}</option>
					{/each}
				</select>
			</div>

			{#if !filterGrade}
				<p class="empty">Selecciona un curso para ver la lista.</p>
			{:else if loading}
				{#each [1,2,3,4,5] as _}
					<div class="skeleton-row"></div>
				{/each}
			{:else if students.length === 0}
				<p class="empty">Sin estudiantes en este curso.</p>
			{:else}
				<div class="list-controls">
					<span class="count-label">{students.length} estudiantes</span>
					<div class="sort-toggle">
						<button
							class="sort-btn"
							class:active={sortMode === 'apellidos'}
							onclick={() => sortMode = 'apellidos'}
						>Apellidos, Nombres</button>
						<button
							class="sort-btn"
							class:active={sortMode === 'nombres'}
							onclick={() => sortMode = 'nombres'}
						>Nombres, Apellidos</button>
					</div>
				</div>
				<div class="student-list">
					{#each sortedStudents as s, i}
						<div class="student-row">
							<span class="num">{i + 1}</span>
							<span class="name">{formatName(s.full_name, sortMode)}</span>
							<button class="btn-danger-sm" onclick={() => deactivate(s.id, s.full_name)}>
								Desactivar
							</button>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.page { max-width: 860px; margin: 0 auto; }

	.page-header { margin-bottom: 24px; }
	h1 { font-size: 22px; font-weight: 600; color: var(--color-foreground); margin: 0 0 4px; }
	.subtitle { font-size: 13px; color: var(--color-muted); margin: 0; }

	.banner {
		padding: 10px 14px;
		border-radius: 8px;
		font-size: 13px;
		margin-bottom: 16px;
	}
	.banner.ok  { background: var(--color-success-muted); color: var(--color-success); }
	.banner.err { background: var(--color-danger-muted);  color: var(--color-danger); }

	/* Tabs */
	.tabs {
		display: flex;
		gap: 4px;
		margin-bottom: 20px;
		border-bottom: 1px solid var(--color-border);
		padding-bottom: 0;
	}

	.tab {
		padding: 8px 16px;
		border: none;
		background: none;
		color: var(--color-muted);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		border-bottom: 2px solid transparent;
		margin-bottom: -1px;
		transition: color 0.15s, border-color 0.15s;
	}

	.tab:hover { color: var(--color-foreground); }
	.tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

	/* Card */
	.card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 24px;
	}

	.card-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 18px;
	}

	.hint {
		font-size: 12.5px;
		color: var(--color-muted);
		line-height: 1.6;
		margin: 0 0 18px;
		padding: 12px;
		background: var(--color-surface-2);
		border-radius: 8px;
	}

	code {
		background: var(--color-surface-3);
		padding: 1px 6px;
		border-radius: 4px;
		font-size: 12px;
		color: var(--color-primary);
	}

	/* Form */
	.form-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 14px;
		margin-bottom: 18px;
	}

	.form-row {
		display: flex;
		gap: 14px;
		margin-bottom: 14px;
	}

	.field { display: flex; flex-direction: column; gap: 5px; }
	label { font-size: 12px; color: var(--color-muted); }

	input, select, textarea {
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-foreground);
		font-size: 13px;
		font-family: inherit;
		padding: 8px 10px;
		outline: none;
		transition: border-color 0.15s;
		resize: vertical;
	}

	input:focus, select:focus, textarea:focus { border-color: var(--color-primary); }

	.btn-primary {
		padding: 9px 20px;
		border-radius: 8px;
		border: none;
		background: var(--color-primary);
		color: white;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		margin-top: 4px;
		transition: background 0.15s;
	}
	.btn-primary:hover { background: var(--color-primary-hover); }

	/* Lista */
	.list-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 16px;
	}

	.list-controls {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 10px;
		flex-wrap: wrap;
		gap: 8px;
	}

	.count-label {
		font-size: 12px;
		color: var(--color-muted-2);
		margin: 0;
	}

	.sort-toggle {
		display: flex;
		gap: 2px;
		background: var(--color-surface-2);
		border-radius: 8px;
		padding: 3px;
	}

	.sort-btn {
		padding: 4px 12px;
		border: none;
		border-radius: 6px;
		background: transparent;
		color: var(--color-muted);
		font-size: 12px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.sort-btn.active {
		background: var(--color-surface-3);
		color: var(--color-foreground);
		font-weight: 500;
	}

	.student-list { display: flex; flex-direction: column; gap: 4px; }

	.student-row {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 9px 12px;
		background: var(--color-surface-2);
		border-radius: 8px;
	}

	.num { font-size: 12px; color: var(--color-muted-2); width: 24px; text-align: right; }
	.name { flex: 1; font-size: 13.5px; color: var(--color-foreground); }

	.btn-danger-sm {
		padding: 4px 10px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-muted);
		font-size: 11px;
		cursor: pointer;
		transition: all 0.15s;
	}
	.btn-danger-sm:hover { border-color: var(--color-danger); color: var(--color-danger); }

	.skeleton-row {
		height: 38px; border-radius: 8px;
		background: var(--color-surface-2);
		margin-bottom: 4px;
		animation: pulse 1.5s infinite;
	}

	.empty { color: var(--color-muted); font-size: 13px; }

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.4; }
	}

	@media (max-width: 600px) {
		.form-grid { grid-template-columns: 1fr; }
	}
</style>
