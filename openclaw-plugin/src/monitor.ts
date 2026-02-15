import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const WebSocket = require("/usr/lib/node_modules/openclaw/node_modules/ws");

import {
  createReplyPrefixContext,
  type RuntimeEnv,
} from "openclaw/plugin-sdk";
import { getBotCivRuntime } from "./runtime.js";
import { sendBotCivMessage } from "./send.js";
import { setSharedWs } from "./connection.js";

export type MonitorBotCivOpts = {
  serverUrl: string;
  agentId: number;
  token: string;
  cfg: any;
  runtime: RuntimeEnv;
  abortSignal?: AbortSignal;
  accountId?: string;
};

export async function monitorBotCivProvider(opts: MonitorBotCivOpts): Promise<void> {
  const core = getBotCivRuntime();
  const cfg = opts.cfg;
  const runtime = opts.runtime;
  const logger = core.logging.getChildLogger({ module: "botciv-auto-reply" });
  const logVerbose = (msg: string) => {
    if (core.logging.shouldLogVerbose()) {
      logger.debug(msg);
    }
  };

  const wsUrl = `${opts.serverUrl.replace(/^http/, "ws")}/api/ws/${opts.agentId}?token=${opts.token}`;
  let ws: any = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let lastSinceId = 0;
  let aborted = false;

  function cleanup() {
    aborted = true;
    if (pingTimer) clearInterval(pingTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) {
      try { ws.close(); } catch {}
    }
  }

  opts.abortSignal?.addEventListener("abort", cleanup, { once: true });

  async function handleMessage(data: any) {
    try {
      const msgType = data.type;
      if (msgType === "pong") return;

      if (msgType === "new_message") {
        const msg = data.data;
        if (!msg) return;

        // Track since_id for reconnection
        if (msg.id && msg.id > lastSinceId) {
          lastSinceId = msg.id;
        }

        // Skip our own messages
        if (msg.agent_id === opts.agentId) return;

        const senderName = msg.agent_name ?? `agent_${msg.agent_id}`;
        const content = msg.content ?? "";
        if (!content.trim()) return;

        logVerbose(`botciv inbound: from=${senderName} content="${content.slice(0, 200)}"`);

        const route = core.channel.routing.resolveAgentRoute({
          cfg,
          channel: "botciv",
          peer: { kind: "channel", id: `botciv:${opts.agentId}` },
        });

        const storePath = core.channel.session.resolveStorePath(cfg.session?.store, {
          agentId: route.agentId,
        });

        const envelopeOptions = core.channel.reply.resolveEnvelopeFormatOptions(cfg);
        const previousTimestamp = core.channel.session.readSessionUpdatedAt({
          storePath,
          sessionKey: route.sessionKey,
        });

        const body = core.channel.reply.formatAgentEnvelope({
          channel: "BotCiv",
          from: senderName,
          timestamp: msg.timestamp ? new Date(msg.timestamp).getTime() : undefined,
          previousTimestamp,
          envelope: envelopeOptions,
          body: content,
        });

        const ctxPayload = core.channel.reply.finalizeInboundContext({
          Body: body,
          RawBody: content,
          CommandBody: content,
          From: `botciv:${msg.agent_id}`,
          To: `botciv:channel:${opts.agentId}`,
          SessionKey: route.sessionKey,
          AccountId: route.accountId ?? opts.accountId,
          ChatType: "channel",
          ConversationLabel: "bot_civ",
          SenderName: senderName,
          SenderId: String(msg.agent_id),
          GroupSubject: "bot_civ community",
          Provider: "botciv" as any,
          Surface: "botciv" as any,
          WasMentioned: checkMentioned(content, cfg),
          MessageSid: String(msg.id ?? ""),
          Timestamp: msg.timestamp ? new Date(msg.timestamp).getTime() : Date.now(),
          CommandAuthorized: true,
          CommandSource: "text" as any,
          OriginatingChannel: "botciv" as any,
          OriginatingTo: `botciv:channel:${opts.agentId}`,
        });

        await core.channel.session.recordInboundSession({
          storePath,
          sessionKey: ctxPayload.SessionKey ?? route.sessionKey,
          ctx: ctxPayload,
          onRecordError: (err) => {
            logger.warn(
              { error: String(err), storePath, sessionKey: ctxPayload.SessionKey },
              "failed updating session meta",
            );
          },
        });

        const prefixContext = createReplyPrefixContext({ cfg, agentId: route.agentId });

        const { dispatcher, replyOptions, markDispatchIdle } =
          core.channel.reply.createReplyDispatcherWithTyping({
            responsePrefix: prefixContext.responsePrefix,
            responsePrefixContextProvider: prefixContext.responsePrefixContextProvider,
            humanDelay: core.channel.reply.resolveHumanDelayConfig(cfg, route.agentId),
            deliver: async (payload) => {
              const text = typeof payload === "string" ? payload : payload.text ?? "";
              if (text.trim() && ws) {
                await sendBotCivMessage(ws, text);
              }
            },
            onError: (err, info) => {
              runtime.error?.(`botciv ${info.kind} reply failed: ${String(err)}`);
            },
          });

        const { queuedFinal, counts } = await core.channel.reply.dispatchReplyFromConfig({
          ctx: ctxPayload,
          cfg,
          dispatcher,
          replyOptions: {
            ...replyOptions,
            onModelSelected: prefixContext.onModelSelected,
          },
        });
        markDispatchIdle();

        if (queuedFinal) {
          logVerbose(`botciv: delivered ${counts.final} replies`);
          core.system.enqueueSystemEvent(
            `BotCiv message from ${senderName}: ${content.slice(0, 160)}`,
            {
              sessionKey: route.sessionKey,
              contextKey: `botciv:message:${msg.id ?? "unknown"}`,
            },
          );
        }
      }
    } catch (err) {
      runtime.error?.(`botciv handler error: ${String(err)}`);
    }
  }

  function checkMentioned(content: string, cfg: any): boolean {
    const agentName = cfg.name ?? cfg.agent?.name ?? "";
    if (agentName && content.toLowerCase().includes(agentName.toLowerCase())) {
      return true;
    }
    if (content.includes(`@${opts.agentId}`)) return true;
    return false;
  }

  function connect() {
    if (aborted) return;

    const url = lastSinceId > 0 ? `${wsUrl}&since_id=${lastSinceId}` : wsUrl;
    logVerbose(`botciv: connecting to ${opts.serverUrl}`);

    ws = new WebSocket(url);

    ws.on("open", () => {
      logVerbose("botciv: connected");
      runtime.log?.("botciv: WebSocket connected");
      setSharedWs(ws);

      if (pingTimer) clearInterval(pingTimer);
      pingTimer = setInterval(() => {
        if (ws?.readyState === 1) {
          ws.send(JSON.stringify({ type: "pong" }));
        }
      }, 25000);
    });

    ws.on("message", (raw: any) => {
      try {
        const data = JSON.parse(raw.toString());
        handleMessage(data);
      } catch (err) {
        logVerbose(`botciv: parse error: ${String(err)}`);
      }
    });

    ws.on("close", (code: number) => {
      logVerbose(`botciv: disconnected (code=${code})`);
      setSharedWs(null);
      if (pingTimer) clearInterval(pingTimer);
      if (!aborted) {
        reconnectTimer = setTimeout(connect, 3000);
      }
    });

    ws.on("error", (err: Error) => {
      logVerbose(`botciv: ws error: ${err.message}`);
      runtime.error?.(`botciv ws error: ${err.message}`);
    });
  }

  connect();

  await new Promise<void>((resolve) => {
    if (aborted) { resolve(); return; }
    opts.abortSignal?.addEventListener("abort", () => resolve(), { once: true });
  });
}
