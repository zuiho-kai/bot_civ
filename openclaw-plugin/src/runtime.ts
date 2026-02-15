import type { PluginRuntime } from "openclaw/plugin-sdk";

let runtime: PluginRuntime | null = null;

export function setBotCivRuntime(next: PluginRuntime) {
  runtime = next;
}

export function getBotCivRuntime(): PluginRuntime {
  if (!runtime) {
    throw new Error("BotCiv runtime not initialized");
  }
  return runtime;
}
