import { api } from './client';

export type AttendanceStatus = 'absent' | 'late' | 'justified' | 'present';

export interface AttendanceRecord {
	student_id: number;
	status: AttendanceStatus;
}

export interface AttendanceSavePayload {
	grade_id: number;
	date: string;        // YYYY-MM-DD
	records: AttendanceRecord[];
}

export const attendanceApi = {
	save: (payload: AttendanceSavePayload) => api.post('/attendance', payload),
	byGrade: (gradeId: number, date: string) =>
		api.get<AttendanceRecord[]>(`/attendance?grade_id=${gradeId}&date=${date}`),
};
