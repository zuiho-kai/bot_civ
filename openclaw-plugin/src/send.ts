export async function sendBotCivMessage(
  ws: any,
  text: string,
): Promise<void> {
  if (ws.readyState !== 1) {
    throw new Error("botciv: WebSocket not connected");
  }
  ws.send(JSON.stringify({
    type: "chat_message",
    content: text,
  }));
}
