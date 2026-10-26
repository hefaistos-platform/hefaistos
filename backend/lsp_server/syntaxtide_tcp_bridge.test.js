const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { mkdtemp, rm, writeFile } = require('node:fs/promises');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

test('bridge forwards split LSP frames using stdio and the current Node binary',
  { timeout: 10000 }, async (t) => {
    const directory = await mkdtemp(path.join(os.tmpdir(), 'hefaistos-lsp-'));
    t.after(() => rm(directory, { recursive: true, force: true }));
    const server = path.join(directory, 'server.js');
    await writeFile(server, `
      require('node:assert/strict').ok(process.argv.includes('--stdio'));
      process.stdin.pipe(process.stdout);
    `);

    const reservation = net.createServer();
    reservation.listen(0, '127.0.0.1');
    await once(reservation, 'listening');
    const port = reservation.address().port;
    await new Promise((resolve) => reservation.close(resolve));

    // No node binary on PATH: the bridge must use process.execPath.
    const bridge = spawn(process.execPath, [
      path.join(__dirname, 'syntaxtide_tcp_bridge.js'),
      '--server', server, '--language', 'spl', '--port', String(port),
    ], { env: { ...process.env, PATH: directory } });
    t.after(() => bridge.kill());
    let errors = '';
    bridge.stderr.on('data', (data) => { errors += data; });
    const [ready] = await once(bridge.stdout, 'data');
    assert.match(ready.toString(), /listening on/);

    const socket = net.createConnection(port, '127.0.0.1');
    t.after(() => socket.destroy());
    await once(socket, 'connect');
    const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} });
    const header = `Content-Length: ${Buffer.byteLength(body)}\r\n\r\n`;
    const expected = Buffer.from(header + body);
    const response = new Promise((resolve, reject) => {
      const chunks = [];
      let length = 0;
      socket.on('data', (data) => {
        chunks.push(data);
        length += data.length;
        if (length >= expected.length) resolve(Buffer.concat(chunks));
      });
      socket.on('error', reject);
      socket.on('end', () => reject(new Error(`LSP child disconnected: ${errors}`)));
    });
    socket.write(header);
    socket.write(body.slice(0, 10));
    socket.write(body.slice(10));
    assert.deepEqual(await response, expected);
    assert.equal(errors, '');
  });
