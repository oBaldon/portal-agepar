# apps/bff/app/games/snake.py
from fastapi import APIRouter
from starlette.responses import HTMLResponse

router = APIRouter(prefix="/api/games/snake", tags=["games:snake"])

@router.get("/ui")
async def snake_ui():
    html = """
<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Snake — Possibilidades</title>
<style>
  :root { --card:#fff; --ink:#0f172a; --muted:#475569; --line:#e2e8f0; --accent:#0284c7; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell;
         background:#f8fafc; color:var(--ink); padding:20px; }
  .wrap { max-width: 960px; margin: 0 auto; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:16px; padding:16px; }
  .head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:12px; }
  .title { font-weight:700; font-size:18px; letter-spacing:.2px; }
  .tag { font-size:11px; border:1px solid var(--line); border-radius:999px; padding:2px 8px; color:var(--muted); background:#fff; }
  .row { display:grid; grid-template-columns: 1fr 340px; gap:16px; }
  @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
  canvas { background:#0b1020; border-radius:12px; width:100%; height:auto; image-rendering: pixelated; }
  .panel { display:grid; gap:12px; }
  .kv { display:flex; gap:8px; align-items:center; justify-content:space-between; }
  .kv .label { color:var(--muted); font-size:13px; }
  .kv .val { font-weight:700; }
  .btns { display:flex; flex-wrap:wrap; gap:8px; }
  button {
    padding:8px 12px; border-radius:10px; border:1px solid var(--line); background:#fff; cursor:pointer;
  }
  button.primary { background: var(--accent); color:white; border-color:var(--accent); }
  button:disabled { opacity:.5; cursor:not-allowed; }
  .hint { color:var(--muted); font-size:13px; }
  .select { display:flex; gap:6px; flex-wrap:wrap; }
  .select > button[aria-pressed="true"] { background:#e0f2fe; border-color:#bae6fd; color:#075985; font-weight:600; }
  .footer { margin-top:10px; font-size:12px; color:var(--muted); }
</style>

<div class="wrap">
  <div class="head">
    <div class="title">Possibilidades • Snake (Jogo da Cobrinha)</div>
    <span class="tag">BFF + iframe</span>
  </div>

  <div class="row">
    <div class="card">
      <canvas id="cv" width="600" height="600" aria-label="tabuleiro do jogo"></canvas>
      <div class="footer">Controles: setas do teclado (↑ ↓ ← →) ou W A S D. P/pausar: Espaço.</div>
    </div>

    <div class="card panel">
      <div class="kv"><span class="label">Status</span><span id="st" class="val">pronto</span></div>
      <div class="kv"><span class="label">Pontuação</span><span id="sc" class="val">0</span></div>
      <div class="kv"><span class="label">Recorde (sessão)</span><span id="hi" class="val">0</span></div>

      <div>
        <div class="label">Dificuldade</div>
        <div class="select" id="diff">
          <button data-sp="150">Leve</button>
          <button data-sp="110" aria-pressed="true">Normal</button>
          <button data-sp="80">Rápido</button>
          <button data-sp="60">Insano</button>
        </div>
      </div>

      <div>
        <div class="label">Tamanho da grade</div>
        <div class="select" id="grid">
          <button data-g="16">16x16</button>
          <button data-g="20" aria-pressed="true">20x20</button>
          <button data-g="24">24x24</button>
          <button data-g="32">32x32</button>
        </div>
      </div>

      <div class="btns">
        <button class="primary" id="btnStart">Iniciar</button>
        <button id="btnPause" disabled>Pausar</button>
        <button id="btnReset">Resetar</button>
      </div>

      <div class="hint">
        Dica: redimensione a janela/iframe — o canvas se ajusta automaticamente, mantendo pixels “crisp”.
      </div>
    </div>
  </div>
</div>

<script>
(() => {
  const cv = document.getElementById('cv');
  const ctx = cv.getContext('2d');
  const $ = (id) => document.getElementById(id);
  const st = $('st'), sc = $('sc'), hi = $('hi');
  const btnStart = $('btnStart'), btnPause = $('btnPause'), btnReset = $('btnReset');
  const diffSel = document.getElementById('diff');
  const gridSel = document.getElementById('grid');

  // Estado do jogo
  let grid = 20;          // células por lado
  let speed = 110;        // ms por tick
  let cell;               // pixels por célula (derivado do tamanho do canvas)
  let snake, dir, nextDir, food, score, best = 0, running = false, timer = null, dead = false;

  // Ajuste responsivo do canvas (quadrado, até 600px)
    function fitCanvas() {
        const container = cv.parentElement;
        // se ainda não houver largura calculada, usa um fallback seguro (600)
        const available = Math.max(300, Math.min(600, Math.floor((container?.clientWidth || 600))));
        const dpr = Math.min(window.devicePixelRatio || 1, 2);

        cv.style.width = available + 'px';
        cv.style.height = available + 'px';
        cv.width = Math.floor(available * dpr);
        cv.height = Math.floor(available * dpr);

        cell = Math.max(4, Math.floor(cv.width / grid));
        draw();
    }

  window.addEventListener('resize', fitCanvas);

  // Utilidades
  const randInt = (n) => Math.floor(Math.random() * n);
  const eq = (a,b) => a.x === b.x && a.y === b.y;

  function placeFood() {
    let p;
    do {
      p = { x: randInt(grid), y: randInt(grid) };
    } while (snake.some(s => eq(s, p)));
    food = p;
  }

  function reset() {
    score = 0; dead = false; running = false; clearInterval(timer); timer = null;
    dir = {x:1, y:0}; nextDir = {x:1, y:0};
    const mid = Math.floor(grid/2);
    snake = [{x:mid-1,y:mid}, {x:mid-2,y:mid}];
    placeFood();
    st.textContent = 'pronto';
    sc.textContent = String(score);
    btnStart.disabled = false;
    btnPause.disabled = true;
    draw();
  }

  function start() {
    if (!snake || snake.length === 0 || dead) {
        reset(); // garante estado inicial válido
    }
    if (running) return;
    running = true; dead = false;
    st.textContent = 'jogando';
    btnStart.disabled = true;
    btnPause.disabled = false;
    clearInterval(timer);
    timer = setInterval(tick, speed);
  }

  function pauseToggle() {
    if (!running) return;
    if (timer) {
      clearInterval(timer);
      timer = null;
      st.textContent = 'pausado';
      btnPause.textContent = 'Retomar';
    } else {
      st.textContent = 'jogando';
      btnPause.textContent = 'Pausar';
      timer = setInterval(tick, speed);
    }
  }

  function gameOver() {
    running = false; dead = true;
    clearInterval(timer); timer = null;
    st.textContent = 'game over';
    btnStart.disabled = false;
    btnPause.disabled = true;
    if (score > best) { best = score; hi.textContent = String(best); }
    draw(true);
  }

  function setDir(nx, ny) {
    // evita 180°
    if (nx === -dir.x && ny === -dir.y) return;
    nextDir = {x:nx, y:ny};
  }

  function tick() {
    dir = nextDir;
    const head = { x: snake[0].x + dir.x, y: snake[0].y + dir.y };

    // colisão com paredes
    if (head.x < 0 || head.x >= grid || head.y < 0 || head.y >= grid) return gameOver();
    // colisão com corpo
    if (snake.some(s => eq(s, head))) return gameOver();

    snake.unshift(head);

    if (eq(head, food)) {
      score++;
      sc.textContent = String(score);
      placeFood();
    } else {
      snake.pop();
    }

    draw();
  }

  function draw(end=false) {
    // fundo
    ctx.fillStyle = '#081024';
    ctx.fillRect(0,0,cv.width,cv.height);

    // grid leve
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    for (let i=1;i<grid;i++){
      const p = i*cell;
      ctx.beginPath(); ctx.moveTo(p,0); ctx.lineTo(p,grid*cell); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0,p); ctx.lineTo(grid*cell,p); ctx.stroke();
    }

    // comida
    const pad = Math.max(1, Math.floor(cell*0.1));
    ctx.fillStyle = '#ef4444';
    ctx.fillRect(food.x*cell+pad, food.y*cell+pad, cell-2*pad, cell-2*pad);

    // cobra
    for (let i=0;i<snake.length;i++){
      const s = snake[i];
      const t = i === 0 ? 1 : (0.65 + 0.35*(1 - i/snake.length));
      ctx.fillStyle = end ? 'rgba(239,68,68,0.8)' : `rgba(56,189,248,${t})`;
      ctx.fillRect(s.x*cell+1, s.y*cell+1, cell-2, cell-2);
    }
  }

  // Controles
  window.addEventListener('keydown', (e) => {
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); pauseToggle(); return; }
    if (['arrowup','w'].includes(k)) { e.preventDefault(); setDir(0,-1); }
    if (['arrowdown','s'].includes(k)) { e.preventDefault(); setDir(0, 1); }
    if (['arrowleft','a'].includes(k)) { e.preventDefault(); setDir(-1,0); }
    if (['arrowright','d'].includes(k)) { e.preventDefault(); setDir(1, 0); }
  });

  // UI: dificuldade
  diffSel.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    [...diffSel.children].forEach(x => x.removeAttribute('aria-pressed'));
    b.setAttribute('aria-pressed','true');
    speed = Number(b.dataset.sp || 110);
    if (running && timer) { clearInterval(timer); timer = setInterval(tick, speed); }
  });

  // UI: grid
  gridSel.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    [...gridSel.children].forEach(x => x.removeAttribute('aria-pressed'));
    b.setAttribute('aria-pressed','true');
    grid = Number(b.dataset.g || 20);
    fitCanvas();
    reset();
  });

  btnStart.addEventListener('click', start);
  btnPause.addEventListener('click', pauseToggle);
  btnReset.addEventListener('click', () => { reset(); st.textContent='pronto'; });

// boot
    function boot() {
    fitCanvas();
        reset();
        // roda um ajuste pós-layout no próximo frame
        requestAnimationFrame(() => { fitCanvas(); draw(); });
    }
    boot();

})();
</script>
"""
    return HTMLResponse(html)
