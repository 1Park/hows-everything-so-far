/* Deck for the room: slides, an architecture drawing, and a way into the live view.
   It is static — no board, no websocket — so it still presents if the demo is down. */
const slides = [...document.querySelectorAll('.slide')];
let index = 0;

function show(next) {
  index = Math.max(0, Math.min(slides.length - 1, next));
  slides.forEach((slide, i) => slide.classList.toggle('current', i === index));
  document.getElementById('position').textContent = `${index + 1} / ${slides.length}`;
  // Named slides keep their name in the address, so a link back from another
  // screen survives the deck being reordered.
  const name = slides[index].id;
  location.hash = name ? `#${name}` : index ? `#${index + 1}` : '';
}

// A hash is either a slide name or its position, in that order of preference.
function slideFromHash() {
  const hash = location.hash.slice(1);
  if (!hash) return 0;
  const named = slides.findIndex(slide => slide.id === hash);
  if (named >= 0) return named;
  const position = Number(hash);
  return Number.isFinite(position) && position > 0 ? position - 1 : 0;
}

addEventListener('keydown', event => {
  if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(event.key)) show(index + 1);
  if (['ArrowLeft', 'PageUp', 'Backspace'].includes(event.key)) show(index - 1);
  if (event.key === 'Home') show(0);
  if (event.key === 'End') show(slides.length - 1);
});
// Click to advance, except on the link: a presenter should not have to find a key.
addEventListener('click', event => {
  if (event.target.closest('a')) return;
  show(index + (event.clientX < innerWidth * 0.25 ? -1 : 1));
});

// The live view is served by the display on 8004; same host as this deck.
const liveView = `${location.protocol}//${location.hostname}:8004/`;
for (const id of ['demoLink', 'demoLinkEnd']) document.getElementById(id).href = liveView;
// The log lives with the Controller, which serves the tablet UI.
document.getElementById('dashboardLink').href =
  `${location.protocol}//${location.hostname}:8080/dashboard`;

document.getElementById('diagram').innerHTML = `
<svg viewBox="0 0 1140 470" role="img"
     aria-label="A camera and microphone feed three board services; the Controller drives
                 the microcontroller with one command and serves the tablet and this display.">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#4a5a50"/>
    </marker>
    <marker id="arrowHot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#8fd16a"/>
    </marker>
  </defs>

  <rect class="zone" x="210" y="20" width="570" height="330" rx="16"/>
  <text class="zone-label" x="228" y="46">ARDUINO VENTUNO Q</text>

  <!-- What it senses -->
  <rect class="box" x="20" y="66" width="152" height="54" rx="10"/>
  <text class="label" x="38" y="90">USB camera</text>
  <text class="sub" x="38" y="108">Brio 101</text>

  <rect class="box" x="20" y="186" width="152" height="54" rx="10"/>
  <text class="label" x="38" y="210">Microphone</text>
  <text class="sub" x="38" y="228">same device, ALSA</text>

  <path class="wire" d="M172 93 H 245"/>
  <path class="wire" d="M172 213 H 208 V 179 H 245"/>

  <!-- Models, each on its own service -->
  <rect class="box accent" x="248" y="60" width="200" height="66" rx="10"/>
  <text class="label" x="266" y="86">Vision · 8001</text>
  <text class="sub" x="266" y="106">YOLO11n + DINOv2 · NPU</text>

  <rect class="box" x="248" y="146" width="200" height="66" rx="10"/>
  <text class="label" x="266" y="172">Speech · 8179</text>
  <text class="sub" x="266" y="192">whisper tiny.en · CPU</text>

  <rect class="box accent" x="248" y="232" width="200" height="66" rx="10"/>
  <text class="label" x="266" y="258">Language · 8000</text>
  <text class="sub" x="266" y="278">Gemma .pte · NPU</text>

  <rect class="box" x="520" y="80" width="190" height="150" rx="10"/>
  <text class="label" x="538" y="110">Controller · 8080</text>
  <text class="sub" x="538" y="134">one video owner</text>
  <text class="sub" x="538" y="156">policy and session</text>
  <text class="sub" x="538" y="178">serves the tablet UI</text>
  <text class="sub" x="538" y="200">logs every request</text>

  <rect class="box accent" x="520" y="270" width="190" height="66" rx="10"/>
  <text class="label" x="538" y="296">Voice · 8003</text>
  <text class="sub" x="538" y="316">Piper decoder · NPU</text>

  <path class="wire" d="M448 93 H 515"/>
  <path class="wire" d="M448 179 H 515"/>
  <path class="wire" d="M448 265 H 486 V 215 H 515"/>
  <path class="wire" d="M615 230 V 266"/>

  <!-- The only thing that crosses to the microcontroller is a command -->
  <rect class="box" x="870" y="100" width="230" height="110" rx="10"/>
  <text class="label" x="888" y="130">STM32H5</text>
  <text class="sub" x="888" y="152">display now, gripper later</text>
  <text class="sub" x="888" y="174">host watchdog, 2s</text>
  <text class="sub" x="888" y="196">refuses repeated commands</text>

  <path class="wire hot" d="M710 155 H 865" marker-end="url(#arrowHot)"/>
  <text class="sub hot-label" x="724" y="143">one command</text>
  <text class="sub" x="724" y="177">arduino-router · RPC</text>

  <!-- Screens, both outside the board -->
  <rect class="box" x="248" y="392" width="200" height="60" rx="10"/>
  <text class="label" x="266" y="416">Tablet</text>
  <text class="sub" x="266" y="436">the customer's screen</text>

  <rect class="box" x="520" y="392" width="200" height="60" rx="10"/>
  <text class="label" x="538" y="416">This room · 8004</text>
  <text class="sub" x="538" y="436">read-only view</text>

  <path class="wire" d="M520 205 H 486 V 370 H 348 V 388"/>
  <path class="wire" d="M710 205 H 756 V 370 H 620 V 388"/>
  <text class="sub" x="500" y="364">wired Ethernet</text>
</svg>`;

show(slideFromHash());
