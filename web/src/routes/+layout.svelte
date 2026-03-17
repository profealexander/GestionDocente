<script lang="ts">
	import '../app.css';
	import Sidebar from '$lib/components/Sidebar.svelte';

	let { children } = $props();
</script>

<svelte:head>
	<title>SchoolAI</title>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
</svelte:head>

<div class="app-shell">
	<Sidebar />
	<main class="main-content">
		{@render children()}
	</main>
</div>

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
