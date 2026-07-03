const form = document.querySelector("#resizeForm");
const dropZone = document.querySelector("#dropZone");
const imageInput = document.querySelector("#imageInput");
const chooseButton = document.querySelector("#chooseButton");
const processButton = document.querySelector("#processButton");
const fileCount = document.querySelector("#fileCount");
const fileList = document.querySelector("#fileList");
const statusMessage = document.querySelector("#statusMessage");
const outputModeInputs = document.querySelectorAll('input[name="outputMode"]');

const MAX_TOTAL_UPLOAD_BYTES = 4 * 1024 * 1024;
const MAX_FILE_COUNT = 12;

let selectedFiles = [];
const previewUrls = new Map();

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setStatus(message, type = "") {
  statusMessage.textContent = message;
  statusMessage.className = `status-message${type ? ` is-${type}` : ""}`;
}

function setProcessLabel(isBusy) {
  processButton.innerHTML = isBusy
    ? '<span class="loader" aria-hidden="true"></span> Memproses...'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 3h-2v10.17l-3.59-3.58L6 11l6 6 6-6-1.41-1.41L13 13.17V3ZM5 19h14v2H5v-2Z"></path></svg> Proses & Download';
}

function setBusy(isBusy) {
  form.classList.toggle("is-busy", isBusy);
  processButton.disabled = isBusy || selectedFiles.length === 0;
  chooseButton.disabled = isBusy;
  setProcessLabel(isBusy);
}

function selectedBytes() {
  return selectedFiles.reduce((total, file) => total + file.size, 0);
}

function outputMode() {
  return document.querySelector('input[name="outputMode"]:checked')?.value || "zip";
}

function updateOutputMode() {
  const imageOption = document.querySelector('input[name="outputMode"][value="image"]');
  const zipOption = document.querySelector('input[name="outputMode"][value="zip"]');

  if (selectedFiles.length > 2) {
    imageOption.disabled = true;
    zipOption.checked = true;
  } else {
    imageOption.disabled = false;
  }
}

function syncInputFiles() {
  const transfer = new DataTransfer();
  selectedFiles.forEach((file) => transfer.items.add(file));
  imageInput.files = transfer.files;
}

function addFiles(files) {
  const incoming = Array.from(files).filter((file) => /^image\/(jpeg|png)$/.test(file.type));
  let skippedByLimit = 0;

  incoming.forEach((file) => {
    const key = `${file.name}-${file.size}-${file.lastModified}`;
    const exists = selectedFiles.some(
      (item) => `${item.name}-${item.size}-${item.lastModified}` === key
    );

    if (exists) {
      return;
    }

    if (
      selectedFiles.length + 1 > MAX_FILE_COUNT ||
      selectedBytes() + file.size > MAX_TOTAL_UPLOAD_BYTES
    ) {
      skippedByLimit += 1;
      return;
    }

    selectedFiles.push(file);
  });

  syncInputFiles();
  updateOutputMode();
  renderFiles();

  if (skippedByLimit > 0) {
    setStatus("Maksimal 12 gambar atau total 4 MB per proses di Vercel.", "error");
  } else if (files.length > 0 && incoming.length === 0) {
    setStatus("Format gambar harus JPG, JPEG, atau PNG.", "error");
  } else if (incoming.length > 0) {
    setStatus("");
  }
}

function removeFile(index) {
  const [removed] = selectedFiles.splice(index, 1);
  const key = `${removed.name}-${removed.size}-${removed.lastModified}`;

  if (previewUrls.has(key)) {
    URL.revokeObjectURL(previewUrls.get(key));
    previewUrls.delete(key);
  }

  syncInputFiles();
  updateOutputMode();
  renderFiles();
}

function renderFiles() {
  updateOutputMode();
  fileList.innerHTML = "";
  fileCount.textContent =
    selectedFiles.length === 0
      ? "Belum ada gambar dipilih"
      : `${selectedFiles.length} gambar dipilih - ${formatBytes(selectedBytes())}`;
  processButton.disabled = selectedFiles.length === 0;

  selectedFiles.forEach((file, index) => {
    const key = `${file.name}-${file.size}-${file.lastModified}`;

    if (!previewUrls.has(key)) {
      previewUrls.set(key, URL.createObjectURL(file));
    }

    const item = document.createElement("div");
    item.className = "file-item";

    const thumb = document.createElement("img");
    thumb.className = "thumb";
    thumb.alt = "";
    thumb.src = previewUrls.get(key);

    const meta = document.createElement("div");
    const name = document.createElement("p");
    const size = document.createElement("p");
    name.className = "file-name";
    size.className = "file-size";
    name.textContent = file.name;
    size.textContent = formatBytes(file.size);
    meta.append(name, size);

    const remove = document.createElement("button");
    remove.className = "remove-button";
    remove.type = "button";
    remove.title = "Hapus gambar";
    remove.setAttribute("aria-label", `Hapus ${file.name}`);
    remove.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 10.59 4.95-4.95 1.41 1.41L13.41 12l4.95 4.95-1.41 1.41L12 13.41l-4.95 4.95-1.41-1.41L10.59 12 5.64 7.05l1.41-1.41L12 10.59Z"></path></svg>';
    remove.addEventListener("click", () => removeFile(index));

    item.append(thumb, meta, remove);
    fileList.append(item);
  });
}

function filenameFromDisposition(disposition) {
  if (!disposition) return "hasil-resize-gambar.zip";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : "hasil-resize-gambar.zip";
}

function downloadBlob(blob, filename) {
  const downloadUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(downloadUrl);
}

function blobFromBase64(base64, contentType) {
  const byteCharacters = atob(base64);
  const chunks = [];

  for (let offset = 0; offset < byteCharacters.length; offset += 8192) {
    const slice = byteCharacters.slice(offset, offset + 8192);
    const bytes = new Uint8Array(slice.length);

    for (let index = 0; index < slice.length; index += 1) {
      bytes[index] = slice.charCodeAt(index);
    }

    chunks.push(bytes);
  }

  return new Blob(chunks, { type: contentType });
}

function downloadImageFiles(files) {
  files.forEach((file, index) => {
    const blob = blobFromBase64(file.data, file.contentType || "image/jpeg");
    window.setTimeout(() => downloadBlob(blob, file.filename), index * 250);
  });
}

chooseButton.addEventListener("click", () => imageInput.click());

outputModeInputs.forEach((input) => {
  input.addEventListener("change", () => {
    if (input.value === "image" && selectedFiles.length > 2) {
      document.querySelector('input[name="outputMode"][value="zip"]').checked = true;
      setStatus("Lebih dari 2 foto otomatis diunduh sebagai ZIP.", "error");
    }
  });
});

imageInput.addEventListener("change", () => {
  addFiles(imageInput.files);
});

dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    imageInput.click();
  }
});

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragover");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragover");
  });
});

dropZone.addEventListener("drop", (event) => {
  addFiles(event.dataTransfer.files);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (selectedFiles.length === 0) {
    setStatus("Pilih gambar terlebih dahulu.", "error");
    return;
  }

  const payload = new FormData();
  selectedFiles.forEach((file) => payload.append("images", file));
  payload.append("output_mode", outputMode());

  setBusy(true);
  setStatus("Gambar sedang diproses...");

  try {
    const response = await fetch("/resize", {
      method: "POST",
      body: payload,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || "Gagal memproses gambar.");
    }

    const responseMode = response.headers.get("X-Output-Mode");
    const contentType = response.headers.get("Content-Type") || "";

    const processed = response.headers.get("X-Processed-Count") || selectedFiles.length;
    const failed = Number(response.headers.get("X-Failed-Count") || 0);
    const suffix = failed > 0 ? `, ${failed} gagal` : "";

    if (responseMode === "image" || contentType.includes("application/json")) {
      const result = await response.json();
      downloadImageFiles(result.files || []);
      setStatus(`${processed} gambar berhasil diunduh sebagai JPG${suffix}.`, "success");
    } else {
      const blob = await response.blob();
      downloadBlob(blob, filenameFromDisposition(response.headers.get("Content-Disposition")));
      setStatus(`${processed} gambar berhasil diunduh sebagai ZIP${suffix}.`, "success");
    }
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(false);
  }
});
