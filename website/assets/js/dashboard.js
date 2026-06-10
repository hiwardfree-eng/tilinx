// ─── TilinX Admin Dashboard JS ─────────────────────────

async function loadAdminData() {
  try {
    const r = await fetch("/api/logs?limit=30");
    const logs = await r.json();
    const tbody = document.getElementById("logs-body");
    if (!tbody) return;
    tbody.innerHTML = logs.map(l => `
      <tr>
        <td><span class="tag ${l.level === 'warn' ? 'badge-red' : l.level === 'info' ? 'badge-green' : 'badge-purple'}">${l.level}</span></td>
        <td>${l.event}</td>
        <td>${l.detail || '—'}</td>
        <td>${new Date(l.time).toLocaleString()}</td>
      </tr>
    `).join("");
  } catch {}
}

async function loadStatus() {
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    document.getElementById("admin-cpu").textContent = d.cpu + "%";
    document.getElementById("admin-ram").textContent = d.ram + "%";
    document.getElementById("admin-disk").textContent = d.disk + "%";
    document.getElementById("admin-uptime").textContent = formatUptime(d.uptime);
  } catch {}
}

function formatUptime(s) {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

document.addEventListener("DOMContentLoaded", () => {
  loadAdminData();
  loadStatus();
  setInterval(loadAdminData, 10000);
  setInterval(loadStatus, 15000);

  document.getElementById("logout-btn")?.addEventListener("click", async () => {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  });
});
