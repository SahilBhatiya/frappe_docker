<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Input from "@/components/ui/input/Input.vue";
import { toast } from "@/composables/useToast";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { call } from "frappe-ui";
import { Loader2, Mail } from "lucide-vue-next";
import { ref } from "vue";

const props = defineProps<{
	invoiceName: string;
	defaultEmail?: string;
}>();

const emit = defineEmits<{
	close: [];
}>();

const email = ref(props.defaultEmail || "");
const message = ref("");
const sending = ref(false);

async function sendEmail() {
	if (!email.value.trim()) {
		toast.error(__("Please enter an email address"));
		return;
	}
	sending.value = true;
	try {
		await call("pos_prime.api.orders.email_invoice", {
			invoice_name: props.invoiceName,
			recipient: email.value.trim(),
			content: message.value.trim(),
		});
		toast.success(`Receipt sent to ${email.value.trim()}`);
		emit("close");
	} catch (e: any) {
		toast.error(e.message || "Failed to send email");
	} finally {
		sending.value = false;
	}
}
</script>

<template>
	<Dialog :open="true" @update:open="(val) => { if (!val) emit('close') }">
		<DialogContent class="sm:max-w-sm">
			<DialogHeader>
				<DialogTitle>{{ __("Email Receipt") }}</DialogTitle>
			</DialogHeader>

			<div class="space-y-3">
				<div>
					<label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
						{{ __("Recipient Email") }}
					</label>
					<Input
						v-model="email"
						type="email"
						placeholder="customer@example.com"
						class="w-full"
						@keydown.enter="sendEmail"
					/>
				</div>

				<div>
					<label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
						{{ __("Message (optional)") }}
					</label>
					<textarea
						v-model="message"
						rows="2"
						:placeholder="__('Add a note...')"
						class="w-full rounded-lg border border-input bg-background text-foreground px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
					/>
				</div>

				<button
					@click="sendEmail"
					:disabled="sending || !email.trim()"
					class="w-full py-2.5 bg-gray-950 text-white rounded-lg text-sm font-semibold hover:bg-black dark:bg-gray-100 dark:text-gray-950 dark:hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
				>
					<Loader2 v-if="sending" :size="14" class="animate-spin" />
					<Mail v-else :size="14" />
					{{ sending ? __("Sending...") : __("Send Receipt") }}
				</button>
			</div>
		</DialogContent>
	</Dialog>
</template>
