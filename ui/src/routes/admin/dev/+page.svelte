<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getToken, BASE_URL } from '$lib/api/client';

	// ── Tipos ────────────────────────────────────────────────────────────────────

	interface ProviderInfo {
		provider: string;
		configured: boolean;
		models: string[];
	}

	interface RunResult {
		run: number;
		latency: number;
		status: 'ok' | 'error';
		msg?: string;
	}

	interface ModelResult {
		model: string;
		runs: RunResult[];
		avg?: number;
		min?: number;
		max?: number;
		status: 'pending' | 'running' | 'done' | 'error';
		currentRun?: number;
		errorMsg?: string;
	}

	// ── Estado ───────────────────────────────────────────────────────────────────

	let providers     = $state<ProviderInfo[]>([]);
	let activeModels  = $state<string[]>([]);
	let selected      = $state<Set<string>>(new Set());
	let customModel   = $state('');
	let prompt        = $state('Responde solo con "ok".');
	let runs          = $state(3);
	let running       = $state(false);
	let results       = $state<ModelResult[]>([]);
	let loadingModels = $state(true);
	let log           = $state<string[]>([]);

	// ── Carga inicial ────────────────────────────────────────────────────────────

	onMount(async () => {
		try {
			const res = await api.get<{ providers: ProviderInfo[]; active_models: string[] }>('/dev/models');
			providers    = res.providers;
			activeModels = res.active_models;
			// Pre-seleccionar modelos activos configurados
			selected = new Set(res.active_models);
		} catch (e: any) {
			log = [`Error al cargar modelos: ${e.message}`];
		} finally {
			loadingModels = false;
		}
	});

	// ── Helpers ──────────────────────────────────────────────────────────────────

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

	function providerOf(model: string): string {
		return model.split('/')[0] ?? 'unknown';
	}

	function colorOf(model: string): string {
		return PROVIDER_COLORS[providerOf(model)] ?? '#6b7280';
	}

	function latencyBar(ms: number, maxMs: number): number {
		if (maxMs === 0) return 0;
		return Math.min(100, Math.round((ms / maxMs) * 100));
	}

	function maxAvg(): number {
		return Math.max(...results.filter(r => r.avg != null).map(r => r.avg!), 0.001);
	}

	function toggleModel(model: string) {
		const s = new Set(selected);
		if (s.has(model)) s.delete(model); else s.add(model);
		selected = s;
	}

	function addCustomModel() {
		const m = customModel.trim();
		if (!m) return;
		selected = new Set([...selected, m]);
		customModel = '';
	}

	// ── Benchmark ────────────────────────────────────────────────────────────────

	async function runBenchmark() {
		const modelList = [...selected];
		if (!modelList.length) return;

		running = true;
		log     = [];
		results = modelList.map(m => ({
			model: m, runs: [], status: 'pending'
		}));

		const token = getToken();
		let res: Response;
		try {
			res = await fetch(`${BASE_URL}/dev/benchmark`, {
				method:  'POST',
				headers: {
					'Content-Type':  'application/json',
					'Authorization': `Bearer ${token}`,
				},
				body: JSON.stringify({ models: modelList, prompt, runs }),
			});
		} catch (e: any) {
			log = [`Error de red: ${e.message}`];
			running = false;
			return;
		}

		if (!res.ok) {
			log = [`HTTP ${res.status}: ${await res.text()}`];
			running = false;
			return;
		}

		// Consume SSE stream
		const reader  = res.body!.getReader();
		const decoder = new TextDecoder();
		let   buf     = '';

		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buf += decoder.decode(value, { stream: true });
			const lines = buf.split('\n');
			buf = lines.pop() ?? '';

			for (const line of lines) {
				if (!line.startsWith('data: ')) continue;
				try {
					const evt = JSON.parse(line.slice(6));
					handleEvent(evt);
				} catch { /* ignore malformed */ }
			}
		}

		running = false;
	}

	function handleEvent(evt: any) {
		const idx = results.findIndex(r => r.model === evt.model);

		if (evt.type === 'done') {
			// sort by avg ascending
			results = [...results].sort((a, b) => (a.avg ?? 99) - (b.avg ?? 99));
			log = [...log, '✓ Benchmark completo'];
			return;
		}

		if (evt.type === 'error') {
			if (idx >= 0) {
				results[idx] = { ...results[idx], status: 'error', errorMsg: evt.msg };
			}
			log = [...log, `✗ ${evt.model}: ${evt.msg}`];
			return;
		}

		if (evt.type === 'running') {
			if (idx >= 0) {
				results[idx] = { ...results[idx], status: 'running', currentRun: evt.run };
			}
			return;
		}

		if (evt.type === 'run') {
			if (idx < 0) return;
			const runEntry: RunResult = {
				run:     evt.run,
				latency: evt.latency,
				status:  evt.status,
				msg:     evt.msg,
			};
			results[idx] = {
				...results[idx],
				runs: [...results[idx].runs, runEntry],
			};
			const emoji = evt.status === 'ok' ? '→' : '✗';
			log = [...log, `${emoji} ${evt.model} run ${evt.run}: ${evt.latency}s`];
			return;
		}

		if (evt.type === 'summary') {
			if (idx < 0) return;
			results[idx] = {
				...results[idx],
				avg: evt.avg,
				min: evt.min,
				max: evt.max,
				status: 'done',
			};
		}
	}
</script>

<div class="page">
	<!-- ── Cabecera ────────────────────────────────────────────────────────────── -->
	<div class="page-header">
		<div>
			<h1 class="page-title">Panel de Desarrollador</h1>
			<p class="page-sub">Benchmark de latencia LLM — configura y ejecuta desde aquí</p>
		</div>
	</div>

	<div class="layout">
		<!-- ── Panel izquierdo: configuración ──────────────────────────────────── -->
		<div class="config-panel">

			<section class="section">
				<h2 class="section-title">Instrucciones al modelo</h2>
				<textarea
					class="prompt-input"
					bind:value={prompt}
					rows={3}
					placeholder="Escribe el prompt que se enviará a cada modelo…"
					disabled={running}
				></textarea>
			</section>

			<section class="section">
				<h2 class="section-title">Repeticiones por modelo</h2>
				<div class="runs-row">
					{#each [1, 3, 5, 10] as n}
						<button
							class="runs-btn"
							class:active={runs === n}
							onclick={() => runs = n}
							disabled={running}
						>{n}</button>
					{/each}
					<input
						class="runs-custom"
						type="number"
						min="1"
						max="20"
						bind:value={runs}
						disabled={running}
					/>
				</div>
			</section>

			<section class="section">
				<h2 class="section-title">Modelos a probar</h2>

				{#if loadingModels}
					<div class="hint">Cargando…</div>
				{:else}
					<!-- Modelos activos del sistema -->
					{#if activeModels.length}
						<div class="group-label">Activos en el sistema</div>
						{#each activeModels as m}
							<label class="model-check">
								<input type="checkbox" checked={selected.has(m)} onchange={() => toggleModel(m)} disabled={running} />
								<span class="model-badge" style="border-color:{colorOf(m)}33; color:{colorOf(m)}">
									{providerOf(m)}
								</span>
								<span class="model-name">{m.split('/').slice(1).join('/')}</span>
							</label>
						{/each}
					{/if}

					<!-- Sugeridos por proveedor -->
					{#each providers.filter(p => p.configured && p.models.length) as p}
						{@const extras = p.models.filter(m => !activeModels.includes(m))}
						{#if extras.length}
							<div class="group-label" style="margin-top:10px">{p.provider}</div>
							{#each extras as m}
								<label class="model-check">
									<input type="checkbox" checked={selected.has(m)} onchange={() => toggleModel(m)} disabled={running} />
									<span class="model-badge" style="border-color:{colorOf(m)}33; color:{colorOf(m)}">
										{providerOf(m)}
									</span>
									<span class="model-name">{m.split('/').slice(1).join('/')}</span>
								</label>
							{/each}
						{/if}
					{/each}

					<!-- Modelo personalizado -->
					<div class="group-label" style="margin-top:10px">Agregar modelo</div>
					<div class="custom-row">
						<input
							class="custom-input"
							bind:value={customModel}
							placeholder="proveedor/modelo-id"
							disabled={running}
							onkeydown={(e) => e.key === 'Enter' && addCustomModel()}
						/>
						<button class="btn-add" onclick={addCustomModel} disabled={running || !customModel.trim()}>+</button>
					</div>
				{/if}
			</section>

			<button
				class="btn-run"
				onclick={runBenchmark}
				disabled={running || selected.size === 0}
			>
				{running ? 'Ejecutando…' : `Ejecutar benchmark (${selected.size} modelo${selected.size !== 1 ? 's' : ''})`}
			</button>
		</div>

		<!-- ── Panel derecho: resultados ────────────────────────────────────────── -->
		<div class="results-panel">

			{#if results.length === 0}
				<div class="empty-state">
					<span class="empty-icon">⚡</span>
					<p>Los resultados aparecerán aquí al ejecutar el benchmark.</p>
				</div>
			{:else}
				<div class="results-header">
					<h2 class="section-title">Resultados</h2>
					{#if running}
						<span class="badge-running">En curso…</span>
					{/if}
				</div>

				{#each results as r}
					{@const color = colorOf(r.model)}
					<div class="result-card" class:card-done={r.status === 'done'} class:card-err={r.status === 'error'}>
						<div class="card-header">
							<span class="card-badge" style="background:{color}22; color:{color}">{providerOf(r.model)}</span>
							<span class="card-model">{r.model.split('/').slice(1).join('/')}</span>
							{#if r.status === 'running'}
								<span class="card-status running">run {r.currentRun}/{runs}…</span>
							{:else if r.status === 'done' && r.avg != null}
								<span class="card-avg">{r.avg.toFixed(2)}s avg</span>
							{:else if r.status === 'error'}
								<span class="card-status error">error</span>
							{/if}
						</div>

						{#if r.status === 'error' && r.errorMsg}
							<div class="card-error-msg">{r.errorMsg}</div>
						{/if}

						{#if r.avg != null}
							<div class="latency-bar-wrap">
								<div class="latency-bar" style="width:{latencyBar(r.avg, maxAvg())}%; background:{color}"></div>
							</div>
							<div class="card-stats">
								<span>min <b>{r.min?.toFixed(2)}s</b></span>
								<span>avg <b>{r.avg.toFixed(2)}s</b></span>
								<span>max <b>{r.max?.toFixed(2)}s</b></span>
							</div>
						{/if}

						<!-- runs individuales -->
						{#if r.runs.length > 0}
							<div class="runs-dots">
								{#each r.runs as run}
									<span
										class="run-dot"
										class:dot-err={run.status === 'error'}
										title="{run.status === 'ok' ? run.latency + 's' : (run.msg ?? 'error')}"
										style={run.status === 'ok' ? `opacity:${0.4 + 0.6 * (run.latency / (r.max ?? 1))}` : ''}
									>
										{run.status === 'ok' ? run.latency.toFixed(2) : '✗'}
									</span>
								{/each}
							</div>
						{/if}
					</div>
				{/each}
			{/if}

			<!-- Log en tiempo real -->
			{#if log.length > 0}
				<div class="log-box">
					{#each log as line}
						<div class="log-line">{line}</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.page { height: 100%; display: flex; flex-direction: column; }

	.page-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		margin-bottom: 20px;
		flex-shrink: 0;
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

	.layout {
		display: grid;
		grid-template-columns: 300px 1fr;
		gap: 20px;
		flex: 1;
		min-height: 0;
	}

	/* ── Config panel ─────────────────────────────────────────────────────────── */

	.config-panel {
		display: flex;
		flex-direction: column;
		gap: 0;
		overflow-y: auto;
		padding-right: 4px;
	}

	.section {
		margin-bottom: 20px;
	}

	.section-title {
		font-size: 11px;
		font-weight: 600;
		color: var(--color-muted-2);
		text-transform: uppercase;
		letter-spacing: 0.7px;
		margin: 0 0 8px;
	}

	.prompt-input {
		width: 100%;
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-foreground);
		font-size: 13px;
		padding: 9px 11px;
		resize: vertical;
		font-family: inherit;
		box-sizing: border-box;
	}

	.prompt-input:focus {
		outline: none;
		border-color: #4285f4;
	}

	.runs-row {
		display: flex;
		align-items: center;
		gap: 6px;
	}

	.runs-btn {
		padding: 5px 12px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: var(--color-surface-2);
		color: var(--color-muted);
		font-size: 13px;
		cursor: pointer;
	}

	.runs-btn.active {
		background: var(--color-surface-3);
		color: var(--color-foreground);
		font-weight: 500;
	}

	.runs-custom {
		width: 52px;
		padding: 5px 8px;
		border-radius: 6px;
		border: 1px solid var(--color-border);
		background: var(--color-surface-2);
		color: var(--color-foreground);
		font-size: 13px;
		text-align: center;
	}

	.group-label {
		font-size: 10.5px;
		font-weight: 500;
		color: var(--color-muted-2);
		text-transform: uppercase;
		letter-spacing: 0.6px;
		margin-bottom: 5px;
	}

	.model-check {
		display: flex;
		align-items: center;
		gap: 7px;
		padding: 5px 6px;
		border-radius: 6px;
		cursor: pointer;
		font-size: 12.5px;
		user-select: none;
	}

	.model-check:hover {
		background: var(--color-surface-2);
	}

	.model-badge {
		font-size: 10px;
		font-weight: 600;
		padding: 1px 6px;
		border-radius: 4px;
		border: 1px solid;
		text-transform: capitalize;
		flex-shrink: 0;
	}

	.model-name {
		color: var(--color-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.custom-row {
		display: flex;
		gap: 6px;
	}

	.custom-input {
		flex: 1;
		padding: 6px 10px;
		border-radius: 7px;
		border: 1px solid var(--color-border);
		background: var(--color-surface-2);
		color: var(--color-foreground);
		font-size: 12px;
	}

	.btn-add {
		padding: 6px 12px;
		border-radius: 7px;
		border: 1px solid var(--color-border);
		background: var(--color-surface-2);
		color: var(--color-foreground);
		font-size: 16px;
		cursor: pointer;
	}

	.btn-run {
		padding: 10px 18px;
		border-radius: 9px;
		border: none;
		background: #4285f4;
		color: #fff;
		font-size: 13.5px;
		font-weight: 500;
		cursor: pointer;
		width: 100%;
		margin-top: 4px;
	}

	.btn-run:hover:not(:disabled) {
		background: #3b78e7;
	}

	.btn-run:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.hint {
		font-size: 12px;
		color: var(--color-muted-2);
	}

	/* ── Results panel ────────────────────────────────────────────────────────── */

	.results-panel {
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.results-header {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-shrink: 0;
	}

	.badge-running {
		font-size: 11px;
		background: #f97316;
		color: #fff;
		padding: 2px 8px;
		border-radius: 20px;
		font-weight: 500;
		animation: pulse 1.4s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50%       { opacity: 0.6; }
	}

	.empty-state {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		color: var(--color-muted-2);
		font-size: 13.5px;
		gap: 10px;
		padding: 60px 20px;
	}

	.empty-icon {
		font-size: 36px;
	}

	.result-card {
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 10px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		transition: border-color 0.2s;
	}

	.result-card.card-done {
		border-color: var(--color-border);
	}

	.result-card.card-err {
		border-color: rgba(239, 68, 68, 0.3);
	}

	.card-header {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.card-badge {
		font-size: 10px;
		font-weight: 600;
		padding: 2px 7px;
		border-radius: 5px;
		text-transform: capitalize;
		flex-shrink: 0;
	}

	.card-model {
		font-family: monospace;
		font-size: 12.5px;
		color: var(--color-muted);
		flex: 1;
	}

	.card-avg {
		font-size: 13px;
		font-weight: 600;
		color: var(--color-foreground);
	}

	.card-status {
		font-size: 11.5px;
		font-weight: 500;
	}

	.card-status.running { color: #f97316; }
	.card-status.error   { color: #f87171; }

	.card-error-msg {
		font-size: 12px;
		color: #f87171;
		background: rgba(239, 68, 68, 0.08);
		border-radius: 6px;
		padding: 6px 10px;
	}

	.latency-bar-wrap {
		height: 6px;
		background: var(--color-surface-3);
		border-radius: 3px;
		overflow: hidden;
	}

	.latency-bar {
		height: 100%;
		border-radius: 3px;
		transition: width 0.5s ease;
		min-width: 4px;
	}

	.card-stats {
		display: flex;
		gap: 16px;
		font-size: 12px;
		color: var(--color-muted);
	}

	.card-stats b {
		color: var(--color-foreground);
	}

	.runs-dots {
		display: flex;
		gap: 5px;
		flex-wrap: wrap;
	}

	.run-dot {
		font-size: 11px;
		padding: 2px 7px;
		border-radius: 4px;
		background: var(--color-surface-3);
		color: var(--color-muted);
		font-family: monospace;
	}

	.run-dot.dot-err {
		background: rgba(239, 68, 68, 0.15);
		color: #f87171;
	}

	.log-box {
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 8px;
		padding: 12px 14px;
		font-family: monospace;
		font-size: 12px;
		color: #8b949e;
		max-height: 160px;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 2px;
		margin-top: 4px;
	}

	.log-line {
		line-height: 1.5;
	}
</style>
