import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { botcivPlugin } from "./src/channel.js";
import { setBotCivRuntime } from "./src/runtime.js";

const plugin = {
  id: "botciv",
  name: "BotCiv",
  description: "bot_civ community platform channel plugin",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setBotCivRuntime(api.runtime);
    api.registerChannel({ plugin: botcivPlugin });
  },
};

export default plugin;
