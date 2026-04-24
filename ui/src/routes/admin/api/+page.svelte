<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api/client';

	interface ModelStat {
		provider: string;
		model: string;
		calls: number;
		prompt_tokens: number;
		completion_tokens: number;
		cached_tokens: number;
		last_used: string | null;
	}

	interface Totals {
		calls: number;
		prompt_tokens: number;
		completion_tokens: number;
		cached_tokens: number;
	}

	let stats   = $state<ModelStat[]>([]);
	let totals  = $state<Totals | null>(null);
	let loading = $state(true);
	let error   = $state('');

	const PROVIDER_COLORS: Record<string, string> = {
		google:     '#4285f4',
		groq:       '#f97316',
		zai:        '#8b5cf6',
		zhipu:      '#8b5cf6',
		openrouter: '#10b981',
		openai:     '#10a37f',
		mistral:    '#ff7000',
		deepseek:   '#1e88e5',
	};

	function providerColor(p: string): string {
		return PROVIDER_COLORS[p.toLowerCase()] ?? '#6b7280';
	}

	function fmt(n: number): string {
		if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
		if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
		return String(n);
	}

	function fmtDate(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return d.toLocaleDateString('es', { day: '2-digit', month: 'short' })
			+ ' ' + d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
	}

	async function load() {
		loading = true;
		error   = '';
		try {
			const res = await api.get<{ stats: ModelStat[]; totals: Totals }>('/llm-stats');
			stats  = res.stats;
			totals = res.totals;
		} catch (e: any) {
			error = e.message ?? 'Error al cargar';
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<div class="page">
	<div class="page-header">
		<div>
			<h1 class="page-title">API — Uso de modelos LLM</h1>
			<p class="page-sub">Tokens consumidos por proveedor y modelo</p>
		</div>
		<button class="btn-refresh" onclick={load} disabled={loading}>
			{loading ? 'Cargando…' : 'Actualizar'}
		</button>
	</div>

	{#if error}
		<div class="alert-err">{error}</div>
	{/if}

	<!-- Totales -->
	{#if totals}
		<div class="totals-grid">
			<div class="total-card">
				<span class="total-value">{fmt(totals.calls)}</span>
				<span class="total-label">Llamadas</span>
			</div>
			<div class="total-card">
				<span class="total-value">{fmt(totals.prompt_tokens)}</span>
				<span class="total-label">Tokens entrada</span>
			</div>
			<div class="total-card">
				<span class="total-value">{fmt(totals.completion_tokens)}</span>
				<span class="total-label">Tokens salida</span>
			</div>
			<div class="total-card accent">
				<span class="total-value">{fmt(totals.cached_tokens)}</span>
				<span class="total-label">Tokens caché</span>
			</div>
		</div>
	{/if}

	<!-- Tabla por modelo -->
	{#if loading}
		<div class="loading">Cargando estadísticas…</div>
	{:else if stats.length === 0}
		<div class="empty">Sin registros aún. Los modelos aparecen aquí al usarlos.</div>
	{:else}
		<div class="table-wrap">
			<table>
				<thead>
					<tr>
						<th>Proveedor</th>
						<th>Modelo</th>
						<th class="num">Llamadas</th>
						<th class="num">Entrada</th>
						<th class="num">Salida</th>
						<th class="num">Caché</th>
						<th class="num">Último uso</th>
					</tr>
				</thead>
				<tbody>
					{#each stats as row}
						<tr>
							<td>
								<span class="badge" style="background:{providerColor(row.provider)}22; color:{providerColor(row.provider)}">
									{row.provider}
								</span>
							</td>
							<td class="model-cell">{row.model}</td>
							<td class="num">{row.calls.toLocaleString()}</td>
							<td class="num">{fmt(row.prompt_tokens)}</td>
							<td class="num">{fmt(row.completion_tokens)}</td>
							<td class="num">
								{#if row.cached_tokens > 0}
									<span class="cached">{fmt(row.cached_tokens)}</span>
								{:else}
									<span class="muted">—</span>
								{/if}
							</td>
							<td class="num muted">{fmtDate(row.last_used)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.page { max-width: 900px; }

	.page-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		margin-bottom: 24px;
	}

	.page-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 4px;
	}

	.page-sub {
		font-size: 13px;
		color: var(--color-muted);
		margin: 0;
	}

	.btn-refresh {
		padding: 7px 16px;
		border-radius: 8px;
		border: 1px solid var(--color-border);
		background: var(--color-surface-2);
		color: var(--color-foreground);
		font-size: 13px;
		cursor: pointer;
	}

	.btn-refresh:hover:not(:disabled) {
		background: var(--color-surface-3);
	}

	.btn-refresh:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.totals-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 12px;
		margin-bottom: 24px;
	}

	.total-card {
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 10px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.total-card.accent {
		border-color: #4285f433;
		background: #4285f408;
	}

	.total-value {
		font-size: 22px;
		font-weight: 600;
		color: var(--color-foreground);
		line-height: 1;
	}

	.total-label {
		font-size: 11.5px;
		color: var(--color-muted);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.table-wrap {
		overflow-x: auto;
		border: 1px solid var(--color-border);
		border-radius: 10px;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 13.5px;
	}

	thead tr {
		background: var(--color-surface-2);
		border-bottom: 1px solid var(--color-border);
	}

	th {
		padding: 10px 14px;
		text-align: left;
		font-size: 11px;
		font-weight: 500;
		color: var(--color-muted-2);
		text-transform: uppercase;
		letter-spacing: 0.6px;
	}

	th.num, td.num {
		text-align: right;
	}

	td {
		padding: 11px 14px;
		border-bottom: 1px solid var(--color-border-muted);
		color: var(--color-foreground);
	}

	tr:last-child td {
		border-bottom: none;
	}

	tr:hover td {
		background: var(--color-surface-2);
	}

	.badge {
		display: inline-block;
		padding: 2px 8px;
		border-radius: 5px;
		font-size: 11.5px;
		font-weight: 500;
		text-transform: capitalize;
	}

	.model-cell {
		font-family: monospace;
		font-size: 12.5px;
		color: var(--color-muted);
	}

	.cached {
		color: #4285f4;
		font-weight: 500;
	}

	.muted {
		color: var(--color-muted-2);
	}

	.loading, .empty {
		padding: 40px;
		text-align: center;
		color: var(--color-muted);
		font-size: 14px;
	}

	.alert-err {
		padding: 10px 14px;
		border-radius: 8px;
		background: rgba(239, 68, 68, 0.1);
		color: #f87171;
		font-size: 13px;
		margin-bottom: 16px;
	}
</style>
