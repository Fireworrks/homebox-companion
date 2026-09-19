import { sortPile, type SortResult } from '$lib/api/sort';

class SortWorkflow {
	files = $state<File[]>([]);
	mysteryBox = $state(false);
	result = $state<SortResult | null>(null);
	busy = $state(false);
	error = $state('');
	completed = $state<string[]>([]);
	private controller: AbortController | null = null;

	setFiles(files: File[]) {
		this.files = files;
		this.result = null;
		this.completed = [];
	}
	setMysteryBox(value: boolean) {
		this.mysteryBox = value;
		this.result = null;
	}
	toggle(id: string) {
		this.completed = this.completed.includes(id)
			? this.completed.filter((key) => key !== id)
			: [...this.completed, id];
	}
	reset() {
		this.controller?.abort();
		this.controller = null;
		this.files = [];
		this.result = null;
		this.completed = [];
		this.error = '';
		this.busy = false;
	}
	async analyze() {
		if (this.busy || !this.files.length) return;
		const controller = new AbortController();
		this.controller = controller;
		this.busy = true;
		this.error = '';
		this.result = null;
		this.completed = [];
		try {
			const result = await sortPile(this.files, this.mysteryBox, controller.signal);
			if (this.controller === controller) this.result = result;
		} catch (error) {
			if (this.controller === controller)
				this.error = error instanceof Error ? error.message : 'Sorting failed. Please retry.';
		} finally {
			if (this.controller === controller) {
				this.busy = false;
				this.controller = null;
			}
		}
	}
}
export const sortWorkflow = new SortWorkflow();
