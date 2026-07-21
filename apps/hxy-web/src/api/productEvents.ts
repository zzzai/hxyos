export type ProductEventName = "briefing_feedback";

export interface ProductEventInput {
  clientEventId?: string;
  eventName: ProductEventName;
  subjectId: string;
  useful: boolean;
}

export interface ProductEventClient {
  track: (input: ProductEventInput) => Promise<boolean>;
}

export const productEventClient: ProductEventClient = {
  track: async (input) => {
    try {
      const clientEventId = input.clientEventId ?? crypto.randomUUID();
      const response = await fetch("/api/v1/product-events", {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_event_id: clientEventId,
          event_name: input.eventName,
          subject_id: input.subjectId,
          useful: input.useful,
        }),
      });
      return response.ok;
    } catch {
      // Product telemetry must never block a store operating action.
      return false;
    }
  },
};
