import { api } from "../../../lib/api";

export type AgentNotificationProjection = Awaited<ReturnType<typeof api.listAgentNotifications>>;

export function listAgentNotifications(): Promise<AgentNotificationProjection> {
  return api.listAgentNotifications();
}
