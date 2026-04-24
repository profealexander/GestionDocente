const WS_URL = import.meta.env.VITE_GATEWAY_WS ?? 'ws://localhost:8001';

export interface GatewayMessage {
	text: string;
	domain: string;
	intent: string;
	session_id: string;
}

export type MessageHandler = (msg: GatewayMessage) => void;
export type ErrorHandler = (err: Event) => void;

export class GatewaySocket {
	private ws: WebSocket | null = null;
	private userId: string;
	private onMessage: MessageHandler;
	private onError: ErrorHandler;
	private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

	constructor(userId: string, onMessage: MessageHandler, onError: ErrorHandler) {
		this.userId = userId;
		this.onMessage = onMessage;
		this.onError = onError;
	}

	connect(): void {
		if (this.ws?.readyState === WebSocket.OPEN) return;

		this.ws = new WebSocket(`${WS_URL}/gateway/ws/${this.userId}`);

		this.ws.onmessage = (e) => {
			try {
				const data = JSON.parse(e.data) as GatewayMessage;
				this.onMessage(data);
			} catch {
				// ignore malformed frames
			}
		};

		this.ws.onerror = (e) => this.onError(e);

		this.ws.onclose = () => {
			// Auto-reconnect after 3s
			this.reconnectTimer = setTimeout(() => this.connect(), 3000);
		};
	}

	send(text: string): void {
		if (this.ws?.readyState === WebSocket.OPEN) {
			this.ws.send(JSON.stringify({ text }));
		}
	}

	disconnect(): void {
		if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
		this.ws?.close();
		this.ws = null;
	}

	get connected(): boolean {
		return this.ws?.readyState === WebSocket.OPEN;
	}
}
