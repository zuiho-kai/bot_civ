import {
  DEFAULT_ACCOUNT_ID,
  buildChannelConfigSchema,
  emptyPluginConfigSchema,
  type ChannelPlugin,
} from "openclaw/plugin-sdk";
import { getBotCivRuntime } from "./runtime.js";
import { botcivOutbound } from "./outbound.js";

export type BotCivAccountConfig = {
  enabled: boolean;
  serverUrl: string;
  agentId: number;
  token: string;
  dm?: {
    policy?: string;
    allowFrom?: Array<string | number>;
  };
};

export type ResolvedBotCivAccount = {
  accountId: string;
  name: string;
  enabled: boolean;
  configured: boolean;
  config: BotCivAccountConfig;
  serverUrl: string;
  agentId: number;
  token: string;
};

function resolveBotCivAccount(cfg: any, accountId?: string | null): ResolvedBotCivAccount {
  const botcivCfg = cfg.channels?.botciv ?? {};
  return {
    accountId: accountId ?? DEFAULT_ACCOUNT_ID,
    name: botcivCfg.name ?? "BotCiv",
    enabled: botcivCfg.enabled !== false,
    configured: Boolean(botcivCfg.serverUrl && botcivCfg.token),
    config: botcivCfg,
    serverUrl: botcivCfg.serverUrl ?? "",
    agentId: botcivCfg.agentId ?? 1,
    token: botcivCfg.token ?? "",
  };
}

export const botcivPlugin: ChannelPlugin<ResolvedBotCivAccount> = {
  id: "botciv",
  meta: {
    id: "botciv",
    label: "BotCiv",
    selectionLabel: "BotCiv (community platform)",
    docsPath: "/channels/botciv",
    docsLabel: "botciv",
    blurb: "Connect to a bot_civ community platform instance.",
    order: 80,
  },
  capabilities: {
    chatTypes: ["group"],
  },
  reload: { configPrefixes: ["channels.botciv"] },
  config: {
    listAccountIds: () => [DEFAULT_ACCOUNT_ID],
    resolveAccount: (cfg, accountId) => resolveBotCivAccount(cfg, accountId),
    defaultAccountId: () => DEFAULT_ACCOUNT_ID,
    isConfigured: (account) => account.configured,
    describeAccount: (account) => ({
      accountId: account.accountId,
      name: account.name,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
  security: {
    resolveDmPolicy: ({ account }) => ({
      policy: "open",
      allowFrom: ["*"],
      allowFromPath: "channels.botciv.dm.allowFrom",
      approveHint: "",
    }),
  },
  outbound: botcivOutbound,
  status: {
    defaultRuntime: {
      accountId: DEFAULT_ACCOUNT_ID,
      running: false,
      lastStartAt: null,
      lastStopAt: null,
      lastError: null,
    },
    buildChannelSummary: ({ snapshot }) => ({
      configured: snapshot.configured ?? false,
      running: snapshot.running ?? false,
      lastStartAt: snapshot.lastStartAt ?? null,
      lastStopAt: snapshot.lastStopAt ?? null,
      lastError: snapshot.lastError ?? null,
    }),
    buildAccountSnapshot: ({ account, runtime }) => ({
      accountId: account.accountId,
      name: account.name,
      enabled: account.enabled,
      configured: account.configured,
      running: runtime?.running ?? false,
      lastStartAt: runtime?.lastStartAt ?? null,
      lastStopAt: runtime?.lastStopAt ?? null,
      lastError: runtime?.lastError ?? null,
    }),
  },
  gateway: {
    startAccount: async (ctx) => {
      const account = ctx.account;
      ctx.setStatus({ accountId: account.accountId });
      ctx.log?.info(`[${account.accountId}] starting bot_civ provider (${account.serverUrl})`);
      const { monitorBotCivProvider } = await import("./monitor.js");
      return monitorBotCivProvider({
        serverUrl: account.serverUrl,
        agentId: account.agentId,
        token: account.token,
        cfg: ctx.cfg,
        runtime: ctx.runtime,
        abortSignal: ctx.abortSignal,
        accountId: account.accountId,
      });
    },
  },
};
