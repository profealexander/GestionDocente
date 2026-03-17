import { api } from './client';

export interface Grade {
	id: number;
	name: string;
	abbrev?: string;
}

export interface Student {
	id: number;
	full_name: string;
	short_name?: string;
}

export const gradesApi = {
	list: ()                        => api.get<Grade[]>('/grades'),
	students: (gradeId: number)     => api.get<Student[]>(`/grades/${gradeId}/students`),
};
