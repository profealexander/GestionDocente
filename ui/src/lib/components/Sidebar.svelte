<script lang="ts">
	import { page } from '$app/state';
	import { logout, getUser } from '$lib/auth.svelte';

	const navItems = [
		{ href: '/agente',       icon: '🤖', label: 'Agente IA'    },
		{ href: '/jornada',      icon: '📅', label: 'Jornada'      },
		{ href: '/asistencia',   icon: '✅', label: 'Asistencia'   },
		{ href: '/tareas',       icon: '📝', label: 'Tareas'       },
		{ href: '/cuotas',       icon: '💰', label: 'Cuotas'       },
		{ href: '/cumplimiento', icon: '📊', label: 'Cumplimiento' },
		{ href: '/notas',        icon: '🎓', label: 'Notas'        },
		{ href: '/reportes',     icon: '👁', label: 'Reportes'     },
	];

	const adminItems = [
		{ href: '/admin/estudiantes', icon: '👥', label: 'Estudiantes'  },
		{ href: '/admin/cursos',      icon: '🏫', label: 'Cursos'       },
		{ href: '/admin/docentes',    icon: '👨‍🏫', label: 'Docentes'     },
		{ href: '/admin/api',         icon: '🔌', label: 'API / Modelos' },
		{ href: '/admin/dev',         icon: '⚡', label: 'Desarrollador'  },
	];
</script>

<aside class="sidebar">
	<!-- Logo / Brand -->
	<div class="sidebar-header">
		<div class="brand">
			<span class="brand-icon">🏫</span>
			<span class="brand-name">SchoolAI</span>
		</div>
	</div>

	<!-- Main navigation -->
	<nav class="sidebar-nav">
		<ul>
			{#each navItems as item}
				<li>
					<a
						href={item.href}
						class="nav-item"
						class:active={page.url.pathname === item.href}
					>
						<span class="nav-icon">{item.icon}</span>
						<span class="nav-label">{item.label}</span>
					</a>
				</li>
			{/each}
		</ul>

		<!-- Admin section -->
		<div class="nav-section-label">Administración</div>
		<ul>
			{#each adminItems as item}
				<li>
					<a
						href={item.href}
						class="nav-item"
						class:active={page.url.pathname.startsWith(item.href)}
					>
						<span class="nav-icon">{item.icon}</span>
						<span class="nav-label">{item.label}</span>
					</a>
				</li>
			{/each}
		</ul>
	</nav>

	<!-- Footer -->
	<div class="sidebar-footer">
		{#if getUser()}
			<div class="user-info">
				<span class="nav-icon">👤</span>
				<span class="user-name">{getUser()?.username}</span>
			</div>
		{/if}
		<button class="nav-item logout-btn" onclick={logout}>
			<span class="nav-icon">🚪</span>
			<span class="nav-label">Cerrar sesión</span>
		</button>
	</div>
</aside>

<style>
	.sidebar {
		width: var(--sidebar-width);
		min-width: var(--sidebar-width);
		height: 100vh;
		background-color: var(--sidebar-bg);
		border-right: 1px solid var(--color-border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.sidebar-header {
		padding: 20px 16px 12px;
		border-bottom: 1px solid var(--color-border-muted);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.brand-icon {
		font-size: 20px;
	}

	.brand-name {
		font-size: 16px;
		font-weight: 600;
		color: var(--color-foreground);
		letter-spacing: -0.3px;
	}

	.sidebar-nav {
		flex: 1;
		overflow-y: auto;
		padding: 8px 8px;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.nav-section-label {
		font-size: 11px;
		font-weight: 500;
		color: var(--color-muted-2);
		text-transform: uppercase;
		letter-spacing: 0.8px;
		padding: 16px 12px 6px;
	}

	.nav-item {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 12px;
		border-radius: 8px;
		color: var(--color-muted);
		text-decoration: none;
		font-size: 13.5px;
		font-weight: 400;
		transition: background 0.15s, color 0.15s;
		cursor: pointer;
	}

	.nav-item:hover {
		background-color: var(--color-surface-2);
		color: var(--color-foreground);
	}

	.nav-item.active {
		background-color: var(--color-surface-3);
		color: var(--color-foreground);
		font-weight: 500;
	}

	.nav-icon {
		font-size: 15px;
		width: 20px;
		text-align: center;
		flex-shrink: 0;
	}

	.sidebar-footer {
		padding: 8px;
		border-top: 1px solid var(--color-border-muted);
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 6px 12px;
		font-size: 12px;
		color: var(--color-muted-2);
	}

	.user-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.logout-btn {
		background: none;
		border: none;
		width: 100%;
		text-align: left;
		color: var(--color-muted);
	}

	.logout-btn:hover {
		background-color: rgba(239, 68, 68, 0.1);
		color: #f87171;
	}
</style>
