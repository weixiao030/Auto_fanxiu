'use strict';

// Informational dialogs never submit game operations or change the automation policy.
(() => {
  const byId = id => document.getElementById(id);
  const declarationVersion = '2026-11-17.2';
  const readKey = 'fanxiu.disclaimer.read';
  const dialog = byId('disclaimer-dialog');
  const acknowledge = byId('disclaimer-acknowledge');
  const storageNote = byId('disclaimer-storage-note');
  let timer, returnFocus;

  function openDeclaration(source) {
    if (dialog.open) return;
    returnFocus = source || document.activeElement;
    acknowledge.disabled = true;
    let remaining = 3;
    acknowledge.textContent = `请阅读（${remaining}秒）`;
    dialog.showModal();
    byId('disclaimer-title').focus({preventScroll: true});
    dialog.scrollTop = 0;
    clearInterval(timer);
    timer = setInterval(() => {
      remaining -= 1;
      acknowledge.disabled = remaining > 0;
      acknowledge.textContent = remaining > 0 ? `请阅读（${remaining}秒）` : '已阅读，进入助手';
      if (remaining <= 0) clearInterval(timer);
    }, 1000);
  }

  dialog.addEventListener('close', () => {
    clearInterval(timer);
    if (returnFocus instanceof HTMLElement && returnFocus !== document.body) returnFocus.focus();
  });
  byId('disclaimer-later').addEventListener('click', () => dialog.close());
  acknowledge.addEventListener('click', () => {
    if (acknowledge.disabled) return;
    try { localStorage.setItem(readKey, declarationVersion); }
    catch (_) { storageNote.textContent = '浏览器未允许保存阅读记录，下次打开会再次提醒。'; }
    dialog.close();
  });
  document.querySelectorAll('[data-open-disclaimer]').forEach(button => {
    button.addEventListener('click', () => openDeclaration(button));
  });
  let hasRead = false;
  try { hasRead = localStorage.getItem(readKey) === declarationVersion; } catch (_) {}
  if (!hasRead) openDeclaration();

  const preview = byId('appreciation-preview');
  const image = byId('appreciation-code');
  const large = byId('appreciation-large');
  const appreciationDialog = byId('appreciation-dialog');
  function imageUnavailable() {
    preview.hidden = true;
    byId('appreciation-owner').hidden = true;
    byId('appreciation-unavailable').hidden = false;
    byId('appreciation-unavailable').textContent = '赞赏码暂不可用';
    if (appreciationDialog.open) appreciationDialog.close();
  }
  image.addEventListener('error', imageUnavailable);
  large.addEventListener('error', imageUnavailable);
  image.addEventListener('load', () => {
    preview.hidden = false;
    byId('appreciation-unavailable').hidden = true;
    byId('appreciation-owner').hidden = !byId('appreciation-owner').textContent;
  });
  preview.addEventListener('click', () => {
    if (preview.hidden || !image.naturalWidth) return;
    large.src = image.src;
    appreciationDialog.showModal();
  });
  byId('appreciation-close').addEventListener('click', () => appreciationDialog.close());
  appreciationDialog.addEventListener('close', () => { if (!preview.hidden) preview.focus(); });

  async function loadProjectInfo() {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 5000);
    try {
      const response = await fetch('/project-info.json', {cache: 'no-store', signal: abort.signal});
      if (!response.ok) return;
      const info = await response.json();
      if (info.github_url) {
        try {
          const url = new URL(info.github_url);
          if (url.protocol === 'https:' && url.hostname === 'github.com' && !url.username && !url.password && !url.port) {
            byId('project-github').href = url.href;
            byId('project-github').hidden = false;
          }
        } catch (_) {}
      }
      // Only the bundled, explicitly provided image is ever used as a payment code.
      if (info.appreciation_image === '/appreciation-code.webp') {
        const owner = typeof info.appreciation_owner === 'string' ? info.appreciation_owner.slice(0, 100) : '';
        byId('appreciation-owner').textContent = owner;
        byId('appreciation-dialog-owner').textContent = owner;
        image.alt = owner ? `${owner}的赞赏码` : '作者提供的赞赏码';
        image.src = info.appreciation_image;
      }
    } catch (_) {
      // Optional project information cannot interrupt the workbench or polling.
    } finally { clearTimeout(timeout); }
  }
  loadProjectInfo();
})();
