<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import { initAuth, isAuthenticated } from '$lib/auth.svelte';
	import { page } from '$app/state';
	import { browser } from '$app/environment';

	let { children } = $props();

	initAuth();

	const isLoginPage = $derived(page.url.pathname === '/login');

	$effect(() => {
		if (browser && !isLoginPage && !isAuthenticated()) {
			window.location.href = '/login';
		}
	});
</script>

<svelte:head>
	<title>SchoolAI</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
</svelte:head>

{#if isLoginPage}
	{@render children()}
{:else}
	<div class="app-shell">
		<Sidebar />
		<main class="main-content">
			{@render children()}
		</main>
	</div>
{/if}

<style>
	.app-shell {
		display: flex;
		height: 100vh;
		overflow: hidden;
	}

	.main-content {
		flex: 1;
		overflow-y: auto;
		padding: 24px 32px;
	}
</style>
