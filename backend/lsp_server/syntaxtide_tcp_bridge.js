#!/usr/bin/env node
/*
 * TCP bridge for stdio-based LSP servers.
 *
 * SyntaxTide runs as a stdio language server (`node out/server.js`).
 * The backend currently expects per-language TCP sockets on fixed ports.
 * This bridge exposes a TCP listener and forwards LSP frames byte-for-byte
 * between each TCP client and a dedicated SyntaxTide child process.
 */

const net = require('net');
const { spawn } = require('child_process');
const path = require('path');

function parseArgs(argv) {
  const args = {
    server: '',
    language: 'unknown',
    port: 0,
  };

  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === '--server' && value) {
      args.server = value;
      i += 1;
    } else if (key === '--language' && value) {
      args.language = value;
      i += 1;
    } else if (key === '--port' && value) {
      args.port = Number(value);
      i += 1;
    }
  }

  return args;
}

const { server, language, port } = parseArgs(process.argv);

if (!server || !port) {
  console.error('[SyntaxTide bridge] Missing required args --server and --port');
  process.exit(2);
}

const resolvedServer = path.resolve(server);
const tcpServer = net.createServer((socket) => {
  const child = spawn('node', [resolvedServer], {
    stdio: ['pipe', 'pipe', 'pipe'],
    env: {
      ...process.env,
      SYNTAXTIDE_LANGUAGE: language,
    },
  });

  child.stderr.on('data', (chunk) => {
    process.stderr.write(`[SyntaxTide ${language}] ${chunk.toString()}`);
  });

  socket.on('data', (chunk) => {
    if (!child.stdin.destroyed) {
      child.stdin.write(chunk);
    }
  });

  child.stdout.on('data', (chunk) => {
    if (!socket.destroyed) {
      socket.write(chunk);
    }
  });

  const cleanup = () => {
    if (!socket.destroyed) {
      socket.destroy();
    }
    if (!child.killed) {
      child.kill('SIGTERM');
    }
  };

  socket.on('error', cleanup);
  socket.on('close', cleanup);
  child.on('error', cleanup);
  child.on('exit', () => {
    if (!socket.destroyed) {
      socket.end();
    }
  });
});

tcpServer.on('error', (err) => {
  console.error(`[SyntaxTide bridge] TCP server error on ${port}:`, err.message);
  process.exit(1);
});

tcpServer.listen(port, '127.0.0.1', () => {
  console.log(`[SyntaxTide bridge] ${language} listening on 127.0.0.1:${port}, server=${resolvedServer}`);
});

function shutdown() {
  tcpServer.close(() => process.exit(0));
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
