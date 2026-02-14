// Shared WebSocket connection reference for botciv plugin
// monitor.ts sets it on connect, outbound.ts reads it to send proactive messages

let _ws: any = null;

export function setSharedWs(ws: any) {
  _ws = ws;
}

export function getSharedWs(): any {
  return _ws;
}
