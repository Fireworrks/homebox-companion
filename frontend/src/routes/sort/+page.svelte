<script lang="ts">
	import { onMount } from 'svelte';
	import { sortWorkflow as workflow } from '$lib/workflows/sort.svelte';
	import { applyRouteGuard } from '$lib/utils/routeGuard';
	import { getInitPromise } from '$lib/services/tokenRefresh';
	import Button from '$lib/components/Button.svelte';

	onMount(async () => {
		await getInitPromise();
		applyRouteGuard({ auth: true });
	});
	const box = $derived(workflow.result?.box);
	const dominant = $derived(
		workflow.result?.groups.find((group) => group.location_id === box?.dominant_location_id)?.name
	);
</script>

<svelte:head><title>Sort Mode - Homebox Companion</title></svelte:head>

<div class="mx-auto max-w-3xl space-y-6 p-4">
	<h1 class="text-h1 font-semibold">Sort Mode</h1>
	<p class="text-body text-neutral-300">
		Photograph a pile. Put it away one destination at a time, based on what you already store there.
	</p>
	<div class="space-y-4 rounded-xl bg-neutral-900 p-4">
		<label class="block space-y-2 text-body-sm">
			<span>Photos of this pile or box, including different angles</span>
			<input
				type="file"
				accept="image/*"
				multiple
				disabled={workflow.busy}
				class="block min-h-touch w-full"
				onchange={(event) => workflow.setFiles(Array.from(event.currentTarget.files ?? []))}
			/>
		</label>
		<p class="text-caption text-neutral-300">{workflow.files.length} photo(s) selected</p>
		<label class="flex min-h-touch items-center gap-3 text-body-sm">
			<input
				type="checkbox"
				checked={workflow.mysteryBox}
				disabled={workflow.busy}
				onchange={(event) => workflow.setMysteryBox(event.currentTarget.checked)}
			/>
			This is a mystery box. Should its contents stay together?
		</label>
		<Button disabled={workflow.busy || !workflow.files.length} onclick={() => workflow.analyze()}
			>{workflow.busy ? 'Identifying items and finding homes...' : 'Sort this pile'}</Button
		>
		{#if workflow.busy}<Button variant="secondary" onclick={() => workflow.reset()}>Cancel</Button
			>{/if}
	</div>
	{#if workflow.error}<p role="alert" class="text-body-sm text-error-500">{workflow.error}</p>{/if}
	{#if workflow.result}
		{#if box}
			<div class="rounded-xl bg-neutral-900 p-4 text-body-sm">
				{#if box.recommendation === 'keep_together'}
					<p>
						Keep the main group together at {dominant}. {Math.round(box.dominant_share * 100)}% of
						the contents belong there. Put the exceptions in their listed destinations.
					</p>
				{:else if box.recommendation === 'disperse'}
					<p>
						Disperse this box. The largest destination holds {Math.round(box.dominant_share * 100)}%
						of its contents.
					</p>
				{:else if box.recommendation === 'needs_home'}
					<p>This box needs a home. None of its contents have a confident destination yet.</p>
				{:else}<p>
						No items were identified. Try a clearer photo with the contents spread out.
					</p>{/if}
			</div>
		{/if}
		<p class="text-body-sm text-neutral-300">
			{workflow.completed.length} of {workflow.result.groups.reduce(
				(sum, group) => sum + group.items.length,
				0
			)} entries put away. Tick each entry when done.
		</p>
		{#each workflow.result.groups as group (group.location_id)}
			<section class="space-y-3 rounded-xl bg-neutral-900 p-4">
				<h2 class="text-h2 font-semibold">{group.name}</h2>
				{#each group.items as entry (entry.id)}
					<label class="flex min-h-touch items-start gap-3 rounded-lg bg-neutral-800 p-3">
						<input
							type="checkbox"
							class="mt-1"
							checked={workflow.completed.includes(entry.id)}
							onchange={() => workflow.toggle(entry.id)}
						/>
						<span class="space-y-1">
							<span
								class="block text-body-sm"
								class:line-through={workflow.completed.includes(entry.id)}
								>{entry.item.quantity} × {entry.item.name}</span
							>
							{#if entry.item.description}<span class="block text-caption text-neutral-300"
									>{entry.item.description}</span
								>{/if}
							<span class="block text-caption text-neutral-300">
								{#if entry.reason === 'no_evidence'}No existing contents to match against
								{:else if entry.reason === 'low_confidence'}Uncertain destination, {Math.round(
										entry.confidence * 100
									)}% confidence
								{:else if entry.reason === 'no_fit'}No suitable destination, {Math.round(
										entry.confidence * 100
									)}% confidence
								{:else}{Math.round(entry.confidence * 100)}% confidence{/if}
							</span>
						</span>
					</label>
				{/each}
			</section>
		{/each}
		{#if !workflow.result.groups.length}<p class="text-body-sm">
				No items were identified. Try spreading the pile out.
			</p>{/if}
		{#if workflow.result.proposal_error}<p role="alert" class="text-body-sm text-warning-500">
				{workflow.result.proposal_error}
			</p>{/if}
		{#if workflow.result.proposed_locations.length}
			<section class="space-y-3">
				<h2 class="text-h2 font-semibold">Suggested new homes</h2>
				<p class="text-body-sm text-neutral-300">
					Suggestions for the whole unplaced pile. These locations have not been created.
				</p>
				{#each workflow.result.proposed_locations as proposal}
					<div class="rounded-xl bg-neutral-900 p-4">
						<h3 class="text-body font-semibold">{proposal.name}</h3>
						<p class="text-body-sm text-neutral-300">{proposal.description}</p>
						<ul class="mt-2 list-inside list-disc text-body-sm">
							{#each workflow.result.groups
								.flatMap((group) => group.items)
								.filter((entry) => proposal.item_ids.includes(entry.id)) as entry (entry.id)}
								<li>{entry.item.quantity} × {entry.item.name}</li>
							{/each}
						</ul>
					</div>
				{/each}
			</section>
		{/if}
	{/if}
</div>
