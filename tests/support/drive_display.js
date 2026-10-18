// Drives app/display/display.js in a stub DOM and reports what the scene image
// was pointed at after each step. Used by tests/test_display.py.
const fs = require('fs'), vm = require('vm');

const nodes = {};
function node(id) {
  if (!nodes[id]) nodes[id] = {
    id, src: '', href: '', textContent: '', style: {}, children: [],
    classList: {add(){}, remove(){}, toggle(){}},
    replaceChildren(){this.children = [];}, append(){}, querySelector(){return node('x');},
  };
  return nodes[id];
}
const document = {
  getElementById: node,
  querySelector: () => node('step'),
  querySelectorAll: () => [],
  createElement: () => node('tmp'),
};
let socket = null;
class WebSocket { constructor() { socket = this; } close() { this.onclose && this.onclose(); } }

const ctx = vm.createContext({
  document, WebSocket, console,
  location: {protocol: 'http:', hostname: 'board', search: '', hash: ''},
  URLSearchParams, Math, JSON, Number, Set, Object, Array,
  // A counter, so each re-attach is visibly a different URL.
  Date: {now: (() => { let n = 0; return () => ++n; })()},
  fetch: () => Promise.reject(new Error('offline')),
  setTimeout: () => 0, clearTimeout: () => {}, setInterval: () => 0,
});
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);

const image = node('sceneImage');
const base = {instance_id: 'A', phase: 'idle', snapshot_url: null, scene: null, target: null};
const steps = [];
const at = label => steps.push([label, image.src]);

socket.onopen();
ctx.render({...base});                                             at('live');
ctx.render({...base, phase: 'offered', snapshot_url: '/api/snapshot/s1'}); at('snapshot');
ctx.render({...base, phase: 'idle'});                              at('restart-same-process');

// The feed dies with the Controller and the image never learns about it.
ctx.render({...base, instance_id: 'B', phase: 'idle'});            at('after-controller-restart');
console.log(JSON.stringify(steps));
