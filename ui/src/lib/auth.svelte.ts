import { browser } from '$app/environment';
import { api, setToken, clearToken, loadToken, isAuthenticated } from './api/client';

export interface AuthUser {
	username: string;
	role: string;
}

let _user = $state<AuthUser | null>(null);

export function getUser(): AuthUser | null {
	return _user;
}

export function initAuth() {
	if (!browser) return;
	loadToken();
	if (isAuthenticated()) {
		const raw = localStorage.getItem('auth_user');
		if (raw) _user = JSON.parse(raw);
	}
}

export async function login(username: string, password: string): Promise<void> {
	const res = await api.post<{ access_token: string; role: string; token_type: string }>(
		'/auth/login',
		{ username, password }
	);
	setToken(res.access_token);
	_user = { username, role: res.role };
	if (browser) localStorage.setItem('auth_user', JSON.stringify(_user));
}

export function logout() {
	clearToken();
	_user = null;
	if (browser) {
		localStorage.removeItem('auth_user');
		window.location.href = '/login';
	}
}

export { isAuthenticated };
