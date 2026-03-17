<script lang="ts">
	import { goto } from '$app/navigation';
</script>

<div class="home">
	<div class="welcome">
		<h1>Bienvenido a SchoolAI</h1>
		<p>Selecciona una opción del menú para comenzar.</p>
	</div>

	<div class="quick-actions">
		<button onclick={() => goto('/jornada')} class="action-card">
			<span class="action-icon">📅</span>
			<span class="action-label">Iniciar Jornada</span>
		</button>
		<button onclick={() => goto('/asistencia')} class="action-card">
			<span class="action-icon">✅</span>
			<span class="action-label">Registrar Asistencia</span>
		</button>
		<button onclick={() => goto('/tareas')} class="action-card">
			<span class="action-icon">📝</span>
			<span class="action-label">Registrar Tarea</span>
		</button>
		<button onclick={() => goto('/reportes')} class="action-card">
			<span class="action-icon">👁</span>
			<span class="action-label">Ver Reportes</span>
		</button>
	</div>
</div>

<style>
	.home {
		max-width: 800px;
		margin: 0 auto;
		padding-top: 48px;
	}

	.welcome {
		margin-bottom: 40px;
	}

	h1 {
		font-size: 24px;
		font-weight: 600;
		color: var(--color-foreground);
		margin: 0 0 8px;
	}

	p {
		color: var(--color-muted);
		margin: 0;
		font-size: 14px;
	}

	.quick-actions {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
		gap: 12px;
	}

	.action-card {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		padding: 24px 16px;
		background-color: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 12px;
		cursor: pointer;
		transition: background 0.15s, border-color 0.15s;
		text-align: center;
	}

	.action-card:hover {
		background-color: var(--color-surface-2);
		border-color: var(--color-surface-3);
	}

	.action-icon {
		font-size: 28px;
	}

	.action-label {
		font-size: 13px;
		font-weight: 500;
		color: var(--color-foreground);
	}
</style>
