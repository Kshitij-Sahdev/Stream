document.addEventListener("DOMContentLoaded", () => {
  const video = document.getElementById("video-player");
  const qualitySelect = document.getElementById("quality-select");
  const metricResolution = document.getElementById("metric-resolution");
  const metricBitrate = document.getElementById("metric-bitrate");
  const metricEngine = document.getElementById("metric-engine");
  const playerError = document.getElementById("player-error");
  const playerErrorMessage = document.getElementById("player-error-message");
  const btnRetry = document.getElementById("btn-player-retry");
  const renditionsList = document.getElementById("renditions-list");

  if (!video) return;

  const videoId = video.getAttribute("data-video-id");
  const playlistUrl = `/stream/${videoId}/master.m3u8`;

  let hlsInstance = null;

  function showPlayerError(msg) {
    playerErrorMessage.textContent = msg;
    playerError.classList.remove("hidden");
  }

  function hidePlayerError() {
    playerError.classList.add("hidden");
  }

  function formatBitrate(bps) {
    if (!bps) return "-";
    if (bps >= 1000000) return (bps / 1000000).toFixed(2) + " Mbps";
    return Math.round(bps / 1000) + " kbps";
  }

  function initPlayer() {
    hidePlayerError();

    // Strategy 1: hls.js (Chrome, Firefox, Edge, Android Chrome, etc.)
    if (window.Hls && Hls.isSupported()) {
      metricEngine.textContent = "Engine: HLS.js";

      if (hlsInstance) {
        hlsInstance.destroy();
      }

      hlsInstance = new Hls({
        debug: false,
        enableWorker: true,
        lowLatencyMode: false,
      });

      hlsInstance.loadSource(playlistUrl);
      hlsInstance.attachMedia(video);

      hlsInstance.on(Hls.Events.MANIFEST_PARSED, (event, data) => {
        qualitySelect.innerHTML = '<option value="-1">Auto (ABR)</option>';
        data.levels.forEach((lvl, idx) => {
          const opt = document.createElement("option");
          opt.value = idx;
          const label = lvl.height ? `${lvl.height}p (${formatBitrate(lvl.bitrate)})` : `Level ${idx}`;
          opt.textContent = label;
          qualitySelect.appendChild(opt);
        });
        qualitySelect.disabled = false;
      });

      hlsInstance.on(Hls.Events.LEVEL_SWITCHED, (event, data) => {
        const levelIdx = data.level;
        const level = hlsInstance.levels[levelIdx];
        if (level) {
          metricResolution.textContent = `Res: ${level.width}x${level.height}`;
          metricBitrate.textContent = `Bitrate: ${formatBitrate(level.bitrate)}`;
        }
      });

      hlsInstance.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              console.error("Fatal network error in HLS stream:", data);
              showPlayerError("Network error while loading video stream segments.");
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              console.error("Fatal media decoding error in stream:", data);
              hlsInstance.recoverMediaError();
              break;
            default:
              console.error("Unrecoverable HLS error:", data);
              showPlayerError("Unrecoverable playback error occurred.");
              hlsInstance.destroy();
              break;
          }
        }
      });

      qualitySelect.addEventListener("change", () => {
        const chosen = parseInt(qualitySelect.value, 10);
        hlsInstance.currentLevel = chosen;
        if (chosen === -1) {
          metricBitrate.textContent = "Bitrate: Auto (ABR)";
        }
      });
    }
    // Strategy 2: Native Safari / iOS HLS
    else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      metricEngine.textContent = "Engine: Native HLS";
      video.src = playlistUrl;
      qualitySelect.innerHTML = '<option value="-1">Auto (System Controlled)</option>';
      qualitySelect.disabled = true;

      video.addEventListener("loadedmetadata", () => {
        if (video.videoWidth && video.videoHeight) {
          metricResolution.textContent = `Res: ${video.videoWidth}x${video.videoHeight}`;
        }
      });

      video.addEventListener("error", () => {
        showPlayerError("Native browser video engine failed to play stream.");
      });
    } else {
      metricEngine.textContent = "Engine: Unsupported";
      showPlayerError("Your browser does not support HLS streaming playback.");
    }
  }

  // Load detailed renditions from backend API for telemetry card
  async function loadVideoDetails() {
    try {
      const res = await fetch(`/api/videos/${videoId}`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.renditions && data.renditions.length > 0) {
        renditionsList.innerHTML = "";
        data.renditions.forEach((r) => {
          const chip = document.createElement("div");
          chip.className = "rendition-chip";
          chip.innerHTML = `
            <strong>${r.name}</strong> &bull; ${r.width}x${r.height} &bull; ${formatBitrate(r.bitrate)}
            <br><small style="color:var(--text-muted)">${r.segment_count} segments (${(r.size_bytes / (1024 * 1024)).toFixed(2)} MB)</small>
          `;
          renditionsList.appendChild(chip);
        });
      } else {
        renditionsList.innerHTML = '<span style="color:var(--text-muted)">No renditions recorded yet.</span>';
      }
    } catch (e) {
      renditionsList.innerHTML = '<span style="color:var(--text-muted)">Renditions unavailable.</span>';
    }
  }

  btnRetry.addEventListener("click", () => {
    initPlayer();
  });

  initPlayer();
  loadVideoDetails();
});
