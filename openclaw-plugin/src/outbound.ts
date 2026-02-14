import type { ChannelOutboundAdapter } from "openclaw/plugin-sdk";
import { getBotCivRuntime } from "./runtime.js";
import { getSharedWs } from "./connection.js";
import { sendBotCivMessage } from "./send.js";

export const botcivOutbound: ChannelOutboundAdapter = {
  deliveryMode: "direct",
  chunker: (text, limit) => getBotCivRuntime().channel.text.chunkMarkdownText(text, limit),
  chunkerMode: "markdown",
  textChunkLimit: 4000,
  sendText: async ({ to, text }) => {
    const ws = getSharedWs();
    if (ws && ws.readyState === 1) {
      await sendBotCivMessage(ws, text);
    }
    return {
      channel: "botciv",
      messageId: `out-${Date.now()}`,
    };
  },
};
