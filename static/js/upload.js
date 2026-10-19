document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("file-input");
  const dropZone = document.getElementById("drop-zone");
  const selectedFileInfo = document.getElementById("selected-file-info");
  const selectedFileName = document.getElementById("selected-file-name");
  const selectedFileSize = document.getElementById("selected-file-size");
  const btnRemoveFile = document.getElementById("btn-remove-file");
  const btnSubmit = document.getElementById("btn-submit-upload");
  const progressContainer = document.getElementById("upload-progress-container");
  const progressFill = document.getElementById("progress-bar-fill");
  const progressPercentage = document.getElementById("progress-percentage");
  const progressStageLabel = document.getElementById("progress-stage-label");
  const uploadError = document.getElementById("upload-error");

  const uploadCard = document.getElementById("upload-card");
  const postUploadCard = document.getElementById("post-upload-card");
  const postStatusBadge = document.getElementById("post-status-badge");
  const postVideoTitle = document.getElementById("post-video-title");
  const postStatusMessage = document.getElementById("post-status-message");
  const postJobId = document.getElementById("post-job-id");
  const postJobStage = document.getElementById("post-job-stage");
  const linkToWatch = document.getElementById("link-to-watch");

  let selectedFile = null;
  let jobPollInterval = null;

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function showError(msg) {
    uploadError.textContent = msg;
    uploadError.classList.remove("hidden");
  }

  function hideError() {
    uploadError.classList.add("hidden");
  }

  function handleFileSelected(file) {
    hideError();
    if (!file) return;

    // Check size limit: 500 MB
    const maxSize = 500 * 1024 * 1024;
    if (file.size > maxSize) {
      showError(`File size (${formatBytes(file.size)}) exceeds the maximum allowed 500 MB limit.`);
      resetFile();
      return;
    }

    selectedFile = file;
    selectedFileName.textContent = file.name;
    selectedFileSize.textContent = formatBytes(file.size);
    selectedFileInfo.classList.remove("hidden");
    dropZone.classList.add("hidden");
    btnSubmit.disabled = false;

    const titleInput = document.getElementById("video-title");
    if (!titleInput.value) {
      titleInput.value = file.name.replace(/\.[^/.]+$/, "");
    }
  }

  function resetFile() {
    selectedFile = null;
    fileInput.value = "";
    selectedFileInfo.classList.add("hidden");
    dropZone.classList.remove("hidden");
    btnSubmit.disabled = true;
  }

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelected(e.target.files[0]);
    }
  });

  btnRemoveFile.addEventListener("click", resetFile);

  // Drag and drop handlers
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("dragover");
    });
  });

  dropZone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });

  // Form submission via XMLHttpRequest for progress reporting
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    hideError();
    btnSubmit.disabled = true;
    progressContainer.classList.remove("hidden");
    progressFill.style.width = "0%";
    progressPercentage.textContent = "0%";
    progressStageLabel.textContent = "Uploading video...";

    const formData = new FormData();
    formData.append("file", selectedFile);
    const titleVal = document.getElementById("video-title").value.trim();
    if (titleVal) {
      formData.append("title", titleVal);
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/videos", true);

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable) {
        const percent = Math.round((evt.loaded / evt.total) * 100);
        progressFill.style.width = percent + "%";
        progressPercentage.textContent = percent + "%";
        if (percent === 100) {
          progressStageLabel.textContent = "Server received upload. Initializing job...";
        }
      }
    };

    xhr.onload = () => {
      if (xhr.status === 201) {
        try {
          const resp = JSON.parse(xhr.responseText);
          showPostUpload(resp);
        } catch (err) {
          showError("Unexpected server response format.");
          btnSubmit.disabled = false;
        }
      } else {
        let errorDetail = `Upload failed with HTTP ${xhr.status}`;
        try {
          const errData = JSON.parse(xhr.responseText);
          if (errData.detail) errorDetail = errData.detail;
        } catch (_) {}
        showError(errorDetail);
        btnSubmit.disabled = false;
      }
    };

    xhr.onerror = () => {
      showError("Network error occurred during upload. Please check your connection.");
      btnSubmit.disabled = false;
    };

    xhr.send(formData);
  });

  function showPostUpload(data) {
    uploadCard.classList.add("hidden");
    postUploadCard.classList.remove("hidden");

    postVideoTitle.textContent = data.title;
    postJobId.textContent = data.job_id;
    postJobStage.textContent = "queued";
    postStatusBadge.textContent = "QUEUED";
    postStatusBadge.className = "status-badge status-QUEUED";

    pollJobStatus(data.job_id, data.video_id);
  }

  function pollJobStatus(jobId, videoId) {
    if (jobPollInterval) clearInterval(jobPollInterval);

    jobPollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();

        postStatusBadge.textContent = job.status;
        postStatusBadge.className = `status-badge status-${job.status}`;
        postJobStage.textContent = job.stage || "processing";

        if (job.status === "READY") {
          clearInterval(jobPollInterval);
          postStatusMessage.textContent = `Transcoding complete! Video ready for multi-bitrate HLS streaming (took ${job.encoding_duration_seconds}s).`;
          linkToWatch.href = `/watch/${videoId}`;
          linkToWatch.classList.remove("hidden");
        } else if (job.status === "FAILED") {
          clearInterval(jobPollInterval);
          postStatusMessage.textContent = `Transcoding failed: ${job.error_summary || "An unexpected error occurred."}`;
        } else if (job.status === "PROCESSING") {
          postStatusMessage.textContent = `FFmpeg is transcoding renditions (stage: ${job.stage})...`;
        }
      } catch (err) {
        console.warn("Polling error:", err);
      }
    }, 2000);
  }
});
