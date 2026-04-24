<script lang="ts">
	import { onMount } from 'svelte';
	import { gradesApi, type Grade } from '$lib/api/grades';
	import { cuotasApi, type Actividad, type ActividadDetalle, type Participante } from '$lib/api/cuotas';

	// ── Estado principal ──────────────────────────────────────────────
	let grades       = $state<Grade[]>([]);
	let actividades  = $state<Actividad[]>([]);
	let selected     = $state<ActividadDetalle | null>(null);
	let loadingList  = $state(false);
	let loadingDetail = $state(false);
	let error        = $state('');
	let success      = $state('');

	// ── Formulario nueva actividad ────────────────────────────────────
	let showForm  = $state(false);
	let savingAct = $state(false);
	let form = $state({ nombre: '', monto: '', descripcion: '' });

	// ── Agregar grado ─────────────────────────────────────────────────
	let addGradeId  = $state(0);
	let savingGrade = $state(false);

	// ── Registrar pago ────────────────────────────────────────────────
	let pagoStudentId = $state(0);
	let pagoMonto     = $state('');
	let pagoNotas     = $state('');
	let savingPago    = $state(false);

	// ── Exportar ──────────────────────────────────────────────────────
	let exporting = $state(false);

	// ── Pendientes de pago (computed) ─────────────────────────────────
	const pendientes = $derived(
		selected?.participantes.filter(p => !p.is_complete) ?? []
	);

	onMount(async () => {
		try {
			[grades] = await Promise.all([gradesApi.list()]);
		} catch (e: any) { error = e.message; }
		await loadActividades();
	});

	async function loadActividades() {
		loadingList = true;
		try {
			actividades = await cuotasApi.list();
		} catch (e: any) { error = e.message; }
		finally { loadingList = false; }
	}

	async function selectActividad(act: Actividad) {
		if (selected?.id === act.id) return;
		loadingDetail = true;
		error = '';
		success = '';
		pagoStudentId = 0;
		pagoMonto = '';
		pagoNotas = '';
		try {
			selected = await cuotasApi.get(act.id);
		} catch (e: any) { error = e.message; }
		finally { loadingDetail = false; }
	}

	async function createActividad() {
		const nombre = form.nombre.trim();
		const monto  = parseFloat(form.monto);
		if (!nombre || !monto || monto <= 0) {
			error = 'Nombre y monto son requeridos.';
			return;
		}
		savingAct = true;
		error = '';
		try {
			const act = await cuotasApi.create({
				nombre,
				monto,
				descripcion: form.descripcion.trim() || undefined,
			});
			form = { nombre: '', monto: '', descripcion: '' };
			showForm = false;
			actividades = [act, ...actividades];
			flash('✅ Actividad creada');
		} catch (e: any) { error = e.message; }
		finally { savingAct = false; }
	}

	async function addGrade() {
		if (!selected || !addGradeId) return;
		savingGrade = true;
		error = '';
		try {
			const res = await cuotasApi.addGrade(selected.id, addGradeId);
			addGradeId = 0;
			flash(`✅ ${res.added} estudiantes agregados`);
			selected = await cuotasApi.get(selected.id);
		} catch (e: any) { error = e.message; }
		finally { savingGrade = false; }
	}

	async function registerPago() {
		if (!selected || !pagoStudentId || !pagoMonto) return;
		const monto = parseFloat(pagoMonto);
		if (monto <= 0) { error = 'El monto debe ser positivo.'; return; }
		savingPago = true;
		error = '';
		try {
			await cuotasApi.registerPago(selected.id, {
				student_id: pagoStudentId,
				monto,
				notas: pagoNotas.trim() || undefined,
			});
			pagoStudentId = 0;
			pagoMonto = '';
			pagoNotas = '';
			flash('✅ Pago registrado');
			selected = await cuotasApi.get(selected.id);
		} catch (e: any) { error = e.message; }
		finally { savingPago = false; }
	}

	async function exportExcel() {
		if (!selected) return;
		exporting = true;
		error = '';
		try {
			await cuotasApi.exportExcel(selected.id, selected.nombre);
		} catch (e: any) { error = e.message; }
		finally { exporting = false; }
	}

	function flash(msg: string) {
		success = msg;
		setTimeout(() => success = '', 3500);
	}

	function fmtMonto(n: number) {
		return `$${n.toFixed(2)}`;
	}

	function statusClass(p: Participante) {
		if (p.is_complete) return 'complete';
		if (p.total_pagado > 0) return 'partial';
		return 'pending';
	}

	function statusLabel(p: Participante, monto: number) {
		if (p.is_complete) return 'Completo';
		if (p.total_pagado > 0) return `${fmtMonto(p.total_pagado)} / ${fmtMonto(monto)}`;
		return 'Pendiente';
	}
</script>

<div class="page">
	<div class="page-header">
		<div>
			<h1>Cuotas</h1>
			<p class="subtitle">Actividades escolares y control de pagos</p>
		</div>
		<button class="btn-primary" onclick={() => { showForm = !showForm; error = ''; }}>
			{showForm ? 'Cancelar' : '+ Nueva actividad'}
		</button>
	</div>

	{#if error}
		<div class="error-banner">{error}</div>
	{/if}
	{#if success}
		<div class="success-banner">{success}</div>
	{/if}

	<!-- Formulario nueva actividad -->
	{#if showForm}
		<div class="form-card form-inline">
			<p class="card-title">Nueva actividad</p>
			<div class="form-row">
				<div class="field">
					<label>Nombre *</label>
					<input
						type="text"
						bind:value={form.nombre}
						placeholder="Ej: Paseo de Grado"
					/>
				</div>
				<div class="field field-sm">
					<label>Monto objetivo *</label>
					<input
						type="number"
						bind:value={form.monto}
						placeholder="0.00"
						min="0.01"
						step="0.01"
					/>
				</div>
				<div class="field field-lg">
					<label>Descripción</label>
					<input
						type="text"
						bind:value={form.descripcion}
						placeholder="Opcional"
					/>
				</div>
				<div class="field field-btn">
					<label>&nbsp;</label>
					<button class="btn-primary" onclick={createActividad} disabled={savingAct}>
						{savingAct ? 'Guardando...' : 'Crear'}
					</button>
				</div>
			</div>
		</div>
	{/if}

	<div class="layout">
		<!-- Lista de actividades -->
		<div class="act-list-section">
			<p class="card-title">
				Actividades
				{#if actividades.length > 0}
					<span class="count-badge">{actividades.length}</span>
				{/if}
			</p>

			{#if loadingList}
				{#each [1,2,3] as _}
					<div class="skeleton-act"></div>
				{/each}
			{:else if actividades.length === 0}
				<p class="empty">Sin actividades. Crea una para comenzar.</p>
			{:else}
				<div class="act-list">
					{#each actividades as act}
						<button
							class="act-card"
							class:act-selected={selected?.id === act.id}
							onclick={() => selectActividad(act)}
						>
							<div class="act-nombre">{act.nombre}</div>
							<div class="act-monto">{fmtMonto(act.monto)}</div>
							{#if act.descripcion}
								<div class="act-desc">{act.descripcion}</div>
							{/if}
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Detalle de actividad -->
		<div class="detail-section">
			{#if !selected && !loadingDetail}
				<div class="empty-detail">
					<span class="empty-icon">💰</span>
					<p>Selecciona una actividad para ver el estado de pagos</p>
				</div>
			{:else if loadingDetail}
				<div class="skeleton-detail"></div>
			{:else if selected}
				<!-- Header del detalle -->
				<div class="detail-header">
					<div>
						<p class="detail-nombre">{selected.nombre}</p>
						{#if selected.descripcion}
							<p class="detail-desc">{selected.descripcion}</p>
						{/if}
					</div>
					<button
						class="btn-export"
						onclick={exportExcel}
						disabled={exporting || selected.participantes.length === 0}
						title={selected.participantes.length === 0 ? 'Sin participantes aún' : 'Exportar a Excel'}
					>
						{exporting ? 'Exportando...' : '↓ Excel'}
					</button>
				</div>

				<!-- Stats -->
				<div class="stats-row">
					<div class="stat-card">
						<span class="stat-val">{fmtMonto(selected.total_recaudado)}</span>
						<span class="stat-label">Recaudado</span>
					</div>
					<div class="stat-card stat-success">
						<span class="stat-val">{selected.total_completos}</span>
						<span class="stat-label">Completos</span>
					</div>
					<div class="stat-card stat-warning">
						<span class="stat-val">{selected.total_pendientes}</span>
						<span class="stat-label">Pendientes</span>
					</div>
					<div class="stat-card">
						<span class="stat-val">{selected.participantes.length}</span>
						<span class="stat-label">Total</span>
					</div>
				</div>

				<!-- Acciones: agregar grado + registrar pago -->
				<div class="actions-row">
					<!-- Agregar grado -->
					<div class="action-card">
						<p class="action-title">Agregar grado</p>
						<div class="action-inline">
							<select bind:value={addGradeId}>
								<option value={0}>Seleccionar grado...</option>
								{#each grades as g}
									<option value={g.id}>{g.name}</option>
								{/each}
							</select>
							<button
								class="btn-secondary"
								onclick={addGrade}
								disabled={!addGradeId || savingGrade}
							>
								{savingGrade ? '...' : 'Agregar'}
							</button>
						</div>
					</div>

					<!-- Registrar pago -->
					<div class="action-card">
						<p class="action-title">Registrar pago</p>
						<div class="action-inline">
							<select bind:value={pagoStudentId} disabled={pendientes.length === 0}>
								<option value={0}>
									{pendientes.length === 0 ? 'Todos completos 🎉' : 'Estudiante...'}
								</option>
								{#each pendientes as p}
									<option value={p.student_id}>{p.student_name}</option>
								{/each}
							</select>
							<input
								type="number"
								bind:value={pagoMonto}
								placeholder={fmtMonto(selected.monto)}
								min="0.01"
								step="0.01"
								class="input-sm"
								disabled={pendientes.length === 0}
							/>
							<input
								type="text"
								bind:value={pagoNotas}
								placeholder="Notas (opcional)"
								class="input-md"
								disabled={pendientes.length === 0}
							/>
							<button
								class="btn-secondary"
								onclick={registerPago}
								disabled={!pagoStudentId || !pagoMonto || savingPago || pendientes.length === 0}
							>
								{savingPago ? '...' : 'Pagar'}
							</button>
						</div>
					</div>
				</div>

				<!-- Tabla de participantes -->
				{#if selected.participantes.length === 0}
					<p class="empty">Sin participantes. Agrega un grado para comenzar.</p>
				{:else}
					<div class="table-wrap">
						<table>
							<thead>
								<tr>
									<th>#</th>
									<th>Alumno</th>
									<th>Estado</th>
									<th>Último pago</th>
								</tr>
							</thead>
							<tbody>
								{#each selected.participantes as p, i}
									<tr class="row-{statusClass(p)}">
										<td class="td-num">{i + 1}</td>
										<td class="td-name">{p.student_name}</td>
										<td>
											<span class="status-badge {statusClass(p)}">
												{statusLabel(p, selected.monto)}
											</span>
										</td>
										<td class="td-date">
											{#if p.pagos.length > 0}
												{new Date(p.pagos[p.pagos.length - 1].paid_at).toLocaleDateString('es-EC', { day: 'numeric', month: 'short' })}
											{:else}
												—
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			{/if}
		</div>
	</div>
</div>

<style>
	.page { max-width: 1100px; margin: 0 auto; }

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 24px;
	}

	h1 { font-size: 22px; font-weight: 600; color: var(--color-foreground); margin: 0 0 4px; }
	.subtitle { font-size: 13px; color: var(--color-muted); margin: 0; }

	.card-title {
		font-size: 13px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 14px;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	/* ── Inline create form ── */
	.form-inline {
		margin-bottom: 20px;
	}

	.form-row {
		display: flex;
		gap: 12px;
		align-items: flex-end;
		flex-wrap: wrap;
	}

	.form-row .field { margin-bottom: 0; flex: 1; min-width: 160px; }
	.field-sm { max-width: 140px; }
	.field-lg { flex: 2; }
	.field-btn { flex: 0 0 auto; }
	.field-btn .btn-primary { width: auto; padding: 8px 18px; margin-top: 0; }

	/* ── Layout ── */
	.layout {
		display: grid;
		grid-template-columns: 300px 1fr;
		gap: 16px;
		align-items: start;
	}

	@media (max-width: 760px) {
		.layout { grid-template-columns: 1fr; }
	}

	/* ── Activities list ── */
	.act-list-section {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 18px;
	}

	.act-list { display: flex; flex-direction: column; gap: 8px; }

	.act-card {
		width: 100%;
		text-align: left;
		padding: 12px 14px;
		background: var(--color-surface-2);
		border: 1px solid var(--color-border-muted);
		border-radius: 10px;
		cursor: pointer;
		transition: border-color 0.15s, background 0.15s;
	}

	.act-card:hover { border-color: var(--color-primary); }
	.act-card.act-selected {
		border-color: var(--color-primary);
		background: var(--color-primary-muted);
	}

	.act-nombre { font-size: 13px; font-weight: 500; color: var(--color-foreground); }
	.act-monto {
		font-size: 12px;
		color: var(--color-primary);
		font-weight: 600;
		margin-top: 2px;
	}
	.act-desc { font-size: 11px; color: var(--color-muted); margin-top: 3px; }

	/* ── Detail section ── */
	.detail-section {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 18px;
		min-height: 200px;
	}

	.empty-detail {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 12px;
		padding: 60px 0;
		color: var(--color-muted);
		font-size: 13px;
	}

	.empty-icon { font-size: 32px; }

	.detail-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 16px;
	}

	.detail-nombre { font-size: 16px; font-weight: 600; color: var(--color-foreground); margin: 0 0 3px; }
	.detail-desc { font-size: 12px; color: var(--color-muted); margin: 0; }

	/* ── Stats ── */
	.stats-row {
		display: flex;
		gap: 10px;
		margin-bottom: 16px;
		flex-wrap: wrap;
	}

	.stat-card {
		flex: 1;
		min-width: 80px;
		background: var(--color-surface-2);
		border: 1px solid var(--color-border-muted);
		border-radius: 10px;
		padding: 10px 14px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.stat-success { border-color: rgba(34, 197, 94, 0.3); }
	.stat-warning { border-color: rgba(245, 158, 11, 0.3); }

	.stat-val {
		font-size: 18px;
		font-weight: 600;
		color: var(--color-foreground);
	}

	.stat-label { font-size: 11px; color: var(--color-muted); }

	/* ── Actions row ── */
	.actions-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 12px;
		margin-bottom: 16px;
	}

	@media (max-width: 900px) {
		.actions-row { grid-template-columns: 1fr; }
	}

	.action-card {
		background: var(--color-surface-2);
		border: 1px solid var(--color-border-muted);
		border-radius: 10px;
		padding: 12px 14px;
	}

	.action-title {
		font-size: 11px;
		font-weight: 600;
		color: var(--color-muted);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0 0 8px;
	}

	.action-inline {
		display: flex;
		gap: 8px;
		align-items: center;
		flex-wrap: wrap;
	}

	.action-inline select,
	.action-inline input {
		flex: 1;
		min-width: 100px;
	}

	.input-sm { max-width: 90px; flex: 0 0 auto !important; }
	.input-md { max-width: 140px; }

	/* ── Table ── */
	.table-wrap {
		overflow-x: auto;
		border-radius: 10px;
		border: 1px solid var(--color-border-muted);
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 13px;
	}

	thead tr {
		background: var(--color-surface-2);
	}

	th {
		padding: 9px 12px;
		text-align: left;
		font-size: 11px;
		font-weight: 600;
		color: var(--color-muted);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		border-bottom: 1px solid var(--color-border-muted);
	}

	td {
		padding: 9px 12px;
		border-bottom: 1px solid var(--color-border-muted);
		color: var(--color-foreground);
	}

	tbody tr:last-child td { border-bottom: none; }

	tbody tr:hover { background: var(--color-surface-2); }

	.row-complete td { opacity: 0.7; }
	.td-num { color: var(--color-muted); font-size: 12px; width: 30px; }
	.td-name { font-weight: 500; }
	.td-date { color: var(--color-muted); font-size: 12px; }

	/* ── Status badges ── */
	.status-badge {
		display: inline-block;
		padding: 3px 9px;
		border-radius: 10px;
		font-size: 11px;
		font-weight: 500;
	}

	.status-badge.complete {
		background: var(--color-success-muted);
		color: var(--color-success);
	}

	.status-badge.partial {
		background: rgba(245, 158, 11, 0.15);
		color: var(--color-warning);
	}

	.status-badge.pending {
		background: var(--color-danger-muted);
		color: var(--color-danger);
	}

	/* ── Buttons ── */
	.btn-primary {
		padding: 9px 16px;
		border-radius: 8px;
		border: none;
		background: var(--color-primary);
		color: white;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.15s;
		white-space: nowrap;
	}

	.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
	.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

	.btn-secondary {
		padding: 7px 14px;
		border-radius: 8px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-foreground);
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
		flex-shrink: 0;
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--color-primary);
		color: var(--color-primary);
	}

	.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

	.btn-export {
		padding: 6px 12px;
		border-radius: 8px;
		border: 1px solid var(--color-border);
		background: transparent;
		color: var(--color-muted);
		font-size: 12px;
		cursor: pointer;
		transition: all 0.15s;
		white-space: nowrap;
		flex-shrink: 0;
	}

	.btn-export:hover:not(:disabled) {
		border-color: var(--color-success);
		color: var(--color-success);
	}

	.btn-export:disabled { opacity: 0.4; cursor: not-allowed; }

	/* ── Shared form ── */
	.form-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		padding: 18px;
	}

	.field { margin-bottom: 14px; }
	label { display: block; font-size: 12px; color: var(--color-muted); margin-bottom: 5px; }

	select, input {
		width: 100%;
		padding: 8px 10px;
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-foreground);
		font-size: 13px;
		font-family: inherit;
		outline: none;
		transition: border-color 0.15s;
		box-sizing: border-box;
	}

	select:focus, input:focus { border-color: var(--color-primary); }

	/* ── Feedback ── */
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

	.skeleton-act {
		height: 64px;
		border-radius: 10px;
		background: var(--color-surface-2);
		margin-bottom: 8px;
		animation: pulse 1.5s infinite;
	}

	.skeleton-detail {
		height: 300px;
		border-radius: 10px;
		background: var(--color-surface-2);
		animation: pulse 1.5s infinite;
	}

	.empty { color: var(--color-muted); font-size: 13px; }
	.count-badge {
		background: var(--color-surface-3);
		color: var(--color-muted);
		font-size: 11px;
		padding: 1px 7px;
		border-radius: 10px;
		font-weight: 400;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.4; }
	}
</style>
