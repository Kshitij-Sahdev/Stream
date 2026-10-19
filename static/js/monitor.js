document.addEventListener("DOMContentLoaded", () => {
  const table = document.getElementById("jobs-table");
  const tbody = document.getElementById("jobs-tbody");
  const loading = document.getElementById("jobs-loading");
  const empty = document.getElementById("jobs-empty");
  const btnRefresh = document.getElementById("btn-manual-refresh");
  const refreshIndicator = document.getElementById("refresh-indicator");
  const healthDot = document.getElementById("health-dot");
  const healthText = document.getElementById("health-text");

  // Modal elements
  const modal = document.getElementById("diagnostic-modal");
  const modalErrorSummary = document.getElementById("modal-error-summary");
  const modalDiagLog = document.getElementById("modal-diagnostic-log");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnModalDone = document.getElementById("btn-modal-done");

  let pollInterval = null;

  function formatBytes(bytes) {
    if (!bytes) return "-";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function formatDate(isoStr) {
    if (!isoStr) return "-";
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Degraded");
      const data = await res.json();
      if (data.status === "healthy") {
        healthDot.className = "health-dot healthy";
        healthText.textContent = `FFmpeg: ${data.ffmpeg} | DB: ${data.database}`;
      } else {
        healthDot.className = "health-dot degraded";
        healthText.textContent = `Status: ${data.status} (FFmpeg: ${data.ffmpeg})`;
      }
    } catch (e) {
      healthDot.className = "health-dot degraded";
      healthText.textContent = "Health: Unreachable";
    }
  }

  async function fetchJobs() {
    try {
      const res = await fetch("/api/jobs");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const jobs = await res.json();

      loading.classList.add("hidden");

      if (jobs.length === 0) {
        empty.classList.remove("hidden");
        table.classList.add("hidden");
        return;
      }

      empty.classList.add("hidden");
      table.classList.remove("hidden");
      tbody.innerHTML = "";

      jobs.forEach((j) => {
        const tr = document.createElement("tr");

        const encTimeStr = j.encoding_duration_seconds != null ? `${j.encoding_duration_seconds}s` : "-";
        const sizeStr = formatBytes(j.total_output_size);
        const stageStr = j.stage || "queued";

        let actionsHtml = "";
        if (j.status === "READY") {
          actionsHtml = `<a href="/watch/${j.video_id}" class="btn btn-primary btn-sm">Watch</a>`;
        } else if (j.status === "FAILED") {
          actionsHtml = `<button class="btn btn-secondary btn-sm btn-diag" data-job='${JSON.stringify({
            id: j.id,
            error: j.error_summary,
            diag: j.diagnostic_log,
          })}'>Logs</button>`;
        } else {
          actionsHtml = `<span class="badge badge-${j.status}">${j.progress}%</span>`;
        }

        tr.innerHTML = `
          <td>
            <strong>${j.id.substring(0, 8)}...</strong>
            <br><small style="color:var(--text-muted)">Video: ${j.video_id.substring(0, 8)}...</small>
          </td>
          <td><span class="status-badge status-${j.status}">${j.status}</span></td>
          <td><code>${stageStr}</code></td>
          <td>${encTimeStr}</td>
          <td>${sizeStr}</td>
          <td>${formatDate(j.created_at)}</td>
          <td>${actionsHtml}</td>
        `;

        const diagBtn = tr.querySelector(".btn-diag");
        if (diagBtn) {
          diagBtn.addEventListener("click", () => {
            const jobData = JSON.parse(diagBtn.getAttribute("data-job"));
            showDiagnosticModal(jobData);
          });
        }

        tbody.appendChild(tr);
      });
    } catch (e) {
      console.warn("Failed to fetch jobs:", e);
    }
  }

  function showDiagnosticModal(data) {
    modalErrorSummary.textContent = data.error || "No error summary recorded.";
    modalDiagLog.textContent = data.diag || "No detailed diagnostic trace available.";
    modal.classList.remove("hidden");
  }

  function closeModal() {
    modal.classList.add("hidden");
  }

  btnCloseModal.addEventListener("click", closeModal);
  btnModalDone.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => {
      if (document.visibilityState === "visible") {
        fetchJobs();
        checkHealth();
      }
    }, 4000);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      refreshIndicator.textContent = "Auto-refresh: On";
      fetchJobs();
      checkHealth();
    } else {
      refreshIndicator.textContent = "Auto-refresh: Paused (tab hidden)";
    }
  });

  btnRefresh.addEventListener("click", () => {
    fetchJobs();
    checkHealth();
  });

  checkHealth();
  fetchJobs();
  startPolling();
});
