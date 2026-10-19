document.addEventListener("DOMContentLoaded", () => {
  const grid = document.getElementById("library-grid");
  const loading = document.getElementById("library-loading");
  const empty = document.getElementById("library-empty");
  const alertBox = document.getElementById("library-alert");

  let pollTimer = null;

  function showAlert(msg, isError = true) {
    alertBox.textContent = msg;
    alertBox.className = isError ? "alert alert-error" : "alert alert-success";
    alertBox.classList.remove("hidden");
  }

  function hideAlert() {
    alertBox.classList.add("hidden");
  }

  function formatDuration(sec) {
    if (!sec) return "";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  async function deleteVideo(videoId, title) {
    if (!confirm(`Are you sure you want to delete "${title}"? This will remove all streaming files.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/videos/${videoId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Delete failed with HTTP ${res.status}`);
      }
      fetchVideos();
    } catch (err) {
      showAlert(err.message, true);
    }
  }

  async function fetchVideos() {
    try {
      const res = await fetch("/api/videos");
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch video library`);
      const videos = await res.json();

      loading.classList.add("hidden");
      hideAlert();

      if (videos.length === 0) {
        empty.classList.remove("hidden");
        grid.classList.add("hidden");
        return;
      }

      empty.classList.add("hidden");
      grid.classList.remove("hidden");
      grid.innerHTML = "";

      let hasPending = false;

      videos.forEach((v) => {
        if (v.status === "QUEUED" || v.status === "PROCESSING") {
          hasPending = true;
        }

        const card = document.createElement("div");
        card.className = "video-card";

        const durationStr = v.duration_seconds ? formatDuration(v.duration_seconds) : "";
        const sizeStr = formatBytes(v.file_size);
        const resolutionStr = v.width && v.height ? `${v.width}x${v.height}` : "";

        let actionBtn = "";
        if (v.status === "READY") {
          actionBtn = `<a href="/watch/${v.id}" class="btn btn-primary btn-sm">Watch</a>`;
        } else if (v.status === "FAILED") {
          actionBtn = `<a href="/jobs" class="btn btn-secondary btn-sm" title="View failure in Monitor">Diagnostics</a>`;
        } else {
          actionBtn = `<a href="/jobs" class="btn btn-secondary btn-sm">Processing...</a>`;
        }

        card.innerHTML = `
          <div class="video-card-thumb">
            <div class="thumb-placeholder">▶</div>
            <span class="badge badge-${v.status} video-card-badge">${v.status}</span>
          </div>
          <div class="video-card-body">
            <h3 class="video-card-title">${v.title || "Untitled Video"}</h3>
            <div class="video-card-meta">
              <span>${sizeStr}</span>
              ${durationStr ? `<span>${durationStr}</span>` : ""}
              ${resolutionStr ? `<span>${resolutionStr}</span>` : ""}
            </div>
            <div class="video-card-actions">
              ${actionBtn}
              <button class="btn-icon btn-delete" data-id="${v.id}" data-title="${v.title}" aria-label="Delete video" title="Delete video">
                🗑️
              </button>
            </div>
          </div>
        `;

        card.querySelector(".btn-delete").addEventListener("click", (e) => {
          e.preventDefault();
          const btn = e.currentTarget;
          deleteVideo(btn.getAttribute("data-id"), btn.getAttribute("data-title"));
        });

        grid.appendChild(card);
      });

      // Polling lifecycle: if videos are queued/processing, poll again
      if (hasPending && !pollTimer) {
        pollTimer = setTimeout(() => {
          pollTimer = null;
          fetchVideos();
        }, 3000);
      }
    } catch (err) {
      loading.classList.add("hidden");
      showAlert(err.message, true);
    }
  }

  fetchVideos();
});
