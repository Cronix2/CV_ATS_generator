// Minimal typings for noVNC's RFB client (the package ships plain JavaScript).
declare module "@novnc/novnc" {
  export interface RFBOptions {
    shared?: boolean;
    wsProtocols?: string[];
  }

  export default class RFB {
    constructor(target: HTMLElement, urlOrChannel: string | WebSocket, options?: RFBOptions);
    scaleViewport: boolean;
    resizeSession: boolean;
    clipViewport: boolean;
    focusOnClick: boolean;
    viewOnly: boolean;
    disconnect(): void;
    focus(): void;
    addEventListener(type: "connect" | "disconnect" | "securityfailure", listener: (e: CustomEvent) => void): void;
  }
}
