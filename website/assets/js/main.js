// ─── TilinX Web - Main ────────────────────────────────

document.addEventListener("DOMContentLoaded", function() {
  // ── Snow Canvas (PURPLE SNOW) ──────────────────────
  var snowCanvas = document.getElementById("snow-canvas");
  if (snowCanvas) {
    var sx = snowCanvas.getContext("2d");
    var sw, sh, flakes = [], snowAngle = 0;

    function sresize() {
      sw = snowCanvas.width = window.innerWidth;
      sh = snowCanvas.height = window.innerHeight;
    }
    sresize();
    window.addEventListener("resize", sresize);

    for (var i = 0; i < 180; i++) {
      flakes.push({
        x: Math.random() * (sw || 1000),
        y: Math.random() * (sh || 1000),
        r: Math.random() * 3 + 1,
        speed: Math.random() * 1.2 + 0.4,
        wind: Math.random() * 0.4 - 0.2,
        opacity: Math.random() * 0.6 + 0.2,
      });
    }

    function drawSnow() {
      sx.clearRect(0, 0, sw, sh);
      snowAngle += 0.005;
      for (var i = 0; i < flakes.length; i++) {
        var f = flakes[i];
        f.y += f.speed;
        f.x += Math.sin(snowAngle + i) * 0.3 + f.wind;
        if (f.y > sh) { f.y = -f.r; f.x = Math.random() * sw; }
        if (f.x > sw + 5) f.x = -5;
        if (f.x < -5) f.x = sw + 5;
        sx.beginPath();
        sx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
        var purple = "rgba(180,80,255," + f.opacity + ")";
        sx.fillStyle = purple;
        sx.fill();
        // glow
        sx.beginPath();
        sx.arc(f.x, f.y, f.r * 3, 0, Math.PI * 2);
        sx.fillStyle = "rgba(180,80,255," + (f.opacity * 0.15) + ")";
        sx.fill();
      }
      requestAnimationFrame(drawSnow);
    }
    drawSnow();
  }

  // ── Canvas BG (Enhanced Matrix + Particles) ────────
  var canvas = document.getElementById("bg-canvas");
  if (canvas) {
    var ctx = canvas.getContext("2d");
    var w, h, particles = [];
    var matrixCols = [];
    var matrixChars = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモラリルレロ01";

    function resize() {
      w = canvas.width = window.innerWidth;
      h = canvas.height = window.innerHeight;
      // Rebuild matrix columns
      var colCount = Math.floor(w / 24);
      while (matrixCols.length < colCount) matrixCols.push(Math.random() * -h);
      matrixCols = matrixCols.slice(0, colCount);
    }
    resize();
    window.addEventListener("resize", resize);

    // More particles (120 instead of 60)
    for (var i = 0; i < 120; i++) {
      particles.push({
        x: Math.random() * (w || 1000),
        y: Math.random() * (h || 1000),
        vx: (Math.random() - 0.5) * 0.8,
        vy: (Math.random() - 0.5) * 0.8,
        r: Math.random() * 2.5 + 0.5,
        hue: Math.random() * 60 + 260, // purple range: 260-320
      });
    }

    function drawBg() {
      ctx.clearRect(0, 0, w, h);

      // Matrix rain columns (brighter)
      ctx.font = "16px monospace";
      for (var c = 0; c < matrixCols.length; c++) {
        var char = matrixChars[Math.floor(Math.random() * matrixChars.length)];
        ctx.fillStyle = "rgba(180,80,255,0.25)";
        ctx.fillText(char, c * 24, matrixCols[c]);
        ctx.fillStyle = "rgba(0,255,65,0.12)";
        ctx.fillText(char, c * 24 + 2, matrixCols[c] + 2);
        // extra glow
        ctx.fillStyle = "rgba(180,80,255,0.06)";
        ctx.fillText(char, c * 24 - 1, matrixCols[c] - 1);
        matrixCols[c] += 8 + Math.random() * 6;
        if (matrixCols[c] > h && Math.random() > 0.98) matrixCols[c] = Math.random() * -100;
      }

      // Floating particles (purple, brighter)
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(180,80,255,0.6)";
        ctx.fill();
        // glow
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 3, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(180,80,255,0.15)";
        ctx.fill();
        // inner glow
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * 0.5, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(200,150,255,0.9)";
        ctx.fill();
      }

      // Lines between particles (closer = stronger, brighter)
      for (var i = 0; i < particles.length; i++) {
        for (var j = i + 1; j < particles.length; j++) {
          var dx = particles[i].x - particles[j].x;
          var dy = particles[i].y - particles[j].y;
          var dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 150) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            var alpha = 0.18 * (1 - dist / 150);
            ctx.strokeStyle = "rgba(180,80,255," + alpha + ")";
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }
      }
      requestAnimationFrame(drawBg);
    }
    drawBg();
  }

  // ── Anti-devtools (Enhanced) ──────────────────────
  document.addEventListener("contextmenu", function(e) { e.preventDefault(); });
  document.addEventListener("dragstart", function(e) { e.preventDefault(); });
  document.addEventListener("copy", function(e) { e.preventDefault(); });
  document.addEventListener("cut", function(e) { e.preventDefault(); });
  document.addEventListener("paste", function(e) { e.preventDefault(); });
  document.addEventListener("selectstart", function(e) { e.preventDefault(); });

  // Devtools detection - multiple methods
  var devtoolsOpen = false;
  var devtoolsCount = 0;
  var devtoolsInterval = setInterval(function() {
    // Method 1: Size threshold
    var widthThreshold = window.outerWidth - window.innerWidth > 160;
    var heightThreshold = window.outerHeight - window.innerHeight > 160;
    // Method 2: Firebug check
    var firebug = window.Firebug && window.Firebug.chrome && window.Firebug.chrome.isInitialized;
    if (widthThreshold || heightThreshold || firebug) {
      devtoolsCount++;
      if (devtoolsCount >= 2 && !devtoolsOpen) {
        devtoolsOpen = true;
        document.body.innerHTML = "<div style=\"display:flex;align-items:center;justify-content:center;height:100vh;background:#000;color:rgba(180,80,255,0.8);font-family:monospace;font-size:18px;text-align:center;padding:30px\">" + String.fromCharCode(128274) + " DevTools detected. Please close and reload.</div>";
        clearInterval(devtoolsInterval);
      }
    } else {
      devtoolsCount = 0;
      devtoolsOpen = false;
    }
  }, 1000);

  // Block ALL developer shortcuts
  document.addEventListener("keydown", function(e) {
    // F12, Ctrl+Shift+I/C/J, Ctrl+U, Ctrl+S, Ctrl+Shift+U, Ctrl+Shift+P
    if (e.key === "F12" ||
        (e.ctrlKey && e.shiftKey && ["I","C","J","U","P"].indexOf(e.key) !== -1) ||
        (e.ctrlKey && ["u","s","S","U","p","P","r","R"].indexOf(e.key) !== -1) ||
        e.key === "PrintScreen" ||
        (e.ctrlKey && e.key === "PrintScreen")) {
      e.preventDefault();
      return false;
    }
  });

  // Disable print
  window.addEventListener("beforeprint", function(e) { e.preventDefault(); return false; });
  window.addEventListener("afterprint", function(e) { e.preventDefault(); return false; });

  // ── Session Keepalive ──────────────────────────────
  if (window.location.pathname === "/admin") {
    setInterval(function() {
      fetch("/api/status", { method: "GET", cache: "no-store" }).catch(function() {});
    }, 300000);
  }

  // ── Mobile Menu ────────────────────────────────────
  var menuBtn = document.getElementById("menu-btn");
  var navLinks = document.getElementById("nav-links");
  if (menuBtn && navLinks) {
    menuBtn.addEventListener("click", function() { navLinks.classList.toggle("open"); });
  }

  // ── Active nav link ────────────────────────────────
  var path = window.location.pathname;
  var links = document.querySelectorAll(".nav-links a");
  for (var li = 0; li < links.length; li++) {
    var a = links[li];
    var href = a.getAttribute("href");
    if (href === path || (href !== "/" && path.indexOf(href) === 0)) a.classList.add("active");
  }

  // ── Load Status ────────────────────────────────────
  var statusEl = document.getElementById("live-status");
  if (statusEl) loadStatus();

  // ── Health Indicator ──────────────────────────────
  var navRight = document.querySelector(".nav-right");
  if (navRight) {
    var dot = document.createElement("span");
    dot.id = "health-dot";
    dot.className = "health-dot dot-red";
    navRight.insertBefore(dot, navRight.firstChild);
    loadHealth();
  }
  setInterval(loadHealth, 30000);

  // ── Login ──────────────────────────────────────────
  var loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", function(e) {
      e.preventDefault();
      var pwd = document.getElementById("password").value;
      fetch("/api/login", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password: pwd}),
      }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.success) window.location.href = "/admin";
        else document.getElementById("login-error").style.display = "block";
      });
    });
  }

  // ── Contact Form ───────────────────────────────────
  var contactForm = document.getElementById("contact-form");
  if (contactForm) {
    contactForm.addEventListener("submit", function(e) {
      e.preventDefault();
      var data = {
        name: document.getElementById("cname").value,
        email: document.getElementById("cemail").value,
        message: document.getElementById("cmessage").value,
      };
      fetch("/api/contact", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data),
      }).then(function(r) { return r.json(); }).then(function(d) {
        contactForm.innerHTML = "<div style=\"text-align:center;padding:30px;color:var(--accent);font-family:monospace;font-size:16px;\">✅ " + d.message + "</div>";
      });
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

// ── Health Check ──────────────────────────────────
function loadHealth() {
  var dot = document.getElementById("health-dot");
  if (!dot) return;
  fetch("/api/status").then(function(r) {
    return r.json();
  }).then(function(d) {
    var cls = d.status === "operational" ? "dot-green" : "dot-red";
    dot.className = "health-dot " + cls;
  }).catch(function() {
    dot.className = "health-dot dot-red";
  });
}
