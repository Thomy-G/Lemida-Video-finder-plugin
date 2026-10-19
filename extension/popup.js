// popup.js - Lemida Video Finder UI Controller
(function () {
  'use strict';

  // State
  let currentVideos = [];
  let currentCourse = { title: 'Unknown Course', id: '-', url: '' };
  let currentTabId = null;
  let lastDiagnostics = null;
  const DEFAULT_XPATH = '/html/body/div[3]/div[5]/div/div/div[2]/div[2]/div/section/div[2]/div[1]/div[1]/div/video/source';

  // DOM Elements
  const videoListEl = document.getElementById('video-list');
  const countBadgeEl = document.getElementById('video-count-badge');
  const courseTitleEl = document.getElementById('course-title');
  const courseIdTagEl = document.getElementById('course-id-tag');
  const notLemidaBanner = document.getElementById('not-lemida-banner');
  const searchInput = document.getElementById('search-input');
  const clearSearchBtn = document.getElementById('clear-search');
  const refreshBtn = document.getElementById('refresh-btn');
  const copyAllBtn = document.getElementById('copy-all-btn');
  const deepScanBtn = document.getElementById('deep-scan-btn');
  const exportDropdownBtn = document.getElementById('export-dropdown-btn');
  const exportMenu = document.getElementById('export-menu');
  const exportTxtBtn = document.getElementById('export-txt-btn');
  const exportJsonBtn = document.getElementById('export-json-btn');
  const exportM3uBtn = document.getElementById('export-m3u-btn');
  const exportYtdlpBtn = document.getElementById('export-ytdlp-btn');
  const exportCliBtn = document.getElementById('export-cli-btn');
  const toggleXpathBtn = document.getElementById('toggle-xpath-btn');
  const xpathDrawer = document.getElementById('xpath-drawer');
  const closeDrawerBtn = document.getElementById('close-drawer-btn');
  const customXpathInput = document.getElementById('custom-xpath-input');
  const applyXpathBtn = document.getElementById('apply-xpath-btn');
  const resetXpathBtn = document.getElementById('reset-xpath-btn');
  const copySessionBtn = document.getElementById('copy-session-btn');
  const diagnoseBtn = document.getElementById('diagnose-btn');
  const diagDrawer = document.getElementById('diag-drawer');
  const closeDiagBtn = document.getElementById('close-diag-btn');
  const diagContent = document.getElementById('diag-content');
  const copyDiagBtn = document.getElementById('copy-diag-btn');
  const toastEl = document.getElementById('toast');

  /**
   * Show temporary toast
   */
  function showToast(message) {
    toastEl.textContent = message;
    toastEl.classList.remove('hidden');
    toastEl.style.animation = 'none';
    toastEl.offsetHeight; // reflow
    toastEl.style.animation = null;

    setTimeout(() => {
      toastEl.classList.add('hidden');
    }, 2200);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Render video list
   */
  function renderVideos(videosToRender, activityCount = 0) {
    if (!videosToRender || videosToRender.length === 0) {
      if (activityCount > 0) {
        videoListEl.innerHTML = `
          <div class="empty-state" style="padding: 24px 16px;">
            <div style="font-size: 24px;">📁</div>
            <h4 style="color: #f8fafc; font-size: 13px;">Found ${activityCount} Video Activities</h4>
            <p style="font-size: 11.5px; color: #94a3b8; line-height: 1.5;">
              In this course, video streams are located inside individual lecture activity subpages (e.g. Kaltura, Panopto, or Resource pages).
            </p>
            <button id="empty-deep-scan-btn" class="btn btn-primary" style="margin-top: 8px;">
              ⚡ Run Deep Scan (${activityCount} Activities)
            </button>
            <button id="empty-diag-btn" class="link-btn" style="margin-top: 6px;">
              🔍 View DOM Diagnostics
            </button>
          </div>
        `;
        const emptyDeep = document.getElementById('empty-deep-scan-btn');
        if (emptyDeep) emptyDeep.addEventListener('click', runDeepScan);
        const emptyDiag = document.getElementById('empty-diag-btn');
        if (emptyDiag) emptyDiag.addEventListener('click', runDiagnosticsAction);
        return;
      }

      videoListEl.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 24 24" width="32" height="32" stroke="currentColor" stroke-width="1.5" fill="none" style="color: #64748b;">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          <p>0 direct videos detected on the active page.</p>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <button id="empty-deep-scan-btn" class="btn btn-sm btn-secondary">Run Deep Scan</button>
            <button id="empty-diag-btn" class="btn btn-sm btn-ghost">🔍 Diagnose Page</button>
          </div>
        </div>
      `;
      const emptyDeep = document.getElementById('empty-deep-scan-btn');
      if (emptyDeep) emptyDeep.addEventListener('click', runDeepScan);
      const emptyDiag = document.getElementById('empty-diag-btn');
      if (emptyDiag) emptyDiag.addEventListener('click', runDiagnosticsAction);
      return;
    }

    let html = '';
    videosToRender.forEach((vid, index) => {
      const typeLabel = vid.sourceType === 'iframe' ? 'Iframe' : (vid.type || 'MP4');
      html += `
        <div class="video-card" data-id="${vid.id}">
          <div class="video-card-header">
            <div class="video-title-area">
              <span class="video-index">${index + 1}</span>
              <span class="video-title" title="${escapeHtml(vid.title)}">${escapeHtml(vid.title)}</span>
            </div>
            <div class="video-meta-tags">
              <span class="meta-pill meta-pill-section" title="Section: ${escapeHtml(vid.section)}">${escapeHtml(vid.section)}</span>
              <span class="meta-pill meta-pill-type">${escapeHtml(typeLabel)}</span>
            </div>
          </div>

          <div class="video-url-container">
            <span class="video-url-text" title="${escapeHtml(vid.url)}">${escapeHtml(vid.url)}</span>
          </div>

          <div class="card-actions">
            <button class="action-chip action-chip-primary copy-single-btn" data-url="${escapeHtml(vid.url)}">
              📋 Copy Link
            </button>
            <button class="action-chip open-tab-btn" data-url="${escapeHtml(vid.url)}">
              ▶ Open / Preview
            </button>
            <button class="action-chip copy-ytdlp-single-btn" data-url="${escapeHtml(vid.url)}" data-title="${escapeHtml(vid.title)}">
              💻 yt-dlp
            </button>
          </div>
        </div>
      `;
    });

    videoListEl.innerHTML = html;

    // Attach listeners
    videoListEl.querySelectorAll('.copy-single-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.getAttribute('data-url');
        navigator.clipboard.writeText(url).then(() => showToast('Link copied to clipboard!'));
      });
    });

    videoListEl.querySelectorAll('.open-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.getAttribute('data-url');
        chrome.tabs.create({ url });
      });
    });

    videoListEl.querySelectorAll('.copy-ytdlp-single-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const url = btn.getAttribute('data-url');
        const title = btn.getAttribute('data-title').replace(/["\\]/g, '');
        const cmd = `yt-dlp "${url}" -o "${title}.%(ext)s"`;
        navigator.clipboard.writeText(cmd).then(() => showToast('yt-dlp command copied!'));
      });
    });
  }

  function filterVideos() {
    const q = searchInput.value.trim().toLowerCase();
    if (!q) {
      clearSearchBtn.classList.add('hidden');
      renderVideos(currentVideos);
      return;
    }

    clearSearchBtn.classList.remove('hidden');
    const filtered = currentVideos.filter(v =>
      (v.title && v.title.toLowerCase().includes(q)) ||
      (v.section && v.section.toLowerCase().includes(q)) ||
      (v.url && v.url.toLowerCase().includes(q))
    );
    renderVideos(filtered);
  }

  /**
   * Request page scan, auto-injecting content.js if necessary
   */
  function performScan(customXPath = null, retryCount = 0) {
    if (!currentTabId) return;

    videoListEl.innerHTML = `
      <div class="empty-state">
        <div class="spinner"></div>
        <p>Scanning course page for videos...</p>
      </div>
    `;

    chrome.tabs.sendMessage(
      currentTabId,
      { action: 'SCAN_VIDEOS', customXPath },
      (response) => {
        if (chrome.runtime.lastError || !response) {
          // If content script was not injected on existing tab, inject dynamically
          if (retryCount === 0) {
            chrome.scripting.executeScript({
              target: { tabId: currentTabId, allFrames: true },
              files: ['content.js']
            }, () => {
              // Wait 100ms then retry
              setTimeout(() => performScan(customXPath, 1), 150);
            });
            return;
          }

          courseTitleEl.textContent = 'Connection Error';
          videoListEl.innerHTML = `
            <div class="empty-state">
              <p>Please refresh the Lemida tab (F5) and open the extension again.</p>
              <button id="retry-scan-btn" class="btn btn-sm btn-primary">Refresh & Retry</button>
            </div>
          `;
          const retryBtn = document.getElementById('retry-scan-btn');
          if (retryBtn) {
            retryBtn.addEventListener('click', () => {
              chrome.tabs.reload(currentTabId, () => window.close());
            });
          }
          return;
        }

        currentVideos = response.videos || [];
        currentCourse = response.course || currentCourse;

        courseTitleEl.textContent = currentCourse.title || 'Lemida Course';
        courseTitleEl.title = currentCourse.title || '';
        courseIdTagEl.textContent = `ID: ${currentCourse.id || '-'}`;
        countBadgeEl.textContent = `${currentVideos.length} Video${currentVideos.length === 1 ? '' : 's'}`;

        renderVideos(currentVideos, response.activityLinksCount || 0);
      }
    );
  }

  function runDeepScan() {
    if (!currentTabId) return;

    deepScanBtn.disabled = true;
    deepScanBtn.innerHTML = `
      <div class="spinner" style="width: 12px; height: 12px; border-width: 2px;"></div>
      Scanning...
    `;

    chrome.tabs.sendMessage(currentTabId, { action: 'DEEP_SCAN' }, (response) => {
      deepScanBtn.disabled = false;
      deepScanBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="15" height="15" stroke="currentColor" stroke-width="2" fill="none">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        Deep Scan
      `;

      if (response && response.videos) {
        currentVideos = response.videos;
        countBadgeEl.textContent = `${currentVideos.length} Video${currentVideos.length === 1 ? '' : 's'}`;
        renderVideos(currentVideos);
        showToast(`Deep scan found ${currentVideos.length} videos!`);
      } else {
        showToast('Deep scan completed.');
      }
    });
  }

  function runDiagnosticsAction() {
    if (!currentTabId) return;
    diagDrawer.classList.remove('hidden');
    xpathDrawer.classList.add('hidden');
    diagContent.textContent = 'Analyzing DOM elements on page...';

    chrome.tabs.sendMessage(currentTabId, { action: 'DIAGNOSE' }, (res) => {
      if (chrome.runtime.lastError || !res || !res.diagnostics) {
        diagContent.textContent = 'Could not run diagnostics. Try refreshing the Lemida page.';
        return;
      }
      lastDiagnostics = res.diagnostics;
      diagContent.textContent = JSON.stringify(res.diagnostics, null, 2);
    });
  }

  function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`Downloaded ${filename}`);
  }

  function initApp() {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs[0]) return;
      const tab = tabs[0];
      currentTabId = tab.id;
      const url = tab.url || '';

      if (!url.includes('lemida.biu.ac.il')) {
        notLemidaBanner.classList.remove('hidden');
        courseTitleEl.textContent = 'Not on Lemida';
        countBadgeEl.textContent = 'Inactive';
        videoListEl.innerHTML = `
          <div class="empty-state">
            <p>Open a course page on <strong>lemida.biu.ac.il</strong> to start finding videos.</p>
          </div>
        `;
        return;
      }

      notLemidaBanner.classList.add('hidden');
      performScan();
    });
  }

  // Event Listeners
  refreshBtn.addEventListener('click', () => performScan(customXpathInput.value.trim()));
  searchInput.addEventListener('input', filterVideos);
  clearSearchBtn.addEventListener('click', () => {
    searchInput.value = '';
    filterVideos();
  });

  copyAllBtn.addEventListener('click', () => {
    if (!currentVideos.length) return showToast('No video links to copy.');
    const allLinks = currentVideos.map(v => v.url).join('\n');
    navigator.clipboard.writeText(allLinks).then(() => {
      showToast(`Copied ${currentVideos.length} links to clipboard!`);
    });
  });

  deepScanBtn.addEventListener('click', runDeepScan);

  exportDropdownBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    exportMenu.classList.toggle('hidden');
  });

  document.addEventListener('click', () => {
    exportMenu.classList.add('hidden');
  });

  exportTxtBtn.addEventListener('click', () => {
    if (!currentVideos.length) return showToast('No videos to export');
    const lines = currentVideos.map(v => `${v.title} [${v.section}]\n${v.url}\n`);
    const content = `Course: ${currentCourse.title} (ID: ${currentCourse.id})\nTotal Videos: ${currentVideos.length}\n\n` + lines.join('\n');
    downloadFile(content, `lemida_course_${currentCourse.id}_videos.txt`, 'text/plain;charset=utf-8');
  });

  exportJsonBtn.addEventListener('click', () => {
    if (!currentVideos.length) return showToast('No videos to export');
    const data = {
      course: currentCourse,
      total: currentVideos.length,
      extractedAt: new Date().toISOString(),
      videos: currentVideos
    };
    downloadFile(JSON.stringify(data, null, 2), `lemida_course_${currentCourse.id}_videos.json`, 'application/json');
  });

  exportM3uBtn.addEventListener('click', () => {
    if (!currentVideos.length) return showToast('No videos to export');
    let m3u = '#EXTM3U\n';
    currentVideos.forEach(v => {
      m3u += `#EXTINF:-1 group-title="${v.section}",${v.title}\n${v.url}\n`;
    });
    downloadFile(m3u, `lemida_course_${currentCourse.id}.m3u`, 'audio/x-mpegurl');
  });

  exportYtdlpBtn.addEventListener('click', () => {
    if (!currentVideos.length) return showToast('No videos to export');
    const commands = currentVideos.map(v => {
      const cleanTitle = v.title.replace(/["\\]/g, '');
      return `yt-dlp "${v.url}" -o "${cleanTitle}.%(ext)s"`;
    }).join('\n');
    navigator.clipboard.writeText(commands).then(() => {
      showToast('Copied yt-dlp commands for all videos!');
    });
  });

  exportCliBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'GET_COOKIES' }, (res) => {
      const session = res && res.moodleSession ? res.moodleSession : '';
      const courseId = currentCourse.id !== '-' ? currentCourse.id : '108883';
      const cmd = session
        ? `uv run lemida-cli fetch ${courseId} --cookie "${session}"`
        : `uv run lemida-cli fetch ${courseId} --login`;

      navigator.clipboard.writeText(cmd).then(() => {
        showToast('Copied CLI command to clipboard!');
      });
    });
  });

  // Drawers
  toggleXpathBtn.addEventListener('click', () => {
    xpathDrawer.classList.toggle('hidden');
    diagDrawer.classList.add('hidden');
  });

  closeDrawerBtn.addEventListener('click', () => xpathDrawer.classList.add('hidden'));

  diagnoseBtn.addEventListener('click', runDiagnosticsAction);
  closeDiagBtn.addEventListener('click', () => diagDrawer.classList.add('hidden'));

  copyDiagBtn.addEventListener('click', () => {
    if (diagContent.textContent) {
      navigator.clipboard.writeText(diagContent.textContent).then(() => {
        showToast('Copied diagnostics to clipboard!');
      });
    }
  });

  applyXpathBtn.addEventListener('click', () => {
    const custom = customXpathInput.value.trim();
    xpathDrawer.classList.add('hidden');
    performScan(custom);
    showToast('Applied custom XPath!');
  });

  resetXpathBtn.addEventListener('click', () => {
    customXpathInput.value = DEFAULT_XPATH;
    performScan();
    showToast('Reset to default XPath.');
  });

  copySessionBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'GET_COOKIES' }, (res) => {
      if (res && res.cookieHeader) {
        navigator.clipboard.writeText(res.cookieHeader).then(() => {
          showToast('Copied Lemida cookie string!');
        });
      } else {
        showToast('Could not read cookies.');
      }
    });
  });

  initApp();
})();
