// ─── TilinX Web - Main ────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {

  // ── Canvas BG (from the original design) ────────────
  const canvas = document.getElementById("bg-canvas");
  if (canvas) {
    const ctx = canvas.getContext("2d");
    let w, h, particles = [];

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < 60; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        r: Math.random() * 2 + 0.5,
      });
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      particles.forEach(p => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(130,0,255,0.4)";
        ctx.fill();
      });
      // lines
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(130,0,255,${0.15 * (1 - dist / 120)})`;
            ctx.stroke();
          }
        }
      }
      requestAnimationFrame(draw);
    }
    draw();
  }

  // ── Anti-devtools ──────────────────────────────────
  // Disable right click
  document.addEventListener("contextmenu", e => e.preventDefault());

  // Detect devtools (basic)
  let devtoolsOpen = false;
  setInterval(() => {
    const widthThreshold = window.outerWidth - window.innerWidth > 160;
    const heightThreshold = window.outerHeight - window.innerHeight > 160;
    if (widthThreshold || heightThreshold) {
      if (!devtoolsOpen) {
        devtoolsOpen = true;
        document.body.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100vh;background:#000;color:rgba(180,80,255,0.8);font-family:monospace;font-size:18px;text-align:center;padding:30px">🔒 DevTools detected. Please close and reload.</div>`;
      }
    } else {
      devtoolsOpen = false;
    }
  }, 1000);

  // Keyboard shortcuts
  document.addEventListener("keydown", e => {
    if (e.key === "F12" || (e.ctrlKey && e.shiftKey && ["I","C","J"].includes(e.key)) ||
        (e.ctrlKey && e.key === "u")) {
      e.preventDefault();
    }
  });

  // ── Mobile Menu ────────────────────────────────────
  const menuBtn = document.getElementById("menu-btn");
  const navLinks = document.getElementById("nav-links");
  if (menuBtn && navLinks) {
    menuBtn.addEventListener("click", () => navLinks.classList.toggle("open"));
  }

  // ── Active nav link ────────────────────────────────
  const path = window.location.pathname;
  document.querySelectorAll(".nav-links a").forEach(a => {
    if (a.getAttribute("href") === path) a.classList.add("active");
  });

  // ── Load Status ────────────────────────────────────
  const statusEl = document.getElementById("live-status");
  if (statusEl) loadStatus();

  // ── Login ──────────────────────────────────────────
  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const pwd = document.getElementById("password").value;
      const r = await fetch("/api/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password: pwd}),
      });
      const d = await r.json();
      if (d.success) window.location.href = "/admin";
      else document.getElementById("login-error").style.display = "block";
    });
  }

  // ── Contact Form ───────────────────────────────────
  const contactForm = document.getElementById("contact-form");
  if (contactForm) {
    contactForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = {
        name: document.getElementById("cname").value,
        email: document.getElementById("cemail").value,
        message: document.getElementById("cmessage").value,
      };
      const r = await fetch("/api/contact", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
      });
      const d = await r.json();
      contactForm.innerHTML = `<div style="text-align:center;padding:30px;color:var(--accent);font-family:monospace;font-size:16px;">✅ ${d.message}</div>`;
    });
  }
});

async function loadStatus() {
  const el = document.getElementById("live-status");
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    const cls = d.status === "operational" ? "dot-green" : "dot-red";
    el.innerHTML = `<span class="status-badge"><span class="dot ${cls}"></span> ${d.status.toUpperCase()}</span>`;
    document.getElementById("stat-uptime").textContent = formatUptime(d.uptime);
    document.getElementById("stat-cpu").textContent = d.cpu + "%";
    document.getElementById("stat-ram").textContent = d.ram + "%";
    document.getElementById("stat-disk").textContent = d.disk + "%";
  } catch {
    el.innerHTML = `<span class="status-badge"><span class="dot dot-red"></span> OFFLINE</span>`;
  }
}

function formatUptime(s) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}
