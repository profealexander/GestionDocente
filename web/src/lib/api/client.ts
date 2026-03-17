const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

let _token: string | null = null;

export function setToken(token: string) {
	_token = token;
	localStorage.setItem('token', token);
}

export function loadToken() {
	_token = localStorage.getItem('token');
}

export function clearToken() {
	_token = null;
	localStorage.removeItem('token');
}

export function isAuthenticated(): boolean {
	return _token !== null;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(options.headers as Record<string, string>),
	};
	if (_token) headers['Authorization'] = `Bearer ${_token}`;

	const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

	if (res.status === 401) {
		clearToken();
		window.location.href = '/login';
		throw new Error('Unauthorized');
	}

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: res.statusText }));
		throw new Error(err.detail ?? 'Error desconocido');
	}

	return res.json();
}

export const api = {
	get:    <T>(path: string)                     => request<T>(path),
	post:   <T>(path: string, body: unknown)      => request<T>(path, { method: 'POST',  body: JSON.stringify(body) }),
	put:    <T>(path: string, body: unknown)      => request<T>(path, { method: 'PUT',   body: JSON.stringify(body) }),
	delete: <T>(path: string)                     => request<T>(path, { method: 'DELETE' }),
};
