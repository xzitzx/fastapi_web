"use strict";

const body = document.getElementById("post-body");
const editorPane = body.closest(".editor-pane");
const preview = document.getElementById("preview");
const message = document.getElementById("editor-message");
const imageFile = document.getElementById("image-file");
const modeButtons = document.querySelectorAll("[data-mode]");
const csrfHeaders = { "X-CSRF-Token": body.form.elements.csrf_token.value };
let previewRequest = 0;

function setMode(mode) {
  for (const button of modeButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
  }
  editorPane.hidden = mode === "preview";
  preview.hidden = mode !== "preview";
  if (mode === "preview") {
    showPreview();
  }
}

async function showPreview() {
  // 只采用最近一次预览的结果，先发出的请求晚到时丢弃
  const request = ++previewRequest;
  message.textContent = "";
  preview.textContent = "";
  try {
    const response = await fetch("/preview", {
      method: "POST",
      headers: csrfHeaders,
      body: new URLSearchParams({ body: body.value }),
    });
    if (!response.ok) {
      throw new Error(response.status);
    }
    const html = await response.text();
    if (request === previewRequest) {
      preview.innerHTML = html;
    }
  } catch {
    if (request === previewRequest) {
      message.textContent = "预览失败，请重试";
    }
  }
}

async function upload(file) {
  message.textContent = "";
  const data = new FormData();
  data.append("file", file);
  let result = {};
  try {
    const response = await fetch("/uploads", { method: "POST", headers: csrfHeaders, body: data });
    result = await response.json();
  } catch {
    // 网络错误或响应不是 JSON，按上传失败提示
  }
  if (result.url) {
    // 图片单独成行，插在行首的 #、-、``` 等标记前面时不会破坏标题、列表或代码围栏
    const start = body.selectionStart;
    const before = start > 0 && body.value[start - 1] !== "\n" ? "\n" : "";
    const after = start < body.value.length && body.value[start] !== "\n" ? "\n" : "";
    const image = `![](${result.url})`;
    body.setRangeText(before + image + after, start, start);
    // 光标放在图片之后、补上的换行之前
    const caret = start + before.length + image.length;
    body.focus();
    body.setSelectionRange(caret, caret);
  } else {
    message.textContent = result.error || "上传失败，请重试";
  }
}

for (const button of modeButtons) {
  button.addEventListener("click", () => setMode(button.dataset.mode));
}

document.getElementById("insert-image").addEventListener("click", () => imageFile.click());

imageFile.addEventListener("change", () => {
  const file = imageFile.files[0];
  // 清空选择，再次选同一个文件时才会触发 change
  imageFile.value = "";
  if (file) {
    // 插图写进正文框，先切回编辑模式，插入结果才看得见
    setMode("edit");
    upload(file);
  }
});

body.addEventListener("paste", (event) => {
  const file = Array.from(event.clipboardData.files).find((item) => item.type.startsWith("image/"));
  if (file) {
    event.preventDefault();
    upload(file);
  }
});
