import { requestFormData } from './client';

export interface SortEntry {
	id: string;
	item: { name: string; quantity: number; description: string | null; tagIds: string[] | null };
	confidence: number;
	reason: 'matched' | 'low_confidence' | 'no_fit' | 'no_evidence';
}
export interface SortResult {
	groups: { location_id: string | null; name: string; items: SortEntry[] }[];
	proposed_locations: { name: string; description: string; item_ids: string[] }[];
	proposal_error: string | null;
	box: {
		recommendation: 'keep_together' | 'disperse' | 'needs_home' | 'empty';
		dominant_location_id: string | null;
		dominant_share: number;
		assigned_share: number;
	} | null;
}
export function sortPile(
	files: File[],
	mysteryBox: boolean,
	signal: AbortSignal
): Promise<SortResult> {
	const data = new FormData();
	for (const file of files) data.append('images', file);
	data.append('mystery_box', String(mysteryBox));
	return requestFormData('/sort', data, { signal, timeout: 0 });
}
