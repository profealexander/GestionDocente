import { api } from './client';
import { browser } from '$app/environment';

export interface Actividad {
	id: number;
	nombre: string;
	monto: number;
	descripcion: string | null;
	is_active: boolean;
	created_at: string;
}

export interface PagoOut {
	id: number;
	monto: number;
	paid_at: string;
	notas: string | null;
}

export interface Participante {
	id: number;
	student_id: number;
	student_name: string;
	total_pagado: number;
	is_complete: boolean;
	pagos: PagoOut[];
}

export interface ActividadDetalle extends Actividad {
	total_recaudado: number;
	total_completos: number;
	total_pendientes: number;
	participantes: Participante[];
}

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const cuotasApi = {
	list: (onlyActive = true) =>
		api.get<Actividad[]>(`/actividades/?only_active=${onlyActive}`),

	create: (data: { nombre: string; monto: number; descripcion?: string }) =>
		api.post<Actividad>('/actividades/', data),

	get: (id: number) =>
		api.get<ActividadDetalle>(`/actividades/${id}/`),

	addGrade: (actividadId: number, gradeId: number) =>
		api.post<{ added: number; total_in_grade: number }>(
			`/actividades/${actividadId}/participantes/`,
			{ grade_id: gradeId }
		),

	registerPago: (
		actividadId: number,
		data: { student_id: number; monto: number; notas?: string }
	) => api.post(`/actividades/${actividadId}/pagos/`, data),

	/** Descarga el Excel como Blob y dispara la descarga en el browser */
	exportExcel: async (actividadId: number, nombre: string): Promise<void> => {
		if (!browser) return;
		const token = localStorage.getItem('token');
		const res = await fetch(`${BASE_URL}/actividades/${actividadId}/export/`, {
			headers: token ? { Authorization: `Bearer ${token}` } : {},
		});
		if (!res.ok) throw new Error('Error al exportar');
		const blob = await res.blob();
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `cuotas_${nombre.toLowerCase().replace(/\s+/g, '_')}.xlsx`;
		a.click();
		URL.revokeObjectURL(url);
	},
};
