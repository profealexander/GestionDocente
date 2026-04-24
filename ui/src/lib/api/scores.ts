import { api } from './client';

export interface Subject {
	id: number;
	name: string;
	area: string;
	sublevel: string;
}

export interface StudentScoreRow {
	id: number;
	name: string;
	scores: Record<string, number | null>;
}

export interface ScoreMatrix {
	grade_id: number;
	subject_id: number;
	trimester_num: number;
	columns: string[];
	students: StudentScoreRow[];
}

export interface ScoreUpsertRow {
	student_id: number;
	subject_id: number;
	grade_id: number;
	trimester_num: number;
	column_label: string;
	score: number;
}

export const subjectsApi = {
	list: () => api.get<Subject[]>('/subjects/'),
};

export const scoresApi = {
	matrix: (gradeId: number, subjectId: number, trimester: number) =>
		api.get<ScoreMatrix>(
			`/scores?grade_id=${gradeId}&subject_id=${subjectId}&trimester=${trimester}`,
		),

	bulkUpsert: (rows: ScoreUpsertRow[]) =>
		api.put<{ upserted: number }>('/scores/bulk', rows),

	deleteColumn: (gradeId: number, subjectId: number, trimester: number, column: string) =>
		api.delete<{ deleted: number }>(
			`/scores/column?grade_id=${gradeId}&subject_id=${subjectId}&trimester=${trimester}&column=${encodeURIComponent(column)}`,
		),
};
