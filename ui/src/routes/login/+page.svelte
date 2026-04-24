<script lang="ts">
	import { login } from '$lib/auth.svelte';

	let username = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		loading = true;
		try {
			await login(username, password);
			window.location.href = '/';
		} catch (err: unknown) {
			error = err instanceof Error ? err.message : 'Error al iniciar sesión';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Iniciar sesión — SchoolAI</title>
</svelte:head>

<div class="login-wrapper">
	<div class="login-card">
		<div class="login-logo">
			<span class="logo-icon">🏫</span>
			<h1>SchoolAI</h1>
			<p>Panel del docente</p>
		</div>

		<form onsubmit={handleSubmit} class="login-form">
			<div class="field">
				<label for="username">Usuario</label>
				<input
					id="username"
					type="text"
					bind:value={username}
					placeholder="Tu nombre de usuario"
					autocomplete="username"
					required
					disabled={loading}
				/>
			</div>

			<div class="field">
				<label for="password">Contraseña</label>
				<input
					id="password"
					type="password"
					bind:value={password}
					placeholder="••••••••"
					autocomplete="current-password"
					required
					disabled={loading}
				/>
			</div>

			{#if error}
				<p class="error-msg">{error}</p>
			{/if}

			<button type="submit" class="btn-login" disabled={loading}>
				{loading ? 'Ingresando…' : 'Iniciar sesión'}
			</button>
		</form>
	</div>
</div>

<style>
	.login-wrapper {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--color-background);
		padding: 24px;
	}

	.login-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 16px;
		padding: 40px 36px;
		width: 100%;
		max-width: 380px;
	}

	.login-logo {
		text-align: center;
		margin-bottom: 32px;
	}

	.logo-icon {
		font-size: 2.5rem;
		display: block;
		margin-bottom: 8px;
	}

	.login-logo h1 {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--color-foreground);
		margin: 0 0 4px;
	}

	.login-logo p {
		color: var(--color-muted);
		font-size: 0.875rem;
		margin: 0;
	}

	.login-form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--color-muted);
	}

	input {
		background: var(--color-surface-2);
		border: 1px solid var(--color-border);
		border-radius: 8px;
		color: var(--color-foreground);
		font-size: 0.9375rem;
		padding: 10px 14px;
		outline: none;
		transition: border-color 0.15s;
	}

	input:focus {
		border-color: var(--color-primary);
	}

	input::placeholder {
		color: var(--color-muted-2);
	}

	input:disabled {
		opacity: 0.6;
	}

	.error-msg {
		background: var(--color-danger-muted);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: 8px;
		color: #f87171;
		font-size: 0.8125rem;
		padding: 10px 14px;
		margin: 0;
	}

	.btn-login {
		background: var(--color-primary);
		border: none;
		border-radius: 8px;
		color: #fff;
		cursor: pointer;
		font-size: 0.9375rem;
		font-weight: 600;
		margin-top: 4px;
		padding: 12px;
		transition: opacity 0.15s;
	}

	.btn-login:hover:not(:disabled) {
		background: var(--color-primary-hover);
	}

	.btn-login:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
