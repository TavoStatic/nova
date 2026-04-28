(() => {
  const canvas = document.getElementById("leahBackdrop");
  if (!canvas) {
    return;
  }

  const gl = canvas.getContext("webgl2", {
    alpha: true,
    antialias: true,
    depth: false,
    stencil: false,
    powerPreference: "low-power",
    premultipliedAlpha: false,
  });
  if (!gl) {
    canvas.hidden = true;
    return;
  }

  const vertexShaderSource = `#version 300 es
  in vec2 a_position;
  out vec2 uv;
  void main() {
    uv = a_position * 0.5 + 0.5;
    gl_Position = vec4(a_position, 0.0, 1.0);
  }`;

  const fragmentShaderSource = `#version 300 es
  precision highp float;

  in vec2 uv;
  out vec4 out_color;

  uniform vec2 u_resolution;
  uniform float u_time;
  uniform vec4 u_mouse;
  uniform float u_pulse;
  uniform vec3 u_palette0;
  uniform vec3 u_palette1;
  uniform vec3 u_palette2;

  float random(in vec2 st) {
    return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
  }

  float noise(in vec2 st) {
    vec2 i = floor(st);
    vec2 f = fract(st);
    vec2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);

    float a = random(i);
    float b = random(i + vec2(1.0, 0.0));
    float c = random(i + vec2(0.0, 1.0));
    float d = random(i + vec2(1.0, 1.0));

    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
  }

  #define OCTAVES 5
  float fbm(in vec2 st) {
    float value = 0.0;
    float amplitude = 0.5;
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));

    for (int i = 0; i < OCTAVES; i++) {
      value += amplitude * noise(st);
      st = rot * st * 2.0 + vec2(100.0, 0.0);
      amplitude *= 0.5;
    }
    return value;
  }

  float warpPattern(in vec2 p, out vec2 q, out vec2 r) {
    q.x = fbm(p + vec2(0.0, 0.0));
    q.y = fbm(p + vec2(5.2, 1.3));

    float viscosity = 1.0 - (length(q) * 0.8);
    viscosity = clamp(viscosity, 0.2, 1.0);
    float t = u_time * (0.18 + u_pulse * 0.1);
    vec2 mouseFlow = vec2(
      (u_mouse.x / max(u_resolution.x, 1.0) - 0.5) * 0.45,
      (u_mouse.y / max(u_resolution.y, 1.0) - 0.5) * 0.45
    );
    vec2 flow = vec2(t * viscosity, t * viscosity * 1.2) + mouseFlow;

    r.x = fbm(p + 4.0 * q + flow + vec2(1.7, 9.2));
    r.y = fbm(p + 4.0 * q + flow + vec2(8.3, 2.8));

    return fbm(p + 4.0 * r);
  }

  vec3 getNormal(vec2 p) {
    vec2 q;
    vec2 r;
    float d = 0.01;

    float hCenter = warpPattern(p, q, r);
    float hRight = warpPattern(p + vec2(d, 0.0), q, r);
    float hTop = warpPattern(p + vec2(0.0, d), q, r);

    vec3 vRight = vec3(d, 0.0, hRight - hCenter);
    vec3 vTop = vec3(0.0, d, hTop - hCenter);

    return normalize(cross(vRight, vTop));
  }

  void main() {
    vec2 st = (2.0 * uv - 1.0) * vec2(u_resolution.x / max(u_resolution.y, 1.0), 1.0);
    st *= 1.3;

    vec2 q;
    vec2 r;
    float f = warpPattern(st, q, r);

    vec3 color = mix(u_palette0, u_palette1, clamp(q.y * length(q), 0.0, 1.0));
    color = mix(color, u_palette2, clamp(r.x + u_pulse * 0.22, 0.0, 1.0));
    color = color * f * (1.08 + u_pulse * 0.26) + 0.08 * f;

    vec3 normal = getNormal(st);
    vec3 lightDir = normalize(vec3(-1.0, -1.0, -2.0));
    float diff = max(dot(normal, -lightDir), 0.0);

    vec3 viewDir = vec3(0.0, 0.0, -1.0);
    vec3 reflectDir = reflect(lightDir, normal);
    float spec = pow(max(dot(viewDir, reflectDir), 0.0), 40.0);

    color *= (0.44 + 0.56 * diff);
    color += vec3(spec) * (0.34 + u_pulse * 0.26);

    float dither = (random(uv * (u_time + 1.0)) - 0.5) / 100.0;
    color += dither;

    float alpha = 0.74 + u_pulse * 0.14;
    out_color = vec4(color, alpha);
  }`;

  function createShader(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  const program = gl.createProgram();
  const vs = createShader(gl.VERTEX_SHADER, vertexShaderSource);
  const fs = createShader(gl.FRAGMENT_SHADER, fragmentShaderSource);
  if (!vs || !fs) {
    canvas.hidden = true;
    return;
  }

  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(program));
    canvas.hidden = true;
    return;
  }

  const positions = new Float32Array([-1, 1, -1, -1, 1, 1, 1, -1]);
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);

  const posLoc = gl.getAttribLocation(program, "a_position");
  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

  const locResolution = gl.getUniformLocation(program, "u_resolution");
  const locTime = gl.getUniformLocation(program, "u_time");
  const locMouse = gl.getUniformLocation(program, "u_mouse");
  const locPulse = gl.getUniformLocation(program, "u_pulse");
  const locPalette0 = gl.getUniformLocation(program, "u_palette0");
  const locPalette1 = gl.getUniformLocation(program, "u_palette1");
  const locPalette2 = gl.getUniformLocation(program, "u_palette2");

  let mouseX = 0;
  let mouseY = 0;
  let lastPaletteSync = 0;
  let palette0 = [0.05, 0.1, 0.25];
  let palette1 = [0.1, 0.4, 0.5];
  let palette2 = [0.8, 0.9, 0.95];

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function parseRgbTriplet(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (!value) {
      return fallback;
    }
    const parts = value.split(",").map((part) => Number.parseFloat(part.trim()) / 255).filter(Number.isFinite);
    if (parts.length !== 3) {
      return fallback;
    }
    return parts.map((part) => clamp(part, 0, 1));
  }

  function syncPalette() {
    palette0 = parseRgbTriplet("--mood-primary-rgb", palette0);
    palette1 = parseRgbTriplet("--mood-secondary-rgb", palette1);
    palette2 = parseRgbTriplet("--mood-tertiary-rgb", palette2);
  }

  function currentPulseStrength() {
    const raw = getComputedStyle(document.body).getPropertyValue("--reply-pulse-strength").trim();
    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) ? clamp(parsed, 0, 1) : 0;
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.6);
    const width = Math.max(1, Math.floor(window.innerWidth * dpr));
    const height = Math.max(1, Math.floor(window.innerHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    gl.viewport(0, 0, canvas.width, canvas.height);
  }

  window.addEventListener("mousemove", (event) => {
    mouseX = event.clientX;
    mouseY = window.innerHeight - event.clientY;
  });
  window.addEventListener("resize", resize);
  resize();
  syncPalette();

  function render(time) {
    if (time - lastPaletteSync > 420) {
      syncPalette();
      lastPaletteSync = time;
    }

    gl.useProgram(program);
    gl.uniform2f(locResolution, canvas.width, canvas.height);
    gl.uniform1f(locTime, time * 0.001);
    gl.uniform4f(locMouse, mouseX, mouseY, 0, 0);
    gl.uniform1f(locPulse, currentPulseStrength());
    gl.uniform3f(locPalette0, palette0[0], palette0[1], palette0[2]);
    gl.uniform3f(locPalette1, palette1[0], palette1[1], palette1[2]);
    gl.uniform3f(locPalette2, palette2[0], palette2[1], palette2[2]);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    requestAnimationFrame(render);
  }

  requestAnimationFrame(render);
})();
