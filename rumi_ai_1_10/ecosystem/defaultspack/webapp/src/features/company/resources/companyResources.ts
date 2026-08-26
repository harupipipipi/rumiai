import { api, arrayFromRecord } from "../../../lib/api";

export const companyResources = {
  listCompanies: api.listCompanies,
  getCompanyStatus: api.getCompanyStatus,
  getAgentStudio: api.getAgentStudio,
  updateAgentStudio: api.updateAgentStudio,
  getP2PStatus: api.getP2PStatus,
  getP2PIdentity: api.getP2PIdentity,
  listP2PPeers: api.listP2PPeers,
  listCompanyAgents: api.listCompanyAgents,
  upsertCompanyAgent: api.upsertCompanyAgent,
  listCompanyChannels: api.listCompanyChannels,
  listCompanyTasks: api.listCompanyTasks,
  dispatchCompanyTask: api.dispatchCompanyTask,
  listCompanyRuns: api.listCompanyRuns,
  listCompanyAgentInbox: api.listCompanyAgentInbox,
  listCompanyInboundRoutes: api.listCompanyInboundRoutes,
  listCompanyMessages: api.listCompanyMessages,
  sendCompanyMessage: api.sendCompanyMessage,
  upsertCompanyInboundRoute: api.upsertCompanyInboundRoute,
  deleteCompanyInboundRoute: api.deleteCompanyInboundRoute,
  updateCompanySettings: api.updateCompanySettings,
  webSearch: api.webSearch,
  startP2PPairing: api.startP2PPairing,
  sendP2PMessage: api.sendP2PMessage,
  createCompanyTask: api.createCompanyTask,
  updateCompanyTask: api.updateCompanyTask,
  bootstrapCompanyWorkspace: api.bootstrapCompanyWorkspace,
};

export { arrayFromRecord };
