<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { GatewaySocket } from '$lib/api/gateway';
	import { loadToken, getToken } from '$lib/api/client';

	interface ChatMessage {
		role: 'user' | 'agent';
		text: string;
		domain?: string;
		intent?: string;
		ts: Date;
	}

	let messages: ChatMessage[] = $state([]);
	let input = $state('');
	let loading = $state(false);
	let connected = $state(false);
	let socket: GatewaySocket | null = null;
	let messagesEl: HTMLElement;

	const DOMAIN_LABEL: Record<string, string> = {
		attendance: 'Asistencia',
		homework: 'Tareas',
		reports: 'Reportes',
		web_search: 'Búsqueda',
		general: 'General',
	};

	onMount(() => {
		loadToken();
		const userId = getToken() ? '5494482378' : 'guest';

		socket = new GatewaySocket(
			userId,
			(msg) => {
				messages = [
					...messages,
					{ role: 'agent', text: msg.text, domain: msg.domain, intent: msg.intent, ts: new Date() },
				];
				loading = false;
				connected = true;
				scrollToBottom();
			},
			() => {
				connected = false;
			}
		);
		socket.connect();
		connected = true;
	});

	onDestroy(() => socket?.disconnect());

	function scrollToBottom() {
		setTimeout(() => messagesEl?.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' }), 50);
	}

	function send() {
		const text = input.trim();
		if (!text || !socket?.connected) return;

		messages = [...messages, { role: 'user', text, ts: new Date() }];
		socket.send(text);
		input = '';
		loading = true;
		scrollToBottom();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}
</script>

<div class="page">
	<div class="header">
		<h1>Agente IA</h1>
		<span class="status" class:online={connected}>{connected ? 'Conectado' : 'Reconectando...'}</span>
	</div>

	<div class="messages" bind:this={messagesEl}>
		{#if messages.length === 0}
			<div class="empty">
				<p>Escribe un mensaje para comenzar.</p>
				<div class="suggestions">
					{#each ['Faltas de hoy 3BT', 'Tareas pendientes 2EGB', '¿Cuánto debe Ana?', 'Reporte asistencia 1BT'] as s}
						<button onclick={() => { input = s; send(); }}>{s}</button>
					{/each}
				</div>
			</div>
		{/if}

		{#each messages as msg}
			<div class="message {msg.role}">
				<div class="bubble">
					<p>{msg.text}</p>
					{#if msg.domain}
						<span class="tag">{DOMAIN_LABEL[msg.domain] ?? msg.domain}</span>
					{/if}
				</div>
				<span class="time">{msg.ts.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}</span>
			</div>
		{/each}

		{#if loading}
			<div class="message agent">
				<div class="bubble typing"><span></span><span></span><span></span></div>
			</div>
		{/if}
	</div>

	<div class="composer">
		<textarea
			bind:value={input}
			onkeydown={handleKeydown}
			placeholder="Escribe un mensaje..."
			rows="2"
			disabled={!connected}
		></textarea>
		<button onclick={send} disabled={!input.trim() || !connected || loading}>
			Enviar
		</button>
	</div>
</div>

<style>
	.page {
		display: flex;
		flex-direction: column;
		height: calc(100vh - 64px);
		max-width: 720px;
		margin: 0 auto;
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 0 12px;
		border-bottom: 1px solid var(--color-border);
	}

	h1 { font-size: 18px; font-weight: 600; margin: 0; }

	.status {
		font-size: 12px;
		padding: 3px 10px;
		border-radius: 99px;
		background: var(--color-surface-2);
		color: var(--color-muted);
	}
	.status.online { background: #d1fae5; color: #065f46; }

	.messages {
		flex: 1;
		overflow-y: auto;
		padding: 16px 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.empty {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 16px;
		color: var(--color-muted);
		font-size: 14px;
	}

	.suggestions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		justify-content: center;
	}

	.suggestions button {
		padding: 6px 12px;
		border: 1px solid var(--color-border);
		border-radius: 99px;
		background: var(--color-surface);
		font-size: 13px;
		cursor: pointer;
		color: var(--color-foreground);
	}
	.suggestions button:hover { background: var(--color-surface-2); }

	.message {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.message.user { align-items: flex-end; }
	.message.agent { align-items: flex-start; }

	.bubble {
		max-width: 80%;
		padding: 10px 14px;
		border-radius: 16px;
		font-size: 14px;
		line-height: 1.5;
	}
	.bubble p { margin: 0; white-space: pre-wrap; }

	.message.user .bubble {
		background: var(--color-primary, #2563eb);
		color: #fff;
		border-bottom-right-radius: 4px;
	}
	.message.agent .bubble {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-bottom-left-radius: 4px;
	}

	.tag {
		display: inline-block;
		margin-top: 6px;
		font-size: 11px;
		padding: 2px 7px;
		border-radius: 99px;
		background: var(--color-surface-2);
		color: var(--color-muted);
	}

	.time { font-size: 11px; color: var(--color-muted); padding: 0 4px; }

	/* Typing indicator */
	.typing {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 12px 16px;
	}
	.typing span {
		width: 7px; height: 7px;
		background: var(--color-muted);
		border-radius: 50%;
		animation: bounce 1.2s infinite;
	}
	.typing span:nth-child(2) { animation-delay: 0.2s; }
	.typing span:nth-child(3) { animation-delay: 0.4s; }
	@keyframes bounce {
		0%, 80%, 100% { transform: translateY(0); }
		40% { transform: translateY(-6px); }
	}

	.composer {
		display: flex;
		gap: 8px;
		padding: 12px 0 16px;
		border-top: 1px solid var(--color-border);
	}

	textarea {
		flex: 1;
		padding: 10px 14px;
		border: 1px solid var(--color-border);
		border-radius: 10px;
		resize: none;
		font-size: 14px;
		background: var(--color-surface);
		color: var(--color-foreground);
		font-family: inherit;
	}
	textarea:focus { outline: none; border-color: var(--color-primary, #2563eb); }

	.composer button {
		padding: 0 20px;
		background: var(--color-primary, #2563eb);
		color: #fff;
		border: none;
		border-radius: 10px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		white-space: nowrap;
	}
	.composer button:disabled { opacity: 0.45; cursor: not-allowed; }
	.composer button:not(:disabled):hover { filter: brightness(1.1); }
</style>
