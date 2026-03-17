<script lang="ts">
	import { onMount } from 'svelte';
	import { gradesApi, type Grade } from '$lib/api/grades';
	import { api } from '$lib/api/client';

	interface Subject { id: number; name: string; }
	interface Homework {
		id: number;
		sequence_num: number;
		description: string;
		subject_name: string;
		grade_name: string;
		delivery_date: string | null;
		trimester_num: number;
		is_open: boolean;
	}

	// ── Estado formulario ────────────────────────────────────────────
	let grades   = $state<Grade[]>([]);
	let subjects = $state<Subject[]>([]);
	let homeworks = $state<Homework[]>([]);

	let form = $state({
		grade_id:      0,
		subject_id:    0,
		description:   '',
		delivery_date: '',
	});

	let saving       = $state(false);
	let savedOk      = $state(false);
	let error        = $state('');
	let loadingHw    = $state(false);

	onMount(async () => {
		try {
			[grades, subjects] = await Promise.all([
				gradesApi.list(),
				api.get<Subject[]>('/subjects'),
			]);
		} catch (e: any) { error = e.message; }
	});

	async function loadHomeworks() {
		if (!form.grade_id) return;
		loadingHw = true;
		try {
			homeworks = await api.get<Homework[]>(
				`/homework?grade_id=${form.grade_id}&is_open=true`
			);
		} catch { homeworks = []; }
		finally { loadingHw = false; }
	}

	$effect(() => {
		if (form.grade_id) loadHomeworks();
	});

	async function submit() {
		if (!form.description.trim() || !form.grade_id) {
			error = 'Completa la descripción y el curso.';
			return;
		}
		saving = true;
		error = '';
		savedOk = false;
		try {
			await api.post('/homework', {
				description:   form.description.trim(),
				grade_id:      form.grade_id,
				subject_id:    form.subject_id || null,
				delivery_date: form.delivery_date || null,
			});
			form.description   = '';
			form.delivery_date = '';
			savedOk = true;
			setTimeout(() => savedOk = false, 3000);
			await loadHomeworks();
		} catch (e: any) {
			error = e.message;
		} finally {
			saving = false;
		}
	}

	async function closeTask(id: number) {
		try {
			await api.put(`/homework/${id}`, { is_open: false });
			homeworks = homeworks.filter(h => h.id !== id);
		} catch (e: any) { error = e.message; }
	}
</script>

<div class="page">
	<div class="page-header">
		<div>
			<h1>Tareas</h1>
			<p class="subtitle">Registro y seguimiento de tareas</p>
		</div>
	</div>

	{#if error}
		<div class="error-banner">{error}</div>
	{/if}
	{#if savedOk}
		<div class="success-banner">✅ Tarea registrada correctamente</div>
	{/if}

	<div class="layout">
		<!-- Formulario -->
		<div class="form-card">
			<p class="card-title">Nueva tarea</p>

			<div class="field">
				<label>Curso *</label>
				<select bind:value={form.grade_id}>
					<option value={0}>Seleccionar curso...</option>
					{#each grades as g}
						<option value={g.id}>{g.name}</option>
					{/each}
				</select>
			</div>

			<div class="field">
				<label>Materia</label>
				<select bind:value={form.subject_id}>
					<option value={0}>Sin materia</option>
					{#each subjects as s}
						<option value={s.id}>{s.name}</option>
					{/each}
				</select>
			</div>

			<div class="field">
				<label>Descripción *</label>
				<textarea
					bind:value={form.description}
					placeholder="Ej: Leer páginas 45–60 del libro de historia y responder cuestionario..."
					rows={4}
				></textarea>
			</div>

			<div class="field">
				<label>Fecha de entrega</label>
				<input type="date" bind:value={form.delivery_date} />
			</div>

			<button class="btn-primary" onclick={submit} disabled={saving}>
				{saving ? 'Guardando...' : '+ Registrar tarea'}
			</button>
		</div>

		<!-- Lista de tareas abiertas -->
		<div class="hw-list-section">
			<p class="card-title">
				Tareas abiertas
				{#if form.grade_id && homeworks.length > 0}
					<span class="count-badge">{homeworks.length}</span>
				{/if}
			</p>

			{#if !form.grade_id}
				<p class="empty">Selecciona un curso para ver sus tareas.</p>
			{:else if loadingHw}
				{#each [1,2,3] as _}
					<div class="skeleton-hw"></div>
				{/each}
			{:else if homeworks.length === 0}
				<p class="empty">Sin tareas abiertas para este curso.</p>
			{:else}
				<div class="hw-list">
					{#each homeworks as hw}
						<div class="hw-card">
							<div class="hw-meta">
								<span class="hw-num">#{hw.sequence_num}</span>
								<span class="hw-subject">{hw.subject_name ?? 'Sin materia'}</span>
								{#if hw.delivery_date}
									<span class="hw-date">
										📅 {new Date(hw.delivery_date + 'T00:00:00').toLocaleDateString('es-EC', { day: 'numeric', month: 'short' })}
									</span>
								{/if}
							</div>
							<p class="hw-desc">{hw.description}</p>
							<div class="hw-actions">
								<button class="btn-close" onclick={() => closeTask(hw.id)}>
									Cerrar tarea
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.page { max-width: 1000px; margin: 0 auto; }

	.page-header { margin-bottom: 28px; }

	h1 { font-size: 22px; font-weight: 600; color: var(--color-foreground); margin: 0 0 4px; }
	.subtitle { font-size: 13px; color: var(--color-muted); margin: 0; }
	.card-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 16px;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.layout {
		display: grid;
		grid-template-columns: 360px 1fr;
		gap: 20px;
		align-items: start;
	}

	@media (max-width: 720px) {
		.layout { grid-template-columns: 1fr; }
	}

	.form-card, .hw-list-section {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 20px;
	}

	.field { margin-bottom: 14px; }
	label { display: block; font-size: 12px; color: var(--color-muted); margin-bottom: 5px; }

	select, input, textarea {
		width: 100%;
		padding: 8px 10px;
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-foreground);
		font-size: 13px;
		font-family: inherit;
		outline: none;
		resize: vertical;
		transition: border-color 0.15s;
	}

	select:focus, input:focus, textarea:focus {
		border-color: var(--color-primary);
	}

	.btn-primary {
		width: 100%;
		padding: 9px;
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

	.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

	/* HW list */
	.hw-list { display: flex; flex-direction: column; gap: 10px; }

	.hw-card {
		padding: 14px;
		background: var(--color-surface-2);
		border: 1px solid var(--color-border-muted);
		border-radius: 10px;
	}

	.hw-meta {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 8px;
	}

	.hw-num {
		font-size: 11px;
		font-weight: 600;
		color: var(--color-primary);
		background: var(--color-primary-muted);
		padding: 2px 7px;
		border-radius: 10px;
	}

	.hw-subject {
		font-size: 12px;
		font-weight: 500;
		color: var(--color-foreground);
	}

	.hw-date {
		font-size: 11px;
		color: var(--color-muted);
		margin-left: auto;
	}

	.hw-desc {
		font-size: 13px;
		color: var(--color-muted);
		margin: 0 0 10px;
		line-height: 1.5;
	}

	.hw-actions { display: flex; justify-content: flex-end; }

	.btn-close {
		padding: 5px 12px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-muted);
		font-size: 12px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.btn-close:hover { border-color: var(--color-danger); color: var(--color-danger); }

	.count-badge {
		background: var(--color-surface-3);
		color: var(--color-muted);
		font-size: 11px;
		padding: 1px 7px;
		border-radius: 10px;
		font-weight: 400;
	}

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

	.skeleton-hw {
		height: 90px;
		border-radius: 10px;
		background: var(--color-surface-2);
		margin-bottom: 10px;
		animation: pulse 1.5s infinite;
	}

	.empty { color: var(--color-muted); font-size: 13px; }

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.4; }
	}
</style>
