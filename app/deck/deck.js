/* Deck for the room: slides, an architecture drawing, and a way into the live view.
   It is static — no board, no websocket — so it still presents if the demo is down. */
const slides = [...document.querySelectorAll('.slide')];
let index = 0;

function show(next) {
  index = Math.max(0, Math.min(slides.length - 1, next));
  slides.forEach((slide, i) => slide.classList.toggle('current', i === index));
  document.getElementById('position').textContent = `${index + 1} / ${slides.length}`;
  location.hash = index ? `#${index + 1}` : '';
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

// The robot picture is optional: the slide should read as a plan, not a broken image.
const robot = document.getElementById('robot');
robot.onerror = () => {
  robot.hidden = true;
  document.getElementById('robotNote').hidden = false;
};

document.getElementById('diagram').innerHTML = `
<svg viewBox="0 0 1000 440" role="img"
     aria-label="Camera and microphone feed board services, which drive the microcontroller;
                 a tablet and a venue display watch over Ethernet.">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="#4a5a50"/>
    </marker>
  </defs>

  <rect class="zone" x="210" y="20" width="520" height="300" rx="16"/>
  <text class="zone-label" x="226" y="44">ARDUINO VENTUNO Q</text>

  <!-- Sensors -->
  <rect class="box" x="20" y="96" width="150" height="54" rx="10"/>
  <text class="label" x="38" y="120">USB camera</text>
  <text class="sub" x="38" y="138">Brio 101</text>

  <rect class="box" x="20" y="186" width="150" height="54" rx="10"/>
  <text class="label" x="38" y="210">Microphone</text>
  <text class="sub" x="38" y="228">same device, ALSA</text>

  <path class="wire" d="M170 123 H 250"/>
  <path class="wire" d="M170 213 H 250"/>

  <!-- Board services -->
  <rect class="box accent" x="250" y="64" width="200" height="66" rx="10"/>
  <text class="label" x="268" y="90">Vision · 8001</text>
  <text class="sub" x="268" y="110">YOLO11n + DINOv2 · NPU</text>

  <rect class="box" x="250" y="150" width="200" height="66" rx="10"/>
  <text class="label" x="268" y="176">Speech · 8179</text>
  <text class="sub" x="268" y="196">whisper tiny.en · CPU</text>

  <rect class="box accent" x="250" y="236" width="200" height="66" rx="10"/>
  <text class="label" x="268" y="262">Language · 8000</text>
  <text class="sub" x="268" y="282">Gemma .pte · NPU</text>

  <rect class="box" x="510" y="106" width="190" height="108" rx="10"/>
  <text class="label" x="528" y="134">Controller · 8080</text>
  <text class="sub" x="528" y="154">one video owner</text>
  <text class="sub" x="528" y="172">policy and session</text>
  <text class="sub" x="528" y="190">serves the tablet UI</text>

  <rect class="box accent" x="510" y="236" width="190" height="66" rx="10"/>
  <text class="label" x="528" y="262">Voice · 8003</text>
  <text class="sub" x="528" y="282">Piper decoder · NPU</text>

  <path class="wire" d="M450 97 H 505"/>
  <path class="wire" d="M450 183 H 505"/>
  <path class="wire" d="M450 269 H 505"/>
  <path class="wire" d="M605 214 V 232"/>

  <!-- Microcontroller -->
  <rect class="box" x="760" y="106" width="210" height="108" rx="10"/>
  <text class="label" x="778" y="134">STM32H5</text>
  <text class="sub" x="778" y="154">LED now, gripper later</text>
  <text class="sub" x="778" y="172">host watchdog, 2s</text>
  <text class="sub" x="778" y="190">refuses repeats</text>
  <path class="wire hot" d="M700 160 H 755"/>
  <text class="sub" x="700" y="148" style="fill:#8fd16a">one command</text>
  <text class="sub" x="700" y="186">arduino-router · RPC</text>

  <!-- Screens -->
  <rect class="box" x="250" y="356" width="200" height="60" rx="10"/>
  <text class="label" x="268" y="380">Tablet</text>
  <text class="sub" x="268" y="400">the customer's screen</text>

  <rect class="box" x="510" y="356" width="200" height="60" rx="10"/>
  <text class="label" x="528" y="380">This room · 8004</text>
  <text class="sub" x="528" y="400">read-only view</text>

  <path class="wire" d="M560 214 V 352"/>
  <path class="wire" d="M530 214 H 350 V 352"/>
  <text class="sub" x="356" y="340">wired Ethernet</text>
</svg>`;

show(location.hash ? Number(location.hash.slice(1)) - 1 : 0);
