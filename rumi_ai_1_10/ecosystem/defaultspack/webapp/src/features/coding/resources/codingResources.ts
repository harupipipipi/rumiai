import { api } from "../../../lib/api";

export const codingResources = {
  listCodingApprovals: api.listCodingApprovals,
  approveCodingApproval: api.approveCodingApproval,
  denyCodingApproval: api.denyCodingApproval,
  listCodingCheckpoints: api.listCodingCheckpoints,
  createCodingCheckpoint: api.createCodingCheckpoint,
  restoreCodingSnapshot: api.restoreCodingSnapshot,
  getGitStatus: api.getGitStatus,
  getGitDiff: api.getGitDiff,
  runTerminalCommand: api.runTerminalCommand,
  listMcpServers: api.listMcpServers,
  registerMcpServer: api.registerMcpServer,
  connectMcpServer: api.connectMcpServer,
  listBrowserArtifacts: api.listBrowserArtifacts,
  createCodingAgentSession: api.createCodingAgentSession,
  getCodingAgentSessionStatus: api.getCodingAgentSessionStatus,
};
