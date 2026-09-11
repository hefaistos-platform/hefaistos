/**
 * lspClient.ts
 *
 * WebSocket-based Language Server Protocol (LSP) client utility.
 *
 * Manages a persistent WebSocket connection to the Django Channels
 * LSP proxy endpoint (`/ws/lsp/{language}/`) and bridges JSON-RPC
 * messages between the Monaco Editor and the local SyntaxTide LSP
 * servers.
 */

import * as monaco from 'monaco-editor';

export type LspConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export class LSPClient {
  private ws: WebSocket | null = null;
  private messageId = 0;
  private pendingRequests = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (reason: unknown) => void }
  >();

  constructor(
    private readonly language: string,
    private readonly onDiagnostics?: (diagnostics: monaco.editor.IMarkerData[]) => void,
    private readonly onStatusChange?: (status: LspConnectionStatus) => void,
  ) {}

  /** Open a WebSocket connection to the Django Channels LSP proxy. */
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/lsp/${this.language}/`;

      this.onStatusChange?.('connecting');
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.onStatusChange?.('connected');
        this.sendInitialize();
        resolve();
      };

      this.ws.onerror = (event) => {
        this.onStatusChange?.('error');
        reject(event);
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data as string);
          this.handleMessage(message);
        } catch (err) {
          console.error('[LSPClient] Failed to parse message:', err);
        }
      };

      this.ws.onclose = () => {
        this.onStatusChange?.('disconnected');
        // Reject any outstanding requests
        this.pendingRequests.forEach(({ reject: rej }) =>
          rej(new Error('WebSocket closed')),
        );
        this.pendingRequests.clear();
      };
    });
  }

  /** Send the LSP `initialize` request required before using any other method. */
  private sendInitialize() {
    this.sendRequest('initialize', {
      processId: null,
      capabilities: {
        textDocument: {
          completion: { completionItem: { snippetSupport: true } },
          hover: { contentFormat: ['markdown', 'plaintext'] },
          publishDiagnostics: {},
        },
      },
      rootUri: null,
    });
  }

  /** Send a JSON-RPC request and return a Promise for the result. */
  sendRequest(method: string, params: unknown): Promise<unknown> {
    return new Promise((resolve, reject) => {
      const id = ++this.messageId;
      const message = { jsonrpc: '2.0', id, method, params };

      this.pendingRequests.set(id, { resolve, reject });

      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(message));
      } else {
        this.pendingRequests.delete(id);
        reject(new Error('WebSocket is not connected'));
      }
    });
  }

  /** Send a JSON-RPC notification (no response expected). */
  sendNotification(method: string, params: unknown): void {
    const message = { jsonrpc: '2.0', method, params };

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  private handleMessage(message: Record<string, unknown>) {
    // Handle responses to outbound requests
    if (typeof message['id'] === 'number' && this.pendingRequests.has(message['id'])) {
      const { resolve, reject } = this.pendingRequests.get(message['id'])!;
      this.pendingRequests.delete(message['id']);

      if (message['error']) {
        reject(message['error']);
      } else {
        resolve(message['result']);
      }
      return;
    }

    // Handle server-initiated notifications
    if (message['method'] === 'textDocument/publishDiagnostics') {
      this.handleDiagnostics(message['params'] as Record<string, unknown>);
    }
  }

  private handleDiagnostics(params: Record<string, unknown>) {
    const diagnostics = params['diagnostics'] as Array<Record<string, unknown>>;
    if (!Array.isArray(diagnostics)) return;

    const markers: monaco.editor.IMarkerData[] = diagnostics.map((diag) => {
      const range = diag['range'] as {
        start: { line: number; character: number };
        end: { line: number; character: number };
      };
      return {
        severity: this.convertSeverity(diag['severity'] as number),
        startLineNumber: range.start.line + 1,
        startColumn: range.start.character + 1,
        endLineNumber: range.end.line + 1,
        endColumn: range.end.character + 1,
        message: diag['message'] as string,
        source: 'LSP',
      };
    });

    this.onDiagnostics?.(markers);
  }

  private convertSeverity(lspSeverity: number): monaco.MarkerSeverity {
    switch (lspSeverity) {
      case 1:
        return monaco.MarkerSeverity.Error;
      case 2:
        return monaco.MarkerSeverity.Warning;
      case 3:
        return monaco.MarkerSeverity.Info;
      case 4:
        return monaco.MarkerSeverity.Hint;
      default:
        return monaco.MarkerSeverity.Error;
    }
  }

  // ---------------------------------------------------------------------------
  // Convenience wrappers for common LSP notifications and requests
  // ---------------------------------------------------------------------------

  didOpen(uri: string, languageId: string, version: number, text: string): void {
    this.sendNotification('textDocument/didOpen', {
      textDocument: { uri, languageId, version, text },
    });
  }

  didChange(uri: string, version: number, text: string): void {
    this.sendNotification('textDocument/didChange', {
      textDocument: { uri, version },
      contentChanges: [{ text }],
    });
  }

  async completion(
    uri: string,
    position: { line: number; character: number },
  ): Promise<unknown> {
    return this.sendRequest('textDocument/completion', {
      textDocument: { uri },
      position,
    });
  }

  async hover(
    uri: string,
    position: { line: number; character: number },
  ): Promise<unknown> {
    return this.sendRequest('textDocument/hover', {
      textDocument: { uri },
      position,
    });
  }

  /** Close the WebSocket connection and clean up. */
  disconnect(): void {
    this.ws?.close();
    this.ws = null;
    this.pendingRequests.clear();
  }
}
